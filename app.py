import streamlit as st
import pandas as pd
import sqlite3, hashlib, secrets, re, os, io
from pathlib import Path
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime

APP_DIR=Path(__file__).resolve().parent
DB_PATH=APP_DIR/'gst_finder.db'
CSV_PATH=APP_DIR/'gst_master_database.csv'
DISCLAIMER='GST FINDER IS AN EDUCATIONAL TOOL, NOT AN OFFICIAL GOVERNMENT PLATFORM OR SUBSTITUTE FOR PROFESSIONAL TAX ADVICE. VERIFY ALL GST RATES, CLASSIFICATIONS AND VALUATION METHODS AGAINST CURRENT OFFICIAL NOTIFICATIONS BEFORE MAKING TAX OR BUSINESS DECISIONS.'

st.set_page_config(page_title='GST Finder',page_icon='🧾',layout='wide')
st.markdown('''<style>
.block-container{padding-top:1.4rem;max-width:1250px}.stApp{background:var(--background-color)}
[data-testid="stMetric"]{background:rgba(40,110,180,.07);padding:12px;border-radius:12px}
.main-title{font-size:2.15rem;font-weight:800;color:#1769aa}.subtle{color:var(--text-color);opacity:.75}
</style>''',unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def load_products():
    if not CSV_PATH.exists(): return pd.DataFrame(columns=['product_name','description','hsn_code','gst_rate','cgst','sgst','igst','cess','aliases','source','effective_date','verification_status'])
    df=pd.read_csv(CSV_PATH,dtype=str).fillna('')
    for c in ['product_name','description','hsn_code','gst_rate','cgst','sgst','igst','cess','aliases','source','effective_date','verification_status']:
        if c not in df: df[c]=''
    return df

def db():
    c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; return c

def init_db():
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, salt TEXT, password_hash TEXT, created_at TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY,user_id INTEGER,kind TEXT,query TEXT,result TEXT,created_at TEXT)')

def hash_password(password,salt):
    return hashlib.pbkdf2_hmac('sha256',password.encode(),salt,240000).hex()

def register_user(username,password):
    salt=secrets.token_hex(16); digest=hash_password(password,salt)
    try:
        with db() as c: c.execute('INSERT INTO users(username,salt,password_hash,created_at) VALUES(?,?,?,?)',(username.strip(),salt,digest,datetime.now().isoformat(timespec='seconds')))
        return True
    except sqlite3.IntegrityError: return False

def authenticate(username,password):
    with db() as c: row=c.execute('SELECT * FROM users WHERE lower(username)=lower(?)',(username.strip(),)).fetchone()
    return dict(row) if row and secrets.compare_digest(row['password_hash'],hash_password(password,row['salt'])) else None

def save_history(kind,query,result):
    if st.session_state.get('mode')!='registered': return
    with db() as c: c.execute('INSERT INTO history(user_id,kind,query,result,created_at) VALUES(?,?,?,?,?)',(st.session_state.user_id,kind,query,result,datetime.now().isoformat(timespec='seconds')))

def clean(s): return re.sub(r'\s+',' ',str(s or '')).strip().lower()
def hsn_digits(s): return re.sub(r'\D','',str(s or ''))

def search_products(query='',hsn=''):
    df=load_products(); q=clean(query); h=hsn_digits(hsn)
    if not q and not h: return df.iloc[0:0]
    scored=[]
    for ix,r in df.iterrows():
        name=clean(r.product_name); desc=clean(r.description); aliases=[clean(x) for x in str(r.aliases).split(';') if clean(x)]
        codes=re.findall(r'\d{2,8}',str(r.hsn_code)); hay=' '.join([name,desc,*aliases])
        score=0
        if q:
            if q==name: score+=200
            if q in name: score+=150
            if q in desc: score+=60
            if q in aliases: score+=180
            if any(q in a for a in aliases): score+=110
            toks=q.split()
            if toks and all(t in hay for t in toks): score+=75
        if h:
            if h in codes: score+=250
            elif any(code.startswith(h) or h.startswith(code) for code in codes): score+=100
            else: continue
        if score: scored.append((score,ix))
    scored.sort(key=lambda x:(-x[0],clean(df.loc[x[1],'product_name']),str(df.loc[x[1],'hsn_code'])))
    return df.loc[[i for _,i in scored]].drop_duplicates(subset=['product_name','hsn_code']).reset_index(drop=True)

def money(x):
    try: return Decimal(str(x)).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
    except (InvalidOperation,ValueError): raise ValueError('Enter a valid numeric amount.')

def show_product(r):
    st.markdown(f"#### {r.product_name}")
    st.write(r.description)
    a,b,c=st.columns(3)
    a.metric('HSN code',r.hsn_code or 'Not established')
    b.metric('GST rate',f"{r.gst_rate}%" if r.gst_rate else 'Not verified')
    c.metric('Cess',r.cess or 'Not specified')
    if 'HISTORICAL' in r.verification_status.upper() or 'UNVERIFIED' in r.verification_status.upper(): st.warning(r.verification_status+' — do not use as a current verified rate.')
    st.caption(f"Source: {r.source} | Effective date: {r.effective_date or 'Not established'}")

def auth_page():
    st.markdown('<div class="main-title">GST FINDER</div>',unsafe_allow_html=True)
    st.subheader('Welcome — sign in or continue as a guest')
    st.info('Guest searches and calculations are temporary and are not saved to history.')
    t1,t2=st.tabs(['Sign In','Register'])
    with t1:
        with st.form('login'):
            u=st.text_input('Username'); p=st.text_input('Password',type='password'); ok=st.form_submit_button('Sign In',use_container_width=True)
        if ok:
            user=authenticate(u,p)
            if user:
                st.session_state.mode='registered'; st.session_state.user_id=user['id']; st.session_state.username=user['username']; st.rerun()
            else: st.error('Incorrect username or password.')
    with t2:
        with st.form('register'):
            u2=st.text_input('Choose username'); p2=st.text_input('Create password',type='password'); p3=st.text_input('Confirm password',type='password'); reg=st.form_submit_button('Create Account',use_container_width=True)
        if reg:
            if len(u2.strip())<3 or len(p2)<8: st.error('Username must be at least 3 characters and password at least 8 characters.')
            elif p2!=p3: st.error('Passwords do not match.')
            elif register_user(u2,p2): st.success('Account created. Please sign in.')
            else: st.error('That username is already registered.')
    if st.button('Continue as Guest',type='primary',use_container_width=True): st.session_state.mode='guest'; st.session_state.username='Guest'; st.rerun()

def set_popular_search(item):
    # Callbacks run before Streamlit rebuilds widgets on the next rerun.
    st.session_state['product_query'] = item
    st.session_state['hsn_query'] = ''
    st.session_state.pop('product_dropdown', None)

def home_page():
    st.title('GST Rate Finder')
    st.caption('Start typing a product name or HSN code. Matching products appear below with their HSN codes.')
    q=st.text_input('Product name',placeholder='Try shampoo, toothpaste, milk, rice, mobile phone…',key='product_query')
    h=st.text_input('HSN code (optional)',placeholder='Enter HSN code if known',key='hsn_query')
    results=search_products(q,h) if q.strip() or h.strip() else load_products().iloc[0:0]
    selected=None
    if len(results):
        opts=[f"{r.product_name}  |  HSN {r.hsn_code or 'Not listed'}" for _,r in results.head(100).iterrows()]
        choice=st.selectbox('Matching products — select to automatically populate HSN',opts,index=None,placeholder='Choose a product…',key='product_dropdown')
        if choice:
            idx=opts.index(choice); selected=results.iloc[idx]
            st.success(f"Selected HSN code: {selected.hsn_code or 'Not established'}")
            show_product(selected)
        if not choice:
            st.markdown(f"**{len(results)} matching records**")
            for _,r in results.head(15).iterrows():
                with st.expander(f"{r.product_name}  |  HSN {r.hsn_code or 'Not listed'}"):
                    show_product(r)
    elif q.strip() or h.strip(): st.warning('No matching record in the loaded source database. Try a shorter name, an alternative name or HSN heading. This does not mean the product is exempt or has no GST entry.')
    if selected is not None: save_history('Product search',q or h, f"{selected.product_name} | HSN {selected.hsn_code}")
    st.divider(); st.subheader('Popular searches')
    popular=['Milk','Rice','Shampoo','Toothpaste','Soap','Detergent','Mobile phone','Laptop','Cement','Biscuits','Curd','Toothbrush']
    cols=st.columns(4)
    for i,item in enumerate(popular):
        cols[i%4].button(
            item,
            key='pop_'+str(i),
            use_container_width=True,
            on_click=set_popular_search,
            args=(item,)
        )

def calculator_page():
    st.title('GST Calculator')
    a,b=st.columns(2)
    amount=a.number_input('Amount (₹)',min_value=0.0,value=1000.0,step=100.0)
    rate=b.selectbox('GST rate', [0,0.1,0.25,1,1.5,3,5,6,12,18,28],index=8)
    inclusive=st.toggle('Amount is GST inclusive',value=False)
    interstate=st.toggle('Inter-state supply (IGST)',value=False)
    base=money(amount/(1+Decimal(str(rate))/100) if inclusive else amount)
    tax=money(base*Decimal(str(rate))/100); total=base+tax
    x,y,z=st.columns(3); x.metric('Taxable value',f'₹{base}'); y.metric('GST amount',f'₹{tax}'); z.metric('Total',f'₹{total}')
    if interstate: st.write(f'IGST: ₹{tax}')
    else: st.write(f'CGST: ₹{money(tax/2)}  |  SGST: ₹{money(tax/2)}')
    save_history('GST calculation',str(amount),f'Rate {rate}%; taxable {base}; tax {tax}; total {total}')

def valuation_page():
    st.title('GST Valuation Assistant')
    st.caption('Educational workflow based on Section 15 and valuation rules. Complex or uncertain cases require professional review.')
    price=st.number_input('Transaction price (₹)',min_value=0.0,value=1000.0)
    incidental=st.number_input('Add: incidental expenses / packing / commission (₹)',min_value=0.0,value=0.0)
    other=st.number_input('Add: other includible amounts (₹)',min_value=0.0,value=0.0)
    discount=st.number_input('Less: eligible invoice discount (₹)',min_value=0.0,value=0.0)
    if st.button('Calculate indicative taxable value'):
        taxable=money(Decimal(str(price))+Decimal(str(incidental))+Decimal(str(other))-Decimal(str(discount)))
        st.metric('Indicative taxable value',f'₹{taxable}')
        st.warning('Confirm eligibility of each inclusion/exclusion under Section 15 and the applicable valuation rule. This tool does not automatically determine related-party, agent, pure-agent or non-monetary valuation.')
        save_history('Valuation',str(price),str(taxable))

def bill_page():
    st.title('Bill Preview')
    customer=st.text_input('Customer label (optional)'); desc=st.text_input('Item description'); hsn=st.text_input('HSN code'); taxable=st.number_input('Taxable value (₹)',min_value=0.0); rate=st.number_input('GST rate (%)',min_value=0.0,max_value=100.0,value=18.0)
    igst=st.checkbox('Inter-state supply (IGST)')
    tax=money(Decimal(str(taxable))*Decimal(str(rate))/100); total=money(Decimal(str(taxable))+tax)
    lines=[('GST BILL PREVIEW — NOT NECESSARILY A TAX INVOICE'),f'Date: {datetime.now():%d-%m-%Y %H:%M}',f'Customer: {customer}',f'Item: {desc}',f'HSN: {hsn}',f'Taxable value: Rs. {money(taxable)}',f'GST rate: {rate}%',f'IGST: Rs. {tax}' if igst else f'CGST: Rs. {money(tax/2)} | SGST: Rs. {money(tax/2)}',f'Total: Rs. {total}',DISCLAIMER]
    content='\n'.join(lines)
    st.text(content)
    st.download_button('Download TXT',content,file_name='gst_bill_preview.txt',mime='text/plain')
    try:
        from docx import Document
        d=Document(); [d.add_paragraph(x) for x in lines]; b=io.BytesIO(); d.save(b); st.download_button('Download DOCX',b.getvalue(),file_name='gst_bill_preview.docx')
    except Exception: st.caption('DOCX export unavailable: install python-docx.')
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        b=io.BytesIO(); c=canvas.Canvas(b,pagesize=A4); y=800
        for line in lines:
            c.drawString(40,y,line[:110]); y-=22
            if y<60: c.showPage(); y=800
        c.save(); st.download_button('Download PDF',b.getvalue(),file_name='gst_bill_preview.pdf',mime='application/pdf')
    except Exception: st.caption('PDF export unavailable: install reportlab.')

def info_page():
    st.title('Information & Data Sources')
    st.warning(DISCLAIMER)
    st.markdown('''- HSN is the Harmonized System of Nomenclature used to classify goods.
- CGST and SGST generally apply to intra-state supplies; IGST generally applies to inter-state supplies.
- Taxable value is ordinarily determined under Section 15, subject to statutory inclusions, exclusions and valuation rules.
- The bundled CSV is based primarily on the CBIC goods schedule supplied with this project, which is labelled **01-04-2023**. It is historical and is not a live or complete current rate database.
- Product aliases are search aids only. Exact HSN classification can depend on ingredients, composition, use, packaging and legal notes.
''')
    df=load_products(); st.metric('Rows in bundled product source',len(df))
    st.download_button('Download master product CSV',CSV_PATH.read_bytes(),file_name='gst_master_database.csv',mime='text/csv')

def history_page():
    st.title('Search & Calculation History')
    if st.session_state.mode!='registered': st.info('Guest history is not stored. Sign in with a registered account to view saved history.'); return
    with db() as c: rows=c.execute('SELECT id,kind,query,result,created_at FROM history WHERE user_id=? ORDER BY id DESC LIMIT 500',(st.session_state.user_id,)).fetchall()
    if not rows: st.info('No history yet.'); return
    st.dataframe(pd.DataFrame([dict(r) for r in rows]),use_container_width=True,hide_index=True)
    if st.button('Delete my history'):
        with db() as c: c.execute('DELETE FROM history WHERE user_id=?',(st.session_state.user_id,))
        st.success('History deleted.'); st.rerun()

def main():
    init_db()
    if 'mode' not in st.session_state:
        auth_page(); return
    st.sidebar.title('GST FINDER')
    st.sidebar.caption(f"Access: {st.session_state.get('username','Guest')}")
    page=st.sidebar.radio('Navigation',['Home','GST Calculator','GST Valuation','Bill Preview','History','INFO'])
    if st.sidebar.button('Sign out / Exit'):
        for k in ['mode','user_id','username','product_query','hsn_query','product_dropdown']: st.session_state.pop(k,None)
        st.rerun()
    {'Home':home_page,'GST Calculator':calculator_page,'GST Valuation':valuation_page,'Bill Preview':bill_page,'History':history_page,'INFO':info_page}[page]()
    st.divider(); st.caption(DISCLAIMER)

main()

