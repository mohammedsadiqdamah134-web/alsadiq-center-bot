import os, sqlite3, secrets
from functools import wraps
from flask import Flask, request, redirect, url_for, session, render_template, jsonify, flash
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)
DB = os.environ.get('SHOP_DB_PATH', 'shop.db')
ADMIN_USER = os.environ.get('ADMIN_USER', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4.1-mini')
SHOP_NAME = os.environ.get('SHOP_NAME', 'الصادق سنتر')


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS products(
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT DEFAULT '',
          description TEXT DEFAULT '', price_north TEXT DEFAULT '', price_south TEXT DEFAULT '',
          sizes TEXT DEFAULT '', colors TEXT DEFAULT '', stock INTEGER DEFAULT 0,
          photo_url TEXT DEFAULT '', active INTEGER DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS orders(
          id INTEGER PRIMARY KEY AUTOINCREMENT, customer_name TEXT DEFAULT '', phone TEXT DEFAULT '',
          address TEXT DEFAULT '', product_id INTEGER, product_name TEXT DEFAULT '', size TEXT DEFAULT '',
          qty INTEGER DEFAULT 1, total TEXT DEFAULT '', status TEXT DEFAULT 'جديد',
          channel TEXT DEFAULT 'لوحة التحكم', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS conversations(
          id INTEGER PRIMARY KEY AUTOINCREMENT, customer TEXT DEFAULT '', channel TEXT DEFAULT '',
          message TEXT DEFAULT '', reply TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        ''')


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return fn(*a, **kw)
    return wrapper


@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        if not ADMIN_PASSWORD:
            flash('أضف ADMIN_PASSWORD في إعدادات الاستضافة أولاً.', 'error')
        elif request.form.get('username') == ADMIN_USER and secrets.compare_digest(request.form.get('password',''), ADMIN_PASSWORD):
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة.', 'error')
    return render_template('login.html', shop=SHOP_NAME)


@app.get('/logout')
def logout():
    session.clear(); return redirect(url_for('login'))


@app.get('/')
@login_required
def dashboard():
    with db() as c:
        products = c.execute('SELECT * FROM products ORDER BY id DESC').fetchall()
        orders = c.execute('SELECT * FROM orders ORDER BY id DESC LIMIT 12').fetchall()
        stats = {
          'products': c.execute('SELECT COUNT(*) FROM products WHERE active=1').fetchone()[0],
          'orders': c.execute("SELECT COUNT(*) FROM orders WHERE status NOT IN ('مكتمل','ملغي')").fetchone()[0],
          'new': c.execute("SELECT COUNT(*) FROM orders WHERE status='جديد'").fetchone()[0],
          'stock': c.execute('SELECT COALESCE(SUM(stock),0) FROM products WHERE active=1').fetchone()[0]
        }
    return render_template('dashboard.html', shop=SHOP_NAME, products=products, orders=orders, stats=stats)


@app.post('/products/add')
@login_required
def add_product():
    f=request.form
    with db() as c:
        c.execute('''INSERT INTO products(name,category,description,price_north,price_south,sizes,colors,stock,photo_url)
        VALUES(?,?,?,?,?,?,?,?,?)''',(f.get('name','').strip(),f.get('category',''),f.get('description',''),f.get('price_north',''),f.get('price_south',''),f.get('sizes',''),f.get('colors',''),int(f.get('stock') or 0),f.get('photo_url','')))
    flash('تمت إضافة المنتج.', 'success'); return redirect(url_for('dashboard')+'#products')


@app.post('/orders/<int:oid>/status')
@login_required
def order_status(oid):
    status=request.form.get('status','جديد')
    if status not in ['جديد','تم التأكيد','قيد التجهيز','تم الشحن','مكتمل','ملغي']:
        return 'Bad status',400
    with db() as c: c.execute('UPDATE orders SET status=? WHERE id=?',(status,oid))
    flash('تم تحديث حالة الطلب.', 'success'); return redirect(url_for('dashboard')+'#orders')


@app.post('/api/chat')
def chat():
    data=request.get_json(silent=True) or {}
    message=(data.get('message') or '').strip()
    if not message: return jsonify(error='اكتب رسالة أولاً'),400
    with db() as c:
        rows=c.execute('SELECT name,description,price_north,price_south,sizes,colors,stock FROM products WHERE active=1 ORDER BY id DESC LIMIT 60').fetchall()
    catalog='\n'.join([f"{r['name']} | الوصف:{r['description']} | شمالي:{r['price_north']} | جنوبي:{r['price_south']} | المقاسات:{r['sizes']} | الألوان:{r['colors']} | المخزون:{r['stock']}" for r in rows]) or 'لا توجد منتجات مسجلة.'
    if not OPENAI_API_KEY:
        answer='أهلاً بك في الصادق سنتر 🌟 وصلت رسالتك. حالياً الرد الذكي غير مفعّل، لكن يمكنك تصفح المنتجات أو ترك رقمك ليتواصل معك فريقنا.'
    else:
        try:
            from openai import OpenAI
            client=OpenAI(api_key=OPENAI_API_KEY)
            res=client.responses.create(model=OPENAI_MODEL, instructions=f'''أنت موظف مبيعات في {SHOP_NAME}. تحدث بالعربية اليمنية الودودة وباختصار. اعتمد فقط على بيانات الكتالوج ولا تخترع سعراً أو مقاساً أو كمية. لا تؤكد حجزاً ولا دفعاً. عند عدم وضوح المنتج اسأل سؤالاً واحداً. الكتالوج:\n{catalog}''', input=message, max_output_tokens=300)
            answer=res.output_text or 'وصلت رسالتك، وسيتواصل معك فريقنا.'
        except Exception:
            app.logger.exception('AI error'); answer='عذراً، الرد الذكي متوقف مؤقتاً. وصلت رسالتك وسنساعدك قريباً.'
    with db() as c: c.execute('INSERT INTO conversations(customer,channel,message,reply) VALUES(?,?,?,?)',(data.get('customer','زائر'),data.get('channel','تجربة اللوحة'),message,answer))
    return jsonify(reply=answer)


@app.get('/webhook')
def verify_meta():
    mode=request.args.get('hub.mode'); token=request.args.get('hub.verify_token'); challenge=request.args.get('hub.challenge')
    if mode=='subscribe' and token and secrets.compare_digest(token,os.environ.get('META_VERIFY_TOKEN','')): return challenge,200
    return 'Verification failed',403


@app.post('/webhook')
def meta_webhook():
    # استقبال Meta يحتاج إعداد Webhooks والصلاحيات والتوكنات من Meta Business.
    payload=request.get_json(silent=True) or {}
    app.logger.info('Meta webhook received object=%s',payload.get('object','unknown'))
    return 'EVENT_RECEIVED',200


@app.get('/health')
def health(): return {'service':'Al-Sadiq Center dashboard','status':'ok'}

init_db()
if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)))
