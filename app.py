from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, jsonify, abort)
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import date, timedelta, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
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
#  SC&WMS — Enterprise Supply Chain & Warehouse Management
#  Enterprise Logistics & Multi-Warehouse Operations Platform
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
#  SECURITY & AUTHENTICATION HELPERS
# ─────────────────────────────────────────────────────────────
_user_table_checked = False
def ensure_user_columns():
    global _user_table_checked
    if _user_table_checked:
        return
    try:
        db_exec("""
            ALTER TABLE Users ADD COLUMN IF NOT EXISTS email VARCHAR(120);
            ALTER TABLE Users ADD COLUMN IF NOT EXISTS full_name VARCHAR(100);
            ALTER TABLE Users ADD COLUMN IF NOT EXISTS phone VARCHAR(30);
            ALTER TABLE Users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT TRUE;
            ALTER TABLE Users ADD COLUMN IF NOT EXISTS otp_code VARCHAR(10);
            ALTER TABLE Users ADD COLUMN IF NOT EXISTS otp_expiry TIMESTAMP;
            UPDATE Users SET email = 'admin@scwms.com', email_verified = TRUE
            WHERE LOWER(Username) = 'admin' AND (email IS NULL OR email = '');
            UPDATE Users SET Role = 'Admin' WHERE Role = 'Viewer' OR Role IS NULL;
        """)
        _user_table_checked = True
    except Exception:
        pass

def send_otp_email(to_email, otp_code, purpose="Verification"):
    smtp_host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    smtp_user = os.environ.get('SMTP_USER') or os.environ.get('MAIL_USERNAME')
    smtp_pass = os.environ.get('SMTP_PASS') or os.environ.get('MAIL_PASSWORD')

    if smtp_user and smtp_pass:
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"SC&WMS Security Code: {otp_code}"
            msg['From'] = f"SC&WMS Security <{smtp_user}>"
            msg['To'] = to_email

            plain_text = f"Your SC&WMS one-time verification code is: {otp_code}. Valid for 10 minutes."
            html_text = f"""
            <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:480px;margin:20px auto;padding:24px;background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;">
              <h2 style="color:#0f172a;margin-top:0;font-size:20px;">SC&amp;WMS Platform</h2>
              <p style="color:#475569;font-size:14px;line-height:1.5;">Your one-time verification code for <strong>{purpose}</strong> is:</p>
              <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:16px;text-align:center;margin:20px 0;">
                <span style="font-size:32px;font-weight:bold;letter-spacing:8px;color:#1e40af;font-family:monospace;">{otp_code}</span>
              </div>
              <p style="color:#64748b;font-size:12px;line-height:1.4;">Valid for 10 minutes. If you did not make this request, please ignore.</p>
            </div>
            """
            msg.attach(MIMEText(plain_text, 'plain'))
            msg.attach(MIMEText(html_text, 'html'))

            with smtplib.SMTP(smtp_host, smtp_port, timeout=8) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, [to_email], msg.as_string())
            return True, "Email sent successfully"
        except Exception as e:
            return False, f"SMTP error: {e}"
    return False, "SMTP not configured"

# ─────────────────────────────────────────────────────────────
#  AUTH (LOGIN, REGISTER, OTP VERIFY, RESET)
# ─────────────────────────────────────────────────────────────
@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    ensure_user_columns()
    if request.method == 'POST':
        login_id = (request.form.get('email') or request.form.get('username') or '').strip()
        password = request.form.get('password', '').strip()
        try:
            rows = db_fetch("""
                SELECT * FROM Users
                WHERE LOWER(COALESCE(Email, '')) = LOWER(%s)
                   OR LOWER(Username) = LOWER(%s)
            """, (login_id, login_id))

            if rows and check_password_hash(rows[0]['password'], password):
                u = rows[0]
                if u.get('email_verified') is False and u.get('email'):
                    otp = f"{secrets.randbelow(900000) + 100000}"
                    otp_expiry = datetime.utcnow() + timedelta(minutes=10)
                    db_exec("UPDATE Users SET otp_code=%s, otp_expiry=%s WHERE User_ID=%s",
                            (otp, otp_expiry, u['user_id']))
                    sent, _ = send_otp_email(u['email'], otp, "Account Activation")
                    if sent:
                        flash('Please verify your email. A verification code was sent to your inbox.', 'warning')
                    else:
                        flash(f'Please verify your email. Code: {otp} (Demo Mode active)', 'warning')
                    return redirect(url_for('verify_otp', email=u['email']))

                session.clear()
                session['user'] = u['username']
                session['role'] = u.get('role', 'Viewer')
                session['email'] = u.get('email') or ''
                session.permanent = True
                return redirect(url_for('dashboard'))

            flash('Invalid email or password.', 'error')
        except ConnectionError as e:
            flash(str(e), 'error')
        except Exception as e:
            flash(f'Sign in error: {e}', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    ensure_user_columns()
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not email or '@' not in email:
            flash('Please enter a valid email address.', 'error')
            return render_template('register.html')
        if not username or len(username) < 3:
            flash('Username must be at least 3 characters long.', 'error')
            return render_template('register.html')
        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
            return render_template('register.html')
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('register.html')

        try:
            exists = db_fetch("""
                SELECT Username, Email FROM Users
                WHERE LOWER(Username) = LOWER(%s) OR LOWER(COALESCE(Email, '')) = LOWER(%s)
            """, (username, email))

            if exists:
                if exists[0]['username'].lower() == username.lower():
                    flash('Username is already taken. Please choose another.', 'error')
                else:
                    flash('An account with this email already exists.', 'error')
                return render_template('register.html')

            otp = f"{secrets.randbelow(900000) + 100000}"
            otp_expiry = datetime.utcnow() + timedelta(minutes=10)
            pwd_hash = generate_password_hash(password)

            role = request.form.get('role', 'Admin').strip()
            if role not in ('Admin', 'Manager', 'Viewer'):
                role = 'Admin'

            db_exec("""
                INSERT INTO Users (Username, Password, Role, email, full_name, email_verified, otp_code, otp_expiry)
                VALUES (%s, %s, %s, %s, %s, FALSE, %s, %s)
            """, (username, pwd_hash, role, email, full_name, otp, otp_expiry))

            sent, msg = send_otp_email(email, otp, "Account Registration")
            if sent:
                flash(f'Verification OTP sent to {email}.', 'info')
            else:
                flash(f'Verification code: {otp} (Demo Mode active — configure SMTP in Vercel to email directly)', 'warning')

            return redirect(url_for('verify_otp', email=email))

        except Exception as e:
            flash(f'Registration error: {e}', 'error')

    return render_template('register.html')

@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    email = request.args.get('email', '') or request.form.get('email', '')
    email = email.strip().lower()
    ensure_user_columns()

    if request.method == 'POST':
        otp = request.form.get('otp', '').strip()
        if not otp or len(otp) != 6:
            flash('Please enter the 6-digit verification code.', 'error')
            return render_template('verify_otp.html', email=email)

        try:
            rows = db_fetch("""
                SELECT * FROM Users WHERE LOWER(COALESCE(Email, '')) = LOWER(%s)
            """, (email,))

            if not rows:
                flash('User account not found.', 'error')
                return redirect(url_for('register'))

            user = rows[0]
            if user.get('otp_code') == otp:
                expiry = user.get('otp_expiry')
                if expiry and isinstance(expiry, datetime) and expiry < datetime.utcnow():
                    flash('OTP has expired. Please click "Resend OTP".', 'error')
                    return render_template('verify_otp.html', email=email)

                db_exec("""
                    UPDATE Users SET email_verified = TRUE, otp_code = NULL, otp_expiry = NULL
                    WHERE LOWER(COALESCE(Email, '')) = LOWER(%s)
                """, (email,))

                flash('Email verified successfully! You can now sign in.', 'success')
                return redirect(url_for('login'))
            else:
                flash('Invalid verification code. Please try again.', 'error')
        except Exception as e:
            flash(f'Verification error: {e}', 'error')

    return render_template('verify_otp.html', email=email)

@app.route('/resend-otp', methods=['POST'])
def resend_otp():
    email = request.form.get('email', '').strip().lower()
    ensure_user_columns()
    if not email:
        flash('Email address is missing.', 'error')
        return redirect(url_for('register'))

    try:
        rows = db_fetch("SELECT * FROM Users WHERE LOWER(COALESCE(Email, '')) = LOWER(%s)", (email,))
        if not rows:
            flash('Account not found.', 'error')
            return redirect(url_for('register'))

        otp = f"{secrets.randbelow(900000) + 100000}"
        otp_expiry = datetime.utcnow() + timedelta(minutes=10)

        db_exec("""
            UPDATE Users SET otp_code = %s, otp_expiry = %s
            WHERE LOWER(COALESCE(Email, '')) = LOWER(%s)
        """, (otp, otp_expiry, email))

        sent, msg = send_otp_email(email, otp, "OTP Resend")
        if sent:
            flash(f'A fresh OTP has been sent to {email}.', 'info')
        else:
            flash(f'New OTP: {otp} (Demo Mode active)', 'warning')

    except Exception as e:
        flash(f'Error resending OTP: {e}', 'error')

    return redirect(url_for('verify_otp', email=email))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if not email:
            flash('Please enter your email address.', 'error')
            return render_template('forgot_password.html')

        ensure_user_columns()
        try:
            rows = db_fetch("SELECT * FROM Users WHERE LOWER(COALESCE(Email, '')) = LOWER(%s)", (email,))
            if rows:
                otp = f"{secrets.randbelow(900000) + 100000}"
                otp_expiry = datetime.utcnow() + timedelta(minutes=15)
                db_exec("UPDATE Users SET otp_code = %s, otp_expiry = %s WHERE LOWER(COALESCE(Email, '')) = LOWER(%s)",
                        (otp, otp_expiry, email))
                sent, _ = send_otp_email(email, otp, "Password Reset")
                if sent:
                    flash(f'Password reset instructions sent to {email}.', 'info')
                else:
                    flash(f'Password Reset Code: {otp} (Demo Mode active)', 'warning')
            else:
                flash(f'If an account exists for {email}, instructions have been sent.', 'info')
        except Exception as e:
            flash(f'Error: {e}', 'error')

        return redirect(url_for('login'))

    return render_template('forgot_password.html')

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

    # Shipment status counts
    status_rows = db_fetch('SELECT Status, COUNT(*) AS c FROM Orders GROUP BY Status')
    shipment_counts = {r['status']: r['c'] for r in status_rows}

    # Transit shipments for pipeline display
    try:
        transit_shipments = db_fetch("""
            SELECT s.Shipment_ID, COALESCE(w.Location, 'Central Hub') AS origin,
                   COALESCE(c.Address, 'Customer Site') AS destination
            FROM Shipment s
            JOIN Orders o ON s.Order_ID = o.Order_ID
            LEFT JOIN Warehouse w ON s.Origin_Warehouse_ID = w.Warehouse_ID
            LEFT JOIN Customer c ON o.Customer_ID = c.Customer_ID
            WHERE s.Status = 'In Transit'
            ORDER BY s.Shipment_ID DESC LIMIT 5
        """)
    except Exception:
        transit_shipments = []

    return render_template('dashboard.html', stats=stats,
                           recent_orders=recent_orders,
                           low_stock=low_stock,
                           shipment_counts=shipment_counts,
                           transit_shipments=transit_shipments,
                           map_data=map_payload(active_only=True))

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

@app.route('/suppliers/edit/<int:sid>', methods=['POST'])
@login_required
@role_required('Admin', 'Manager')
def edit_supplier(sid):
    try:
        db_exec(
            'UPDATE Supplier SET Name=%s, Contact=%s, Email=%s, Address=%s WHERE Supplier_ID=%s',
            (request.form['name'], request.form['contact'],
             request.form['email'], request.form['address'], sid))
        flash('Supplier updated successfully.', 'success')
    except Exception as e:
        flash(f'Error updating supplier: {e}', 'error')
    return redirect(url_for('suppliers'))

@app.route('/suppliers/delete/<int:sid>', methods=['POST', 'GET'])
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

@app.route('/products/edit/<int:pid>', methods=['POST'])
@login_required
@role_required('Admin', 'Manager')
def edit_product(pid):
    try:
        db_exec(
            'UPDATE Product SET Product_Name=%s, Category=%s, Price=%s, Supplier_ID=%s WHERE Product_ID=%s',
            (request.form['product_name'], request.form['category'],
             request.form['price'], request.form['supplier_id'], pid))
        flash('Product updated successfully.', 'success')
    except Exception as e:
        flash(f'Error updating product: {e}', 'error')
    return redirect(url_for('products'))

@app.route('/products/delete/<int:pid>', methods=['POST', 'GET'])
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

@app.route('/warehouses/edit/<int:wid>', methods=['POST'])
@login_required
@role_required('Admin', 'Manager')
def edit_warehouse(wid):
    try:
        hit = geo.resolve(request.form['location'])
        db_exec('UPDATE Warehouse SET Location=%s, Latitude=%s, Longitude=%s WHERE Warehouse_ID=%s',
                (request.form['location'], hit[0] if hit else None, hit[1] if hit else None, wid))
        flash('Warehouse updated successfully.', 'success')
    except Exception as e:
        flash(f'Error updating warehouse: {e}', 'error')
    return redirect(url_for('warehouses'))

@app.route('/warehouses/delete/<int:wid>', methods=['POST', 'GET'])
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

@app.route('/stock/set', methods=['POST'])
@login_required
@role_required('Admin', 'Manager')
def set_stock():
    """Directly set a stock quantity (edit in-place)."""
    try:
        db_exec('''
            UPDATE Stock SET Quantity=%s
            WHERE Product_ID=%s AND Warehouse_ID=%s
        ''', (request.form['quantity'], request.form['product_id'], request.form['warehouse_id']))
        flash('Stock quantity updated.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('stock'))

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

@app.route('/customers/edit/<int:cid>', methods=['POST'])
@login_required
@role_required('Admin', 'Manager')
def edit_customer(cid):
    try:
        hit = geo.resolve(request.form.get('address', ''))
        db_exec(
            'UPDATE Customer SET Name=%s, Phone=%s, Email=%s, Address=%s, Latitude=%s, Longitude=%s WHERE Customer_ID=%s',
            (request.form['name'], request.form['phone'], request.form['email'], request.form['address'],
             hit[0] if hit else None, hit[1] if hit else None, cid))
        flash('Customer updated successfully.', 'success')
    except Exception as e:
        flash(f'Error updating customer: {e}', 'error')
    return redirect(url_for('customers'))

@app.route('/customers/delete/<int:cid>', methods=['POST', 'GET'])
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

@app.route('/orders/edit/<int:oid>', methods=['POST'])
@login_required
@role_required('Admin', 'Manager')
def edit_order(oid):
    try:
        db_exec(
            'UPDATE Orders SET Customer_ID=%s, Product_ID=%s, Quantity=%s, Status=%s WHERE Order_ID=%s',
            (request.form['customer_id'], request.form['product_id'],
             request.form['quantity'], request.form['status'], oid))
        flash('Order updated successfully.', 'success')
    except Exception as e:
        flash(f'Error updating order: {e}', 'error')
    return redirect(url_for('orders'))

@app.route('/orders/delete/<int:oid>', methods=['POST', 'GET'])
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
#  AI DEBUG  (admin only — checks if key works)
# ─────────────────────────────────────────────────────────────
@app.route('/api/ai/ping')
def api_ai_ping():
    if 'user' not in session or session.get('role') != 'Admin':
        return jsonify(ok=False, error='Admin only'), 403
    import requests as _req
    key = config.GEMINI_API_KEY
    if not key:
        return jsonify(ok=False, configured=False, error='GEMINI_API_KEY not set in environment variables.')
    try:
        for api_ver in ('v1', 'v1beta'):
            url  = f'https://generativelanguage.googleapis.com/{api_ver}/models/gemini-pro:generateContent?key={key}'
            body = {'contents':[{'role':'user','parts':[{'text':'Reply with just: OK'}]}],
                    'generationConfig':{'maxOutputTokens':5}}
            r = _req.post(url, json=body, timeout=8,
                          headers={'Content-Type': 'application/json'})
            if r.status_code == 200:
                return jsonify(ok=True, model=f'gemini-pro ({api_ver})', message='AI is working!')
        try: err = r.json().get('error',{}).get('message', r.text[:300])
        except: err = r.text[:300]
        return jsonify(ok=False, configured=True, status=r.status_code, error=err)
    except Exception as e:
        return jsonify(ok=False, configured=True, error=str(e))

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
#  LIVE DASHBOARD API  (called by Chart.js every 30 seconds)
# ─────────────────────────────────────────────────────────────
@app.route('/api/dashboard/live')
def api_dashboard_live():
    if 'user' not in session:
        return jsonify(ok=False), 401
    stats = {
        'suppliers':  db_fetch('SELECT COUNT(*) AS c FROM Supplier')[0]['c'],
        'products':   db_fetch('SELECT COUNT(*) AS c FROM Product')[0]['c'],
        'orders':     db_fetch('SELECT COUNT(*) AS c FROM Orders')[0]['c'],
        'shipments':  db_fetch('SELECT COUNT(*) AS c FROM Shipment')[0]['c'],
        'low_stock':  db_fetch('SELECT COUNT(*) AS c FROM Low_Stock_Alert')[0]['c'],
        'pending':    db_fetch("SELECT COUNT(*) AS c FROM Orders WHERE Status='Pending'")[0]['c'],
        'in_transit': db_fetch("SELECT COUNT(*) AS c FROM Shipment WHERE Status='In Transit'")[0]['c'],
    }
    # order status distribution
    status = db_fetch('SELECT Status, COUNT(*) AS cnt FROM Orders GROUP BY Status')
    # revenue by category
    cat = db_fetch('''
        SELECT p.Category, COALESCE(SUM(o.Quantity*p.Price),0) AS revenue
        FROM Orders o JOIN Product p ON o.Product_ID=p.Product_ID
        GROUP BY p.Category ORDER BY revenue DESC
    ''')
    # warehouse stock
    wh = db_fetch('''
        SELECT w.Location, COALESCE(SUM(s.Quantity),0) AS qty
        FROM Warehouse w LEFT JOIN Stock s ON s.Warehouse_ID=w.Warehouse_ID
        GROUP BY w.Location ORDER BY qty DESC
    ''')
    return jsonify(ok=True, stats=stats,
                   status=[{'s': r['status'], 'c': r['cnt']} for r in status],
                   cat=[{'l': r['category'], 'v': float(r['revenue'])} for r in cat],
                   wh=[{'l': r['location'], 'v': int(r['qty'])} for r in wh])

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
