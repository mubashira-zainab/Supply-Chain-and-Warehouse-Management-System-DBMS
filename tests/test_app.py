"""End-to-end test: needs PostgreSQL with a FRESH schema.sql + sample_data.sql loaded.
Run from the project root:  python tests/test_app.py   (set DB_PASSWORD in .env or the environment)
"""
import os, re, sys, json
os.environ.setdefault('SECRET_KEY', 'test-secret')
for k in ('GEMINI_API_KEY','GROQ_API_KEY','DATABASE_URL'): os.environ.pop(k, None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as A
import ai_assistant, config
c = A.app.test_client()
ok = fail = 0
def chk(name, cond, extra=''):
    global ok, fail
    if cond: ok += 1; print('PASS', name)
    else: fail += 1; print('FAIL', name, extra)

def token(path='/login'):
    r = c.get(path); m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', r.get_data(as_text=True)); return m.group(1)

# 1 login page / csrf
r = c.post('/login', data={'username':'admin','password':'admin123'})
chk('POST without CSRF is blocked (400)', r.status_code == 400)
t = token()
r = c.post('/login', data={'username':'admin','password':'wrong','csrf_token':t})
chk('wrong password rejected', b'Invalid credentials' in r.data)
t = token()
r = c.post('/login', data={'username':'admin','password':'admin123','csrf_token':t}, follow_redirects=False)
chk('admin login ok -> redirect', r.status_code == 302)

# 2 all pages load
pages = ['/dashboard','/suppliers','/products','/warehouses','/stock','/customers','/orders','/shipments',
         '/reports','/ledger','/reorder','/assistant','/shipments/1/track','/shipments/3/track','/shipments/4/track']
for p in pages:
    r = c.get(p); chk(f'GET {p} = 200', r.status_code == 200, r.status_code)

# 3 tracking API
j = c.get('/api/shipments/3/tracking').get_json()
chk('api tracking ok', j['ok'] and j['t']['status']=='In Transit' and len(j['t']['events'])==4, j)
print('   s3:', j['t']['origin_name'], '->', j['t']['address'], '| progress', j['t']['progress'], '| dist', j['t']['distance_km'], '| rem', j['t']['remaining_km'], '| eta', j['t']['eta'])
j1 = c.get('/api/shipments/1/tracking').get_json()['t']
chk('delivered shipment 100%', j1['progress']==100 and j1['eta'] is None, j1['progress'])
print('   s1:', j1['origin_name'], '->', j1['address'], j1['distance_km'], 'km')

# 4 simulate shipment 4 until delivered
t = token('/shipments/4/track'); seen=[]
for i in range(8):
    r = c.post('/shipments/4/simulate', data={'csrf_token':t}, follow_redirects=True)
    tp = c.get('/api/shipments/4/tracking').get_json()['t']
    seen.append((tp['status'], tp['events'][-1]['type'], tp['events'][-1]['location'], tp['progress']))
    if tp['status']=='Delivered': break
for s_ in seen: print('   sim:', s_)
chk('simulation reaches Delivered', seen[-1][0]=='Delivered')
st = A.db_fetch("SELECT status FROM Orders WHERE Order_ID=4")[0]['status']
chk('trigger synced order -> Delivered', st=='Delivered', st)

# 5 manual checkpoint on shipment 3
t = token('/shipments/3/track')
r = c.post('/shipments/3/checkpoint', data={'csrf_token':t,'city':'Hyderabad','event_type':'In Transit','note':'test'}, follow_redirects=True)
n = len(c.get('/api/shipments/3/tracking').get_json()['t']['events'])
chk('manual checkpoint added', n==5, n)
r = c.post('/shipments/3/checkpoint', data={'csrf_token':t,'city':'Atlantis','event_type':'In Transit'}, follow_redirects=True)
chk('invalid city rejected', c.get('/api/shipments/3/tracking').get_json()['t']['events'].__len__()==5)

# 6 returned status -> event
r = c.post('/shipments/update/3', data={'csrf_token':t,'status':'Returned'}, follow_redirects=True)
tp = c.get('/api/shipments/3/tracking').get_json()['t']
chk('returned -> event at origin', tp['status']=='Returned' and tp['events'][-1]['type']=='Returned', tp['events'][-1])

# 7 new warehouse/customer get coordinates; delete via POST
t = token('/warehouses')
c.post('/warehouses/add', data={'csrf_token':t,'location':'Peshawar North Depot'}, follow_redirects=True)
w = A.db_fetch("SELECT * FROM Warehouse WHERE Location='Peshawar North Depot'")
chk('new warehouse geocoded', w and float(w[0]['latitude'])>33, w)
r = c.get(f"/warehouses/delete/{w[0]['warehouse_id']}"); chk('GET delete -> 405', r.status_code==405)
r = c.post(f"/warehouses/delete/{w[0]['warehouse_id']}", data={'csrf_token':t}, follow_redirects=True)
chk('POST delete works', not A.db_fetch("SELECT 1 FROM Warehouse WHERE Location='Peshawar North Depot'"))

# 8 AI endpoint: unconfigured, mocked, rate-limit & safety
t = token('/assistant'); H = {'X-CSRF-Token': t}
r = c.post('/api/assistant', json={'question':'hello'}, headers=H).get_json()
chk('AI unconfigured -> friendly error', (not r['ok']) and 'not configured' in r['error'], r)
r = c.post('/api/assistant', json={'question':'hello'})
chk('AI POST without CSRF -> 400', r.status_code==400)

import itertools
responses = iter([])
def fake_chat(system, messages):
    return next(responses), 'Gemini', 'mock-model'
ai_assistant.chat = fake_chat
responses = iter([json.dumps({'sql':'SELECT product_name, quantity FROM low_stock_alert ORDER BY quantity','explanation':'low stock'}), 'Two products are running low.'])
r = c.post('/api/assistant', json={'question':'low stock?'}, headers=H).get_json()
chk('AI happy path runs SQL + summary', r['ok'] and r['rows'] and 'running low' in r['reply'], r)
print('   cols', r['columns'], 'rows', len(r['rows']))
responses = iter([json.dumps({'sql':'DELETE FROM product','explanation':'x'}), json.dumps({'sql':'SELECT * FROM users','explanation':'x'})])
r = c.post('/api/assistant', json={'question':'delete everything'}, headers=H).get_json()
chk('AI malicious SQL blocked (both attempts)', (not r['ok']) and 'safe query' in r['error'], r)
print('   products intact:', A.db_fetch('SELECT COUNT(*) c FROM Product')[0]['c'])
responses = iter([json.dumps({'sql':'SELECT nonexistent FROM product','explanation':'x'}), json.dumps({'sql':'SELECT product_name FROM product LIMIT 3','explanation':'fixed'}), 'Here are 3 products.'])
r = c.post('/api/assistant', json={'question':'products'}, headers=H).get_json()
chk('AI self-repair after SQL error', r['ok'] and len(r['rows'])==3, r)
responses = iter([json.dumps({'sql':None,'reply':'Hi! Ask me about stock.'})])
r = c.post('/api/assistant', json={'question':'salam'}, headers=H).get_json()
chk('AI chit-chat without SQL', r['ok'] and r['sql'] is None, r)
# read-only transaction really blocks writes even if filter were bypassed
try:
    conn = config.get_db(); conn.set_session(readonly=True); cur = conn.cursor(); cur.execute("DELETE FROM Supplier WHERE Supplier_ID=-1"); chk('readonly session blocks writes', False)
except Exception as e: chk('readonly session blocks writes', 'read-only' in str(e)); 
finally: conn.rollback(); conn.close()

# 9 roles
c2 = A.app.test_client()
tt = re.search(r'name="csrf-token" content="([0-9a-f]+)"', c2.get('/login').get_data(as_text=True)).group(1)
c2.post('/login', data={'username':'viewer','password':'viewer123','csrf_token':tt})
tt = re.search(r'name="csrf-token" content="([0-9a-f]+)"', c2.get('/suppliers').get_data(as_text=True)).group(1)
before = A.db_fetch('SELECT COUNT(*) c FROM Supplier')[0]['c']
c2.post('/suppliers/add', data={'csrf_token':tt,'name':'X','contact':'1','email':'a@b','address':'Lahore'}, follow_redirects=True)
chk('viewer cannot add', A.db_fetch('SELECT COUNT(*) c FROM Supplier')[0]['c']==before)
c3 = A.app.test_client()
chk('anonymous redirected to login', c3.get('/dashboard').status_code==302)
chk('anonymous API gets 401', c3.get('/api/shipments/1/tracking').status_code==401)
print(f'\nRESULT: {ok} passed, {fail} failed')
