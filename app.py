from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, jsonify, abort)
from werkzeug.security import check_password_hash
from datetime import date, timedelta
from functools import wraps
import hmac
import math
import os
import secrets
import time

import ai_assistant
import config
import geo
from config import get_db

# ─────────────────────────────────────────────────────────────
#  Supply Chain & Warehouse Management System
#  Student:    Mubashira Zainab | BS Mathematics 5th Semester
#  University: CASPAM, BZU Multan
#  Course:     DBMS (COMP351) | Supervisor: Dr. Imran Javaid
# ─────────────────────────────────────────────────────────────

# static files live in public/static so Vercel's CDN can serve them directly
app = Flask(__name__, static_folder='public/static', static_url_path='/static')
app.secret_key = config.SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=bool(os.environ.get('VERCEL')),   # HTTPS-only cookie in production
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)

# ─────────────────────────────────────────────────────────────
#  DATABASE HELPERS
# ─────────────────────────────────────────────────────────────
def db_fetch(query, params=None):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute(query, params or ())
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    cur.close()
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

def db_exec(query, params=None):
    conn = get_db()
    cur  = conn.cursor()
    try:
        cur.execute(query, params or ())
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise exc
    finally:
        cur.close()
        conn.close()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    """Admin = everything · Manager = add/update · Viewer = read-only."""
    def deco(f):
        @wraps(f)
        def inner(*args, **kwargs):
            if session.get('role') not in roles:
                flash('Your account is read-only for this action.', 'error')
                return redirect(request.referrer or url_for('dashboard'))
            return f(*args, **kwargs)
        return inner
    return deco

# ─────────────────────────────────────────────────────────────
#  SECURITY: CSRF protection + response headers
# ─────────────────────────────────────────────────────────────
def csrf_token():
    if '_csrf' not in session:
        session['_csrf'] = secrets.token_hex(16)
    return session['_csrf']

app.jinja_env.globals['csrf_token'] = csrf_token

@app.before_request
def _csrf_protect():
    if request.method == 'POST':
        sent = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token', '')
        expected = session.get('_csrf', '')
        # an empty token must never match (empty == empty would bypass the check)
        if not sent or not expected or not hmac.compare_digest(sent, expected):
            if request.path.startswith('/api/'):
                return jsonify(ok=False, error='Session expired — refresh the page.'), 400
            return render_template('error.html', code=400,
                                   message='Security check failed. Please go back and try again.'), 400

@app.after_request
def _security_headers(resp):
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'SAMEORIGIN'
    resp.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return resp

# ─────────────────────────────────────────────────────────────
#  ERROR HANDLERS
# ─────────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', code=404,
                           message='Page not found.'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', code=500,
                           message='Internal server error.'), 500

# ─────────────────────────────────────────────────────────────
#  AUTH
# ─────────────────────────────────────────────────────────────
@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        try:
            rows = db_fetch('SELECT * FROM Users WHERE Username=%s', (username,))
            if rows and check_password_hash(rows[0]['password'], password):
                session.clear()
                session['user'] = rows[0]['username']
                session['role'] = rows[0]['role']
                session.permanent = True
                return redirect(url_for('dashboard'))
            flash('Invalid credentials.', 'error')
        except ConnectionError as e:
            flash(str(e), 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ─────────────────────────────────────────────────────────────
#  DASHBOARD
# ─────────────────────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    stats = {
        'suppliers':  db_fetch('SELECT COUNT(*) AS c FROM Supplier')[0]['c'],
        'products':   db_fetch('SELECT COUNT(*) AS c FROM Product')[0]['c'],
        'warehouses': db_fetch('SELECT COUNT(*) AS c FROM Warehouse')[0]['c'],
        'customers':  db_fetch('SELECT COUNT(*) AS c FROM Customer')[0]['c'],
        'orders':     db_fetch('SELECT COUNT(*) AS c FROM Orders')[0]['c'],
        'shipments':  db_fetch('SELECT COUNT(*) AS c FROM Shipment')[0]['c'],
        'low_stock':  db_fetch('SELECT COUNT(*) AS c FROM Low_Stock_Alert')[0]['c'],
        'pending':    db_fetch("SELECT COUNT(*) AS c FROM Orders WHERE Status='Pending'")[0]['c'],
        'in_transit': db_fetch("SELECT COUNT(*) AS c FROM Shipment WHERE Status='In Transit'")[0]['c'],
    }
    recent_orders = db_fetch(
        'SELECT * FROM Order_Summary ORDER BY Order_ID DESC LIMIT 5')
    low_stock = db_fetch('SELECT * FROM Low_Stock_Alert LIMIT 5')
    return render_template('dashboard.html', stats=stats,
                           recent_orders=recent_orders,
                           low_stock=low_stock, map_data=map_payload(active_only=True))

# ─────────────────────────────────────────────────────────────
#  SUPPLIERS
# ─────────────────────────────────────────────────────────────
@app.route('/suppliers')
@login_required
def suppliers():
    rows = db_fetch('SELECT * FROM Supplier ORDER BY Supplier_ID')
    return render_template('suppliers.html', suppliers=rows)

@app.route('/suppliers/add', methods=['POST'])
@login_required
@role_required('Admin', 'Manager')
def add_supplier():
    try:
        db_exec(
            'INSERT INTO Supplier (Name,Contact,Email,Address) VALUES (%s,%s,%s,%s)',
            (request.form['name'], request.form['contact'],
             request.form['email'], request.form['address']))
        flash('Supplier added successfully.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('suppliers'))

@app.route('/suppliers/delete/<int:sid>', methods=['POST'])
@login_required
@role_required('Admin')
def delete_supplier(sid):
    try:
        db_exec('DELETE FROM Supplier WHERE Supplier_ID=%s', (sid,))
        flash('Supplier deleted.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('suppliers'))

# ─────────────────────────────────────────────────────────────
#  PRODUCTS
# ─────────────────────────────────────────────────────────────
@app.route('/products')
@login_required
def products():
    rows      = db_fetch('SELECT * FROM Product_Supplier_Detail ORDER BY Product_ID')
    suppliers = db_fetch('SELECT Supplier_ID, Name FROM Supplier ORDER BY Name')
    return render_template('products.html', products=rows, suppliers=suppliers)

@app.route('/products/add', methods=['POST'])
@login_required
@role_required('Admin', 'Manager')
def add_product():
    try:
        db_exec(
            'INSERT INTO Product (Product_Name,Category,Price,Supplier_ID) VALUES (%s,%s,%s,%s)',
            (request.form['product_name'], request.form['category'],
             request.form['price'],        request.form['supplier_id']))
        flash('Product added successfully.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('products'))

@app.route('/products/delete/<int:pid>', methods=['POST'])
@login_required
@role_required('Admin')
def delete_product(pid):
    try:
        db_exec('DELETE FROM Product WHERE Product_ID=%s', (pid,))
        flash('Product deleted.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('products'))

# ─────────────────────────────────────────────────────────────
#  WAREHOUSES
# ─────────────────────────────────────────────────────────────
@app.route('/warehouses')
@login_required
def warehouses():
    rows = db_fetch('SELECT * FROM Warehouse ORDER BY Warehouse_ID')
    return render_template('warehouses.html', warehouses=rows)

@app.route('/warehouses/add', methods=['POST'])
@login_required
@role_required('Admin', 'Manager')
def add_warehouse():
    try:
        hit = geo.resolve(request.form['location'])
        db_exec('INSERT INTO Warehouse (Location, Latitude, Longitude) VALUES (%s,%s,%s)',
                (request.form['location'], hit[0] if hit else None, hit[1] if hit else None))
        flash('Warehouse added.' if hit else
              'Warehouse added. (City not recognised, so it will not appear on the tracking map.)', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('warehouses'))

@app.route('/warehouses/delete/<int:wid>', methods=['POST'])
@login_required
@role_required('Admin')
def delete_warehouse(wid):
    try:
        db_exec('DELETE FROM Warehouse WHERE Warehouse_ID=%s', (wid,))
        flash('Warehouse deleted.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('warehouses'))

# ─────────────────────────────────────────────────────────────
#  STOCK / INVENTORY
# ─────────────────────────────────────────────────────────────
@app.route('/stock')
@login_required
def stock():
    rows       = db_fetch('SELECT * FROM Warehouse_Inventory')
    products   = db_fetch('SELECT Product_ID, Product_Name FROM Product ORDER BY Product_Name')
    warehouses = db_fetch('SELECT Warehouse_ID, Location FROM Warehouse ORDER BY Location')
    return render_template('stock.html', stock=rows,
                           products=products, warehouses=warehouses)

@app.route('/stock/add', methods=['POST'])
@login_required
@role_required('Admin', 'Manager')
def add_stock():
    try:
        db_exec('''
            INSERT INTO Stock (Product_ID, Warehouse_ID, Quantity)
            VALUES (%s, %s, %s)
            ON CONFLICT (Product_ID, Warehouse_ID)
            DO UPDATE SET Quantity = Stock.Quantity + EXCLUDED.Quantity
        ''', (request.form['product_id'], request.form['warehouse_id'],
              request.form['quantity']))
        flash('Stock updated successfully.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('stock'))

# ─────────────────────────────────────────────────────────────
#  CUSTOMERS
# ─────────────────────────────────────────────────────────────
@app.route('/customers')
@login_required
def customers():
    rows = db_fetch('SELECT * FROM Customer ORDER BY Customer_ID')
    return render_template('customers.html', customers=rows)

@app.route('/customers/add', methods=['POST'])
@login_required
@role_required('Admin', 'Manager')
def add_customer():
    try:
        db_exec(
            'INSERT INTO Customer (Name,Phone,Email,Address,Latitude,Longitude) VALUES (%s,%s,%s,%s,%s,%s)',
            (request.form['name'], request.form['phone'], request.form['email'], request.form['address'],
             *(geo.resolve(request.form['address'])[:2] if geo.resolve(request.form['address']) else (None, None))))
        flash('Customer added.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('customers'))

@app.route('/customers/delete/<int:cid>', methods=['POST'])
@login_required
@role_required('Admin')
def delete_customer(cid):
    try:
        db_exec('DELETE FROM Customer WHERE Customer_ID=%s', (cid,))
        flash('Customer deleted.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('customers'))

# ─────────────────────────────────────────────────────────────
#  ORDERS
# ─────────────────────────────────────────────────────────────
@app.route('/orders')
@login_required
def orders():
    rows      = db_fetch('SELECT * FROM Order_Summary ORDER BY Order_ID DESC')
    customers = db_fetch('SELECT Customer_ID, Name FROM Customer ORDER BY Name')
    products  = db_fetch('SELECT Product_ID, Product_Name, Price FROM Product ORDER BY Product_Name')
    return render_template('orders.html', orders=rows,
                           customers=customers, products=products,
                           today=date.today().isoformat())

@app.route('/orders/add', methods=['POST'])
@login_required
@role_required('Admin', 'Manager')
def add_order():
    try:
        db_exec(
            'INSERT INTO Orders (Customer_ID,Product_ID,Quantity,Order_Date) VALUES (%s,%s,%s,%s)',
            (request.form['customer_id'], request.form['product_id'],
             request.form['quantity'],    request.form['order_date']))
        flash('Order placed. Stock updated automatically via trigger.', 'success')
    except Exception as e:
        flash(f'Order failed: {e}', 'error')
    return redirect(url_for('orders'))

@app.route('/orders/status/<int:oid>', methods=['POST'])
@login_required
@role_required('Admin', 'Manager')
def update_order_status(oid):
    try:
        db_exec('UPDATE Orders SET Status=%s WHERE Order_ID=%s',
                (request.form['status'], oid))
        flash('Order status updated.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('orders'))

@app.route('/orders/delete/<int:oid>', methods=['POST'])
@login_required
@role_required('Admin')
def delete_order(oid):
    try:
        db_exec('DELETE FROM Orders WHERE Order_ID=%s', (oid,))
        flash('Order deleted.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('orders'))

# ─────────────────────────────────────────────────────────────
#  SHIPMENTS & LIVE MAP TRACKING
# ─────────────────────────────────────────────────────────────
AVG_KM_PER_DAY = 450      # average truck distance per day — used for the delivery estimate (ETA)

def _f(v):
    return float(v) if v is not None else None

def _pt(lat, lng):
    return [_f(lat), _f(lng)] if lat is not None and lng is not None else None

def map_payload(active_only=False):
    """Data for the overview map (dashboard + shipments page)."""
    where = "WHERE Shipment_Status = 'In Transit'" if active_only else ''
    rows = db_fetch(f'SELECT * FROM Shipment_Tracking_Detail {where} ORDER BY Shipment_ID DESC')
    whs = db_fetch('SELECT Location, Latitude, Longitude FROM Warehouse WHERE Latitude IS NOT NULL')
    return {
        'warehouses': [{'name': w['location'], 'p': _pt(w['latitude'], w['longitude'])} for w in whs],
        'shipments': [{
            'id': r['shipment_id'], 'tracking': r['tracking_no'], 'customer': r['customer_name'],
            'product': r['product_name'], 'qty': r['quantity'], 'status': r['shipment_status'],
            'origin': _pt(r['origin_lat'], r['origin_lng']), 'dest': _pt(r['dest_lat'], r['dest_lng']),
            'current': _pt(r['last_lat'], r['last_lng']), 'last': r['last_location'],
            'url': url_for('track_shipment', sid=r['shipment_id']),
        } for r in rows],
    }

def tracking_payload(sid):
    """Everything the tracking page / live API needs for one shipment."""
    rows = db_fetch('SELECT * FROM Shipment_Tracking_Detail WHERE Shipment_ID=%s', (sid,))
    if not rows:
        return None
    r = rows[0]
    events = db_fetch('''SELECT Event_Type, Location_Name, Latitude, Longitude, Note, Event_Time
                         FROM Shipment_Tracking WHERE Shipment_ID=%s
                         ORDER BY Event_Time, Event_ID''', (sid,))
    origin, dest = _pt(r['origin_lat'], r['origin_lng']), _pt(r['dest_lat'], r['dest_lng'])
    evs = [{'type': e['event_type'], 'location': e['location_name'],
            'p': _pt(e['latitude'], e['longitude']), 'note': e['note'],
            'time': e['event_time'].strftime('%d %b %Y, %H:%M')} for e in events]
    located = [e for e in evs if e['p']]
    current = located[-1]['p'] if located else origin
    status = r['shipment_status']

    total = geo.haversine_km(*origin, *dest) if origin and dest else None
    done = geo.haversine_km(*origin, *current) if origin and current else 0
    if status == 'Delivered':
        progress = 100
    elif total:
        progress = int(min(done / total, 0.99) * 100)
    else:
        progress = 0
    remaining = max(0.0, total - done) if total and status == 'In Transit' else 0
    eta = None
    if status == 'In Transit':
        eta = (date.today() + timedelta(days=max(1, math.ceil(remaining / AVG_KM_PER_DAY)))).strftime('%d %b %Y')

    return {
        'id': sid, 'tracking_no': r['tracking_no'], 'carrier': r['carrier'], 'status': status,
        'order_id': r['order_id'], 'customer': r['customer_name'], 'address': r['customer_address'],
        'product': r['product_name'], 'qty': r['quantity'],
        'shipped': r['shipment_date'].strftime('%d %b %Y'),
        'origin': origin, 'origin_name': r['origin_warehouse'], 'dest': dest, 'current': current,
        'events': evs, 'progress': progress,
        'distance_km': round(total) if total else None, 'remaining_km': round(remaining), 'eta': eta,
    }

def _add_event(sid, etype, location, p, note):
    db_exec('''INSERT INTO Shipment_Tracking
               (Shipment_ID, Event_Type, Location_Name, Latitude, Longitude, Note)
               VALUES (%s,%s,%s,%s,%s,%s)''',
            (sid, etype, location, p[0] if p else None, p[1] if p else None, note))

@app.route('/shipments')
@login_required
def shipments():
    rows = db_fetch('SELECT * FROM Shipment_Tracking_Detail ORDER BY Shipment_ID DESC')
    return render_template('shipments.html', shipments=rows, map_data=map_payload())

@app.route('/shipments/<int:sid>/track')
@login_required
def track_shipment(sid):
    data = tracking_payload(sid)
    if not data:
        abort(404)
    return render_template('track.html', t=data, cities=sorted(geo.CITIES))

@app.route('/api/shipments/<int:sid>/tracking')
def api_tracking(sid):
    if 'user' not in session:
        return jsonify(ok=False, error='Please log in.'), 401
    data = tracking_payload(sid)
    if not data:
        return jsonify(ok=False, error='Shipment not found.'), 404
    return jsonify(ok=True, t=data)

@app.route('/shipments/update/<int:sid>', methods=['POST'])
@login_required
@role_required('Admin', 'Manager')
def update_shipment(sid):
    try:
        db_exec('UPDATE Shipment SET Status=%s WHERE Shipment_ID=%s',
                (request.form['status'], sid))
        flash('Shipment status updated. Tracking event logged automatically.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(request.referrer or url_for('shipments'))

@app.route('/shipments/<int:sid>/checkpoint', methods=['POST'])
@login_required
@role_required('Admin', 'Manager')
def add_checkpoint(sid):
    """Record a carrier scan (manual checkpoint) on the shipment."""
    city = request.form.get('city', '')
    etype = request.form.get('event_type', 'In Transit')
    if city not in geo.CITIES or etype not in ('In Transit', 'Out for Delivery', 'Delayed'):
        flash('Please choose a valid city and event type.', 'error')
        return redirect(url_for('track_shipment', sid=sid))
    try:
        _add_event(sid, etype, f'{city} Transit Hub', list(geo.CITIES[city]),
                   request.form.get('note', '').strip()[:200] or 'Checkpoint scan')
        flash(f'Checkpoint added at {city}.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('track_shipment', sid=sid))

@app.route('/shipments/<int:sid>/simulate', methods=['POST'])
@login_required
@role_required('Admin', 'Manager')
def simulate_checkpoint(sid):
    """Demo helper: move the shipment to its next hub along the route (…→ Out for Delivery → Delivered)."""
    t = tracking_payload(sid)
    if not t:
        abort(404)
    if t['status'] != 'In Transit':
        flash('This shipment is already closed.', 'error')
        return redirect(url_for('track_shipment', sid=sid))
    try:
        origin, dest = t['origin'], t['dest']
        last_type = t['events'][-1]['type'] if t['events'] else ''
        total = t['distance_km'] or 0
        steps = [25, 50, 75, 90] if total >= 120 else []
        nxt = next((x for x in steps if x > t['progress'] + 5), None) if last_type != 'Out for Delivery' else None
        if nxt and origin and dest:
            names = [e['location'] for e in t['events']] + [t['origin_name'] or '', t['address'] or '']
            used = {h[2] for h in map(geo.resolve, names) if h}
            lat, lng = geo.interpolate(origin, dest, nxt / 100)
            city, _ = geo.nearest_city(lat, lng, exclude=used)
            _add_event(sid, 'In Transit', f'{city} Transit Hub', list(geo.CITIES[city]), 'Scanned at sorting hub')
            flash(f'Shipment reached {city} Transit Hub.', 'success')
        elif last_type != 'Out for Delivery':
            _add_event(sid, 'Out for Delivery', 'Local delivery station', dest, 'Out for delivery')
            flash('Shipment is out for delivery.', 'success')
        else:
            db_exec("UPDATE Shipment SET Status='Delivered' WHERE Shipment_ID=%s", (sid,))
            flash('Shipment delivered. The order was marked Delivered automatically (trigger).', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('track_shipment', sid=sid))

# ─────────────────────────────────────────────────────────────
#  AI ASSISTANT  (keys stay on the server — see ai_assistant.py)
# ─────────────────────────────────────────────────────────────
AI_LIMIT_PER_HOUR = 40     # protects the free API quota

@app.route('/assistant')
@login_required
def assistant():
    return render_template('assistant.html', ai=ai_assistant.status())

@app.route('/api/assistant', methods=['POST'])
def api_assistant():
    if 'user' not in session:
        return jsonify(ok=False, error='Please log in.'), 401
    now = time.time()
    calls = [c for c in session.get('ai_calls', []) if now - c < 3600]
    if len(calls) >= AI_LIMIT_PER_HOUR:
        return jsonify(ok=False, error='Hourly question limit reached. Please try again later.'), 429
    session['ai_calls'] = calls + [now]
    data = request.get_json(silent=True) or {}
    return jsonify(ai_assistant.ask(data.get('question'), data.get('history')))

# ─────────────────────────────────────────────────────────────
#  REPORTS  (full SQL portfolio — 11 query types)
# ─────────────────────────────────────────────────────────────
@app.route('/reports')
@login_required
def reports():
    data = {
        'selection':     db_fetch('SELECT * FROM Product WHERE Price > 1000 ORDER BY Price DESC'),
        'projection':    db_fetch('SELECT Product_Name, Category, Price FROM Product ORDER BY Price DESC'),
        'join':          db_fetch('SELECT * FROM Product_Supplier_Detail'),
        'aggregation':   db_fetch('SELECT Category, COUNT(*) AS Total, ROUND(AVG(Price),2) AS Avg_Price FROM Product GROUP BY Category ORDER BY Avg_Price DESC'),
        'having':        db_fetch('''
            SELECT w.Location, SUM(s.Quantity) AS Total_Stock
            FROM   Stock s JOIN Warehouse w ON s.Warehouse_ID = w.Warehouse_ID
            GROUP  BY w.Location HAVING SUM(s.Quantity) > 50
            ORDER  BY Total_Stock DESC
        '''),
        'subquery':      db_fetch('''
            SELECT Product_Name, Category, Price FROM Product
            WHERE  Product_ID NOT IN (SELECT DISTINCT Product_ID FROM Orders)
        '''),
        'low_stock':     db_fetch('SELECT * FROM Low_Stock_Alert'),
        'reorder':       db_fetch('SELECT * FROM Reorder_Alert'),
        'order_summary': db_fetch('SELECT * FROM Order_Summary ORDER BY Order_ID DESC'),
        'supplier_perf': db_fetch('SELECT * FROM Supplier_Product_Summary'),
        'division':      db_fetch('''
            SELECT DISTINCT w.Warehouse_ID, w.Location
            FROM   Stock s
            JOIN   Warehouse w ON s.Warehouse_ID = w.Warehouse_ID
            WHERE  NOT EXISTS (
                SELECT p.Product_ID FROM Product p WHERE p.Supplier_ID = 1
                AND NOT EXISTS (
                    SELECT 1 FROM Stock s2
                    WHERE  s2.Warehouse_ID = s.Warehouse_ID
                    AND    s2.Product_ID   = p.Product_ID
                )
            )
        '''),
        'function_demo': db_fetch('''
            SELECT p.Product_Name, w.Location,
                   get_stock(s.Product_ID, s.Warehouse_ID) AS Current_Stock
            FROM   Stock s
            JOIN   Product   p ON s.Product_ID   = p.Product_ID
            JOIN   Warehouse w ON s.Warehouse_ID = w.Warehouse_ID
            ORDER  BY Current_Stock DESC
        '''),
    }
    return render_template('reports.html', **data)

# ─────────────────────────────────────────────────────────────
#  BUSINESS INTELLIGENCE DASHBOARD
# ─────────────────────────────────────────────────────────────
@app.route('/analytics')
@login_required
def analytics():
    # KPI summary
    kpi_rows = db_fetch('''
        SELECT
            COUNT(*)                                           AS total_orders,
            COALESCE(SUM(o.Quantity * p.Price), 0)            AS total_revenue,
            COALESCE(ROUND(AVG(o.Quantity * p.Price), 0), 0)  AS avg_order_value,
            COALESCE(
              ROUND(
                100.0 * COUNT(*) FILTER (WHERE o.Status = 'Delivered') / NULLIF(COUNT(*), 0),
                1
              ), 0
            )                                                  AS fulfilment_rate
        FROM Orders o
        JOIN Product p ON o.Product_ID = p.Product_ID
    ''')
    kpi = kpi_rows[0] if kpi_rows else {}
    kpi['in_transit'] = db_fetch("SELECT COUNT(*) AS c FROM Shipment WHERE Status='In Transit'")[0]['c']

    # Order trend — last 30 days
    trend = db_fetch('''
        SELECT TO_CHAR(Order_Date,'MM-DD') AS day, COUNT(*) AS cnt
        FROM Orders
        WHERE Order_Date >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY Order_Date
        ORDER BY Order_Date
    ''')

    # Order status distribution
    status_data = db_fetch('''
        SELECT Status, COUNT(*) AS cnt
        FROM Orders
        GROUP BY Status
        ORDER BY cnt DESC
    ''')

    # Revenue by product category
    category_data = db_fetch('''
        SELECT p.Category AS category,
               COALESCE(SUM(o.Quantity * p.Price), 0) AS revenue
        FROM   Orders o
        JOIN   Product p ON o.Product_ID = p.Product_ID
        GROUP  BY p.Category
        ORDER  BY revenue DESC
    ''')

    # Stock by warehouse
    warehouse_stock = db_fetch('''
        SELECT w.Location AS location, COALESCE(SUM(s.Quantity), 0) AS qty
        FROM   Warehouse w
        LEFT   JOIN Stock s ON s.Warehouse_ID = w.Warehouse_ID
        GROUP  BY w.Location
        ORDER  BY qty DESC
    ''')

    # Top products by revenue
    raw_top = db_fetch('''
        SELECT p.Product_Name, p.Category,
               COUNT(o.Order_ID)       AS order_count,
               SUM(o.Quantity)         AS units_sold,
               SUM(o.Quantity*p.Price) AS revenue
        FROM   Orders o
        JOIN   Product p ON o.Product_ID = p.Product_ID
        GROUP  BY p.Product_ID, p.Product_Name, p.Category
        ORDER  BY revenue DESC
        LIMIT  10
    ''')
    top_products = list(enumerate(raw_top, 1))

    # Supplier performance
    supplier_perf = db_fetch('SELECT * FROM Supplier_Product_Summary')

    return render_template(
        'analytics.html',
        kpi=kpi,
        trend_data=[{'day': r['day'], 'cnt': r['cnt']} for r in trend],
        status_data=[{'status': r['status'], 'cnt': r['cnt']} for r in status_data],
        category_data=[{'category': r['category'], 'revenue': float(r['revenue'])} for r in category_data],
        warehouse_stock=[{'location': r['location'], 'qty': int(r['qty'])} for r in warehouse_stock],
        top_products=top_products,
        supplier_perf=supplier_perf,
    )

# ─────────────────────────────────────────────────────────────
#  INVENTORY LEDGER
# ─────────────────────────────────────────────────────────────
@app.route('/ledger')
@login_required
def ledger():
    rows = db_fetch('''
        SELECT it.Trans_ID, p.Product_Name, w.Location,
               it.Trans_Type, it.Quantity, it.Trans_Date,
               it.Reference_No, it.Notes
        FROM   Inventory_Transaction it
        JOIN   Product   p ON it.Product_ID   = p.Product_ID
        JOIN   Warehouse w ON it.Warehouse_ID = w.Warehouse_ID
        ORDER  BY it.Trans_Date DESC
    ''')
    return render_template('ledger.html', transactions=rows)

# ─────────────────────────────────────────────────────────────
#  REORDER ALERTS
# ─────────────────────────────────────────────────────────────
@app.route('/reorder')
@login_required
def reorder():
    rows = db_fetch('SELECT * FROM Reorder_Alert')
    return render_template('reorder.html', alerts=rows)

# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG', '0') == '1', host='0.0.0.0', port=5000)
