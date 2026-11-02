import os, sqlite3, secrets, io, uuid
from pathlib import Path
from contextlib import contextmanager
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from PIL import Image, UnidentifiedImageError

ROOT = Path('/data')
ROOT.mkdir(parents=True, exist_ok=True)
UPLOADS = ROOT / 'uploads'
UPLOADS.mkdir(exist_ok=True)
DB = ROOT / 'site.db'
SECRET = os.environ.get('APP_SECRET', '')
ADMIN_USER = os.environ.get('ADMIN_USER', '')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')
if not all((SECRET, ADMIN_USER, ADMIN_PASSWORD)):
    raise RuntimeError('Set APP_SECRET, ADMIN_USER and ADMIN_PASSWORD')
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SessionMiddleware, secret_key=SECRET, https_only=os.environ.get('HTTPS_ONLY','true').lower()=='true', same_site='lax', max_age=86400)
templates = Jinja2Templates(directory='templates')
app.mount("/static", StaticFiles(directory="static"), name="static")

@contextmanager
def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()

with db() as con:
    con.execute('CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY AUTOINCREMENT, title_ar TEXT NOT NULL, title_en TEXT NOT NULL, description_ar TEXT NOT NULL, description_en TEXT NOT NULL, category TEXT NOT NULL, image TEXT NOT NULL DEFAULT "", link TEXT NOT NULL DEFAULT "", featured INTEGER NOT NULL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
    con.execute('CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
    con.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    if not con.execute('SELECT COUNT(*) FROM projects').fetchone()[0]:
        con.executemany('INSERT INTO projects (title_ar,title_en,description_ar,description_en,category,featured) VALUES (?,?,?,?,?,?)', [
            ('مساعد الصيدلي الذكي','Smart Pharmacy Agent','مساعد ذكي يعتمد على RAG وربط المخزون في الوقت الحقيقي.','AI assistant using RAG and live inventory integration.','AI / RAG',1),
            ('منصة أتمتة المؤسسات','Organization Automation Platform','حلول رقمية لتنظيم العمليات وإدارة البيانات.','Digital workflows for operations and data management.','Automation',1),
            ('نظام استرجاع المعرفة','Multi-Tenant RAG API','واجهة API لفصل بيانات المؤسسات واسترجاع المعرفة.','Multi-tenant API for isolated knowledge retrieval.','API / AI',0)
        ])

DEFAULT_SETTINGS = {
    'hero_ar': 'أحوّل الأفكار إلى تجارب رقمية استثنائية.',
    'hero_en': 'Turning ideas into extraordinary digital experiences.',
    'intro_ar': 'أصمّم وأطوّر حلول أتمتة ذكية تربط الأنظمة والبيانات والذكاء الاصطناعي في تجربة واحدة، سريعة وقابلة للتوسع.',
    'intro_en': 'I design intelligent automation systems connecting data, workflows and AI in seamless, scalable digital experiences.',
    'about_ar': 'متخصص في تطوير أنظمة الأتمتة وتطبيقات الذكاء الاصطناعي، مع اهتمام ببناء حلول عملية، واجهات واضحة، وبنية تقنية موثوقة.',
    'about_en': 'I specialize in AI automation and intelligent applications, building reliable systems, intuitive interfaces and practical solutions.',
    'email': '', 'github': '', 'linkedin': ''
}

def settings():
    with db() as con:
        data = dict(DEFAULT_SETTINGS)
        data.update({r['key']: r['value'] for r in con.execute('SELECT key,value FROM settings')})
        return data

def projects():
    with db() as con:
        return [dict(x) for x in con.execute('SELECT * FROM projects ORDER BY featured DESC,id DESC')]

def admin(request):
    return request.session.get('admin') is True

def csrf(request, token):
    if not token or not secrets.compare_digest(str(token), str(request.session.get('csrf',''))):
        raise HTTPException(403, 'Invalid form token')

def page(request, name, **kwargs):
    if 'csrf' not in request.session:
        request.session['csrf'] = secrets.token_urlsafe(32)
    return templates.TemplateResponse(request, name, {'request':request,'csrf':request.session['csrf'], **kwargs})

@app.get('/health')
def health(): return {'status':'ok'}

@app.get('/')
def home(request:Request):
    return page(request,'index.html',projects=projects(),settings=settings())

@app.get('/media/{filename}')
def media(filename:str):
    if filename != Path(filename).name or not filename.endswith('.webp'):
        raise HTTPException(404)
    path = UPLOADS / filename
    if not path.is_file(): raise HTTPException(404)
    return FileResponse(path,media_type='image/webp')

@app.get('/admin/login')
def login_page(request:Request):
    if admin(request): return RedirectResponse('/admin',303)
    return page(request,'login.html',error=False)

@app.post('/admin/login')
def login(request:Request,username:str=Form(...),password:str=Form(...),token:str=Form(...)):
    csrf(request,token)
    if not (secrets.compare_digest(username,ADMIN_USER) and secrets.compare_digest(password,ADMIN_PASSWORD)):
        return page(request,'login.html',error=True)
    request.session.clear()
    request.session['admin']=True
    request.session['csrf']=secrets.token_urlsafe(32)
    return RedirectResponse('/admin',303)

@app.post('/admin/logout')
def logout(request:Request,token:str=Form(...)):
    csrf(request,token)
    request.session.clear()
    return RedirectResponse('/admin/login',303)

@app.get('/admin')
def dashboard(request:Request):
    if not admin(request): return RedirectResponse('/admin/login',303)
    with db() as con:
        messages=[dict(x) for x in con.execute('SELECT * FROM messages ORDER BY id DESC LIMIT 30')]
    return page(request,'admin.html',projects=projects(),messages=messages,settings=settings())

async def save_image(image: UploadFile | None) -> str:
    """Validate and convert an uploaded image to persistent WebP storage."""
    if not image or not image.filename:
        return ''
    raw = await image.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(413, 'Image too large (maximum 5 MB)')
    try:
        im = Image.open(io.BytesIO(raw))
        if im.format not in ('JPEG','PNG','WEBP'): raise ValueError('Unsupported format')
        im.verify()
        im = Image.open(io.BytesIO(raw))
        im.load()
        if im.width * im.height > 20_000_000:
            raise ValueError('Too many pixels')
        im.thumbnail((1800, 1200))
        if im.mode not in ('RGB', 'RGBA'):
            im = im.convert('RGB')
        filename = uuid.uuid4().hex + '.webp'
        im.save(UPLOADS / filename, 'WEBP', quality=85)
        return filename
    except (UnidentifiedImageError, ValueError, OSError, Image.DecompressionBombError):
        raise HTTPException(400, 'Invalid image')

@app.post('/admin/projects')
async def create_project(request:Request,token:str=Form(...),title_ar:str=Form(...),title_en:str=Form(...),description_ar:str=Form(...),description_en:str=Form(...),category:str=Form('Automation'),link:str=Form(''),featured:str=Form(''),image:UploadFile|None=File(None)):
    if not admin(request): raise HTTPException(403)
    csrf(request,token)
    if any(len(x)>3000 for x in (title_ar,title_en,description_ar,description_en,category,link)): raise HTTPException(400)
    if link and not (link.startswith('https://') or link.startswith('http://')): raise HTTPException(400,'Invalid link')
    filename = await save_image(image)
    with db() as con:
        con.execute('INSERT INTO projects(title_ar,title_en,description_ar,description_en,category,image,link,featured) VALUES (?,?,?,?,?,?,?,?)',(title_ar,title_en,description_ar,description_en,category,filename,link,int(featured=='yes')))
    return RedirectResponse('/admin#projects',303)

@app.post('/admin/projects/{project_id}/delete')
def delete_project(project_id:int,request:Request,token:str=Form(...)):
    if not admin(request): raise HTTPException(403)
    csrf(request,token)
    with db() as con:
        con.execute('DELETE FROM projects WHERE id=?',(project_id,))
    return RedirectResponse('/admin#projects',303)

@app.post('/admin/projects/{project_id}/update')
async def update_project(project_id:int,request:Request,token:str=Form(...),title_ar:str=Form(...),title_en:str=Form(...),description_ar:str=Form(...),description_en:str=Form(...),category:str=Form(...),link:str=Form(''),featured:str=Form(''),image:UploadFile|None=File(None)):
    if not admin(request): raise HTTPException(403)
    csrf(request,token)
    if any(len(x)>3000 for x in (title_ar,title_en,description_ar,description_en,category,link)): raise HTTPException(400)
    if link and not (link.startswith('https://') or link.startswith('http://')): raise HTTPException(400)
    filename = await save_image(image)
    with db() as con:
        old = con.execute('SELECT image FROM projects WHERE id=?',(project_id,)).fetchone()
        if not old:
            if filename: (UPLOADS / filename).unlink(missing_ok=True)
            raise HTTPException(404, 'Project not found')
        if filename:
            con.execute('UPDATE projects SET title_ar=?,title_en=?,description_ar=?,description_en=?,category=?,link=?,featured=?,image=? WHERE id=?',(title_ar,title_en,description_ar,description_en,category,link,int(featured=='yes'),filename,project_id))
        else:
            con.execute('UPDATE projects SET title_ar=?,title_en=?,description_ar=?,description_en=?,category=?,link=?,featured=? WHERE id=?',(title_ar,title_en,description_ar,description_en,category,link,int(featured=='yes'),project_id))
    return RedirectResponse('/admin#projects',303)

@app.post('/contact')
def contact(request:Request,token:str=Form(...),name:str=Form(...),email:str=Form(...),message:str=Form(...)):
    csrf(request,token)
    if not (1<=len(name)<=100 and 3<=len(email)<=200 and 1<=len(message)<=3000): raise HTTPException(400)
    with db() as con: con.execute('INSERT INTO messages(name,email,message) VALUES(?,?,?)',(name,email,message))
    return RedirectResponse('/?sent=1#contact',303)

@app.post('/admin/settings')
def update_settings(request:Request,token:str=Form(...),hero_ar:str=Form(''),hero_en:str=Form(''),intro_ar:str=Form(''),intro_en:str=Form(''),about_ar:str=Form(''),about_en:str=Form(''),email:str=Form(''),github:str=Form(''),linkedin:str=Form('')):
    if not admin(request): raise HTTPException(403)
    csrf(request,token)
    values=locals()
    with db() as con:
        for key in DEFAULT_SETTINGS:
            val=values[key].strip()
            if len(val)>3000: raise HTTPException(400,'Text too long')
            if key in ('github','linkedin') and val and not val.startswith('https://'): raise HTTPException(400,'Use HTTPS links')
            con.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,val))
    return RedirectResponse('/admin#settings',303)

@app.post('/admin/messages/{message_id}/delete')
def delete_message(message_id:int,request:Request,token:str=Form(...)):
    if not admin(request): raise HTTPException(403)
    csrf(request,token)
    with db() as con: con.execute('DELETE FROM messages WHERE id=?',(message_id,))
    return RedirectResponse('/admin#messages',303)

@app.post('/admin/projects/{project_id}/remove-image')
def remove_image(project_id:int,request:Request,token:str=Form(...)):
    if not admin(request): raise HTTPException(403)
    csrf(request,token)
    with db() as con: con.execute("UPDATE projects SET image='' WHERE id=?",(project_id,))
    return RedirectResponse('/admin#projects',303)

@app.get('/robots.txt')
def robots():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse('User-agent: *\nDisallow: /admin\nAllow: /\n')
