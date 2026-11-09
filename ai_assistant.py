"""
AI Assistant for SC&WMS — "ask your database in plain language".

Flow:   question  ->  LLM writes a SQL SELECT  ->  server VALIDATES it  ->
        runs it READ-ONLY with a timeout  ->  LLM explains the result  ->  answer + table

Providers: Google Gemini (primary) and Groq (automatic backup). Both have free tiers.
API keys are read from the server environment (.env / Vercel settings) — never from the browser.
"""
import json
import re
from datetime import date, datetime
from decimal import Decimal

import requests

import config

MAX_ROWS        = 50           # rows returned to the UI
SUMMARY_ROWS    = 10           # rows sent to the LLM for the explanation
STATEMENT_MS    = 4000         # DB statement timeout
HTTP_TIMEOUT    = 8            # seconds per LLM call (Vercel hobby = 10s max)
# columns that hold personal data are never sent to the LLM
PII_COLUMNS = {'phone', 'email', 'contact', 'address', 'customer_address',
               'supplier_email', 'supplier_contact', 'password'}

SYSTEM_PROMPT = """You are the data assistant of SC&WMS, a Supply Chain & Warehouse Management System \
running on PostgreSQL. Currency is PKR. Today is {today}.

TABLES (column names are lower-case):
supplier(supplier_id, name, contact, email, address)
product(product_id, product_name, category, price, supplier_id -> supplier)
warehouse(warehouse_id, location, latitude, longitude)
customer(customer_id, name, phone, email, address, latitude, longitude)
stock(stock_id, product_id -> product, warehouse_id -> warehouse, quantity)   -- one row per product+warehouse
orders(order_id, customer_id -> customer, product_id -> product, quantity, order_date, status)
        -- status: Pending | Processing | Shipped | Delivered | Cancelled
shipment(shipment_id, order_id -> orders (1:1), shipment_date, status, carrier, tracking_no, origin_warehouse_id -> warehouse)
        -- status: In Transit | Delivered | Returned
shipment_tracking(event_id, shipment_id -> shipment, event_type, location_name, latitude, longitude, note, event_time)
reorderrule(rule_id, product_id, warehouse_id, reorder_point, safety_stock)
inventory_transaction(trans_id, product_id, warehouse_id, trans_type, quantity, trans_date, reference_no, notes)
        -- trans_type: Receipt | Sale | Return | Adjustment | Transfer_In | Transfer_Out

VIEWS (prefer these when they fit):
low_stock_alert(product_name, category, warehouse, quantity)                -- stock below 10
reorder_alert(product_name, category, warehouse, current_stock, reorder_point, safety_stock, units_needed)
order_summary(order_id, customer_name, product_name, supplier_name, quantity, order_date, status)
warehouse_inventory(warehouse_id, location, product_id, product_name, category, quantity)
supplier_product_summary(supplier_id, supplier_name, contact, total_products, avg_product_price, total_stock)
shipment_tracking_detail(shipment_id, tracking_no, carrier, order_id, shipment_status, shipment_date, customer_name,
        product_name, quantity, origin_warehouse, last_event, last_location, last_event_time)

Order value = orders.quantity * product.price.

RULES
1. Reply with ONE JSON object and nothing else (no markdown, no code fences):
   {{"sql": "<one SELECT query or null>", "explanation": "<one short sentence on what the query shows>", "reply": "<text, only when sql is null>"}}
2. Only read data: a single SELECT (or WITH ... SELECT). Never INSERT/UPDATE/DELETE/DDL. Never touch a table named users.
3. Use unquoted lower-case identifiers, ILIKE for text search, and LIMIT 50 unless the user asks for more.
4. If the message is a greeting, a general question, or asks to change data, set "sql" to null and put a helpful
   answer in "reply" (for changes: explain this assistant is read-only and point to the right page of the app).
5. Write "explanation" and "reply" in the same language as the user (English, Urdu, or Roman Urdu).
"""

SUMMARY_PROMPT = """You are a concise business analyst for SC&WMS (currency PKR). You get the user's question and the \
rows returned by the database. Answer in 2-4 short sentences in the SAME language as the question \
(English, Urdu or Roman Urdu). Use only the data given; mention key numbers; if there are no rows say nothing was found. \
No markdown tables, no code."""


class AIUnavailable(Exception):
    """No provider could answer (no key, quota, network...)."""


class SqlRejected(Exception):
    """The generated SQL failed the safety check."""


# ──────────────────────────────────────────────────────────────
#  1. SQL SAFETY
# ──────────────────────────────────────────────────────────────
_BLOCKED = re.compile(
    r'\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|copy|call|do|execute|merge|vacuum|'
    r'analyze|refresh|lock|listen|notify|set|reset|show|explain|comment|into|pg_sleep|lo_import|lo_export|'
    r'dblink|set_config|current_setting|users|password|information_schema)\b|\bpg_\w+', re.I)


def _strip_literals(sql):
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def validate_sql(sql):
    """Return a cleaned single SELECT statement or raise SqlRejected."""
    if not sql or not isinstance(sql, str):
        raise SqlRejected('empty query')
    s = re.sub(r'/\*.*?\*/', ' ', sql, flags=re.S)          # block comments
    s = re.sub(r'--[^\n]*', ' ', s).strip()                  # line comments
    s = re.sub(r'"([A-Za-z_][A-Za-z0-9_]*)"', r'\1', s)      # "Name" -> Name
    s = s.rstrip(';').strip()
    probe = _strip_literals(s)
    if ';' in probe:
        raise SqlRejected('only one statement is allowed')
    if '"' in probe or '$$' in probe:
        raise SqlRejected('quoted identifiers are not allowed')
    if not re.match(r'^(select|with)\b', probe, re.I):
        raise SqlRejected('only SELECT queries are allowed')
    m = _BLOCKED.search(probe)
    if m:
        raise SqlRejected(f'"{m.group(0)}" is not allowed')
    return s


# ──────────────────────────────────────────────────────────────
#  2. LLM PROVIDERS  (Gemini primary, Groq backup)
# ──────────────────────────────────────────────────────────────
def _gemini(model, system, messages):
    # Try v1 first, fall back to v1beta
    for api_ver in ('v1', 'v1beta'):
        url = (f'https://generativelanguage.googleapis.com/{api_ver}/models/'
               f'{model}:generateContent?key={config.GEMINI_API_KEY}')
        body = {
            'contents': [
                {'role': 'user',
                 'parts': [{'text': f'[System context]\n{system}\n\n[User question]\n{messages[-1]["content"]}'}]}
            ],
            'generationConfig': {'temperature': 0.1, 'maxOutputTokens': 800},
        }
        r = requests.post(url, json=body, timeout=HTTP_TIMEOUT,
                          headers={'Content-Type': 'application/json'})
        if r.status_code == 200:
            data  = r.json()
            parts = (data.get('candidates') or [{}])[0].get('content', {}).get('parts', [])
            text  = ''.join(p.get('text', '') for p in parts if not p.get('thought'))
            if text.strip():
                return text
        elif r.status_code != 404:
            # 404 = try next api version; anything else = real error
            try: err_msg = r.json().get('error', {}).get('message', r.text[:200])
            except: err_msg = r.text[:200]
            raise _HttpError(r.status_code, err_msg)
    try: err_msg = r.json().get('error', {}).get('message', r.text[:200])
    except: err_msg = r.text[:200]
    raise _HttpError(404, err_msg)
    data = r.json()
    parts = (data.get('candidates') or [{}])[0].get('content', {}).get('parts', [])
    text = ''.join(p.get('text', '') for p in parts if not p.get('thought'))
    if not text.strip():
        raise _HttpError(502, 'empty response')
    return text


def _groq(model, system, messages):
    body = {
        'model': model, 'temperature': 0.1, 'max_tokens': 800,
        'messages': [{'role': 'system', 'content': system}] + messages,
    }
    r = requests.post('https://api.groq.com/openai/v1/chat/completions', json=body, timeout=HTTP_TIMEOUT,
                      headers={'Authorization': f'Bearer {config.GROQ_API_KEY}',
                               'Content-Type': 'application/json'})
    if r.status_code != 200:
        raise _HttpError(r.status_code, r.text)
    text = r.json()['choices'][0]['message']['content'] or ''
    if not text.strip():
        raise _HttpError(502, 'empty response')
    return text


class _HttpError(Exception):
    def __init__(self, status, body):
        super().__init__(f'HTTP {status}')
        self.status = status
        self.body = (body or '')[:200]


def _providers():
    order = {'gemini': ['gemini'], 'groq': ['groq']}.get(config.AI_PROVIDER, ['gemini', 'groq'])
    out = []
    for p in order:
        if p == 'gemini' and config.GEMINI_API_KEY:
            out.append(('Gemini', _gemini, config.GEMINI_MODELS))
        if p == 'groq' and config.GROQ_API_KEY:
            out.append(('Groq', _groq, config.GROQ_MODELS))
    return out


def chat(system, messages):
    """Try providers/models in order. Returns (text, provider_name, model)."""
    providers = _providers()
    if not providers:
        raise AIUnavailable('AI is not configured yet. Add GEMINI_API_KEY and/or GROQ_API_KEY to the .env file.')
    errors = []
    for name, fn, models in providers:
        for model in models:
            try:
                return fn(model, system, messages), name, model
            except _HttpError as e:
                errors.append(f'{name}/{model}: {e}')
                if e.status in (401, 403):      # bad key -> skip this provider entirely
                    break
            except requests.RequestException as e:
                errors.append(f'{name}/{model}: network error ({type(e).__name__})')
    raise AIUnavailable('All AI providers failed — ' + '; '.join(errors[-4:]))


def _parse_json(text):
    t = text.strip()
    t = re.sub(r'^```(?:json)?|```$', '', t, flags=re.M).strip()
    a, b = t.find('{'), t.rfind('}')
    if a != -1 and b > a:
        try:
            return json.loads(t[a:b + 1])
        except ValueError:
            pass
    return {'sql': None, 'reply': text.strip()}


# ──────────────────────────────────────────────────────────────
#  3. SAFE EXECUTION
# ──────────────────────────────────────────────────────────────
def _jsonable(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat(sep=' ', timespec='minutes') if isinstance(v, datetime) else v.isoformat()
    return v


def run_readonly(sql):
    """Execute a validated SELECT in a READ ONLY transaction with a timeout."""
    conn = config.get_db(readonly_ai=True)
    try:
        conn.set_session(readonly=True, autocommit=False)
        cur = conn.cursor()
        cur.execute(f'SET LOCAL statement_timeout = {STATEMENT_MS}')
        cur.execute(f'SELECT * FROM ({sql}) AS _q LIMIT {MAX_ROWS + 1}')
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        truncated = len(rows) > MAX_ROWS
        rows = [[_jsonable(v) for v in r] for r in rows[:MAX_ROWS]]
        return cols, rows, truncated
    finally:
        conn.rollback()
        conn.close()


# ──────────────────────────────────────────────────────────────
#  4. PUBLIC API
# ──────────────────────────────────────────────────────────────
def status():
    return {'gemini': bool(config.GEMINI_API_KEY), 'groq': bool(config.GROQ_API_KEY),
            'configured': config.ai_configured()}


def _history_messages(history):
    msgs = []
    for h in (history or [])[-3:]:
        q = str(h.get('q', ''))[:500]
        sql = h.get('sql')
        if q:
            msgs.append({'role': 'user', 'content': q})
            msgs.append({'role': 'assistant', 'content': json.dumps({'sql': str(sql)[:1500] if sql else None})})
    return msgs


def ask(question, history=None):
    """Answer a natural-language question about the database."""
    question = (question or '').strip()[:500]
    if not question:
        return {'ok': False, 'error': 'Please type a question.'}

    system = SYSTEM_PROMPT.format(today=date.today().isoformat())
    messages = _history_messages(history) + [{'role': 'user', 'content': question}]
    provider = model = None

    try:
        plan = None
        for attempt in range(2):                       # 2nd attempt = self-repair after an SQL error
            text, provider, model = chat(system, messages)
            plan = _parse_json(text)
            sql = plan.get('sql')
            if not sql:                                # greeting / help / refusal
                return {'ok': True, 'reply': plan.get('reply') or plan.get('explanation') or '…',
                        'sql': None, 'columns': [], 'rows': [], 'provider': provider, 'model': model}
            try:
                clean = validate_sql(sql)
                cols, rows, truncated = run_readonly(clean)
                break
            except SqlRejected as e:
                err = f'Rejected by the safety filter: {e}'
            except Exception as e:                     # database error (bad column, timeout, ...)
                err = str(e).strip().splitlines()[0][:300]
            if attempt == 1:
                return {'ok': False, 'sql': sql, 'provider': provider, 'model': model,
                        'error': f'I could not build a safe query for that. ({err})'}
            messages += [{'role': 'assistant', 'content': text},
                         {'role': 'user', 'content': f'That query failed: {err}. Fix it and return the JSON again.'}]

        # explain the result (PII columns removed before anything leaves the server)
        keep = [i for i, c in enumerate(cols) if c.lower() not in PII_COLUMNS]
        payload = {'question': question, 'columns': [cols[i] for i in keep],
                   'rows': [[r[i] for i in keep] for r in rows[:SUMMARY_ROWS]], 'total_rows': len(rows)}
        try:
            answer, provider, model = chat(SUMMARY_PROMPT, [{'role': 'user', 'content': json.dumps(payload, default=str)}])
        except AIUnavailable:
            answer = plan.get('explanation') or 'Here is the result.'
        return {'ok': True, 'reply': answer.strip(), 'sql': clean, 'columns': cols, 'rows': rows,
                'truncated': truncated, 'provider': provider, 'model': model}

    except AIUnavailable as e:
        return {'ok': False, 'error': str(e)}
