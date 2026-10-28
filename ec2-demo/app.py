"""TaskFlow EC2 teaching demo. Python 3.10+, standard library only."""
import argparse
import csv
import hmac
import io
import json
import os
import secrets
import sqlite3
import threading
import time
import webbrowser
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get('DATABASE_PATH', ROOT / 'data' / 'tasks.db'))
PASSWORD = os.environ.get('DEMO_PASSWORD', 'demo2026')
MODE = os.environ.get('APP_ENV', 'local')
SESSIONS = {}
ATTEMPTS = {}
LOCK = threading.Lock()
STATUSES = ('todo', 'doing', 'done')
PRIORITIES = ('low', 'medium', 'high')


@contextmanager
def connect():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, owner TEXT NOT NULL, priority TEXT NOT NULL, status TEXT NOT NULL, due TEXT NOT NULL, created_at TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        if not db.execute("SELECT 1 FROM settings WHERE key='seeded'").fetchone():
            sample = [('Tìm hiểu các thành phần của EC2', 'Minh', 'high', 'done', 0), ('Thiết kế giao diện quản lý công việc', 'Linh', 'medium', 'done', 1), ('Cài đặt ứng dụng trên máy chủ', 'An', 'high', 'doing', 2), ('Cấu hình Security Group', 'Minh', 'high', 'doing', 2), ('Kiểm tra dữ liệu sau khi khởi động lại', 'Linh', 'medium', 'todo', 3), ('Chuẩn bị phần trình diễn', 'An', 'low', 'todo', 4)]
            now = datetime.now(timezone.utc).isoformat()
            db.executemany('INSERT INTO tasks(title,owner,priority,status,due,created_at) VALUES(?,?,?,?,?,?)', [(t,o,p,s,(date.today()+timedelta(days=d)).isoformat(),now) for t,o,p,s,d in sample])
            db.execute("INSERT INTO settings VALUES('seeded','1')")


class Handler(BaseHTTPRequestHandler):
    server_version = 'TaskFlow/1.0'

    def send(self, status, body, content_type='application/json; charset=utf-8', headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        elif isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def authenticated(self):
        try:
            cookie = SimpleCookie(self.headers.get('Cookie', ''))
            token = cookie['taskflow_session'].value if 'taskflow_session' in cookie else ''
        except Exception:
            return False
        with LOCK:
            expiry = SESSIONS.get(token, 0)
            if expiry <= time.time():
                SESSIONS.pop(token, None)
                return False
        return True

    def body_json(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 8192:
                raise ValueError('Kích thước yêu cầu không hợp lệ')
            if self.headers.get_content_type() != 'application/json':
                raise ValueError('Yêu cầu phải dùng JSON')
            payload = json.loads(self.rfile.read(length).decode('utf-8'))
            if not isinstance(payload, dict):
                raise ValueError('JSON phải là một đối tượng')
            return payload
        except (ValueError, UnicodeError) as exc:
            raise ValueError('Dữ liệu yêu cầu không hợp lệ') from exc

    def same_origin(self):
        # A custom header plus no CORS blocks cross-site browser mutations.
        return self.headers.get('X-TaskFlow-Request') == '1'

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == '/health':
            try:
                with connect() as db:
                    db.execute('SELECT 1').fetchone()
                return self.send(200, {'ok': True, 'service': 'taskflow', 'mode': MODE})
            except sqlite3.Error:
                return self.send(503, {'ok': False})
        files = {'/': ('index.html','text/html; charset=utf-8'), '/style.css': ('style.css','text/css; charset=utf-8'), '/app.js': ('app.js','text/javascript; charset=utf-8')}
        if url.path in files:
            name, mime = files[url.path]
            return self.send(200, (ROOT/'web'/name).read_bytes(), mime)
        if url.path == '/api/session':
            return self.send(200, {'authenticated': self.authenticated(), 'mode': MODE})
        if url.path.startswith('/api/') and not self.authenticated():
            return self.send(401, {'error': 'Vui lòng đăng nhập'})
        if url.path in ('/api/tasks', '/api/export'):
            q = parse_qs(url.query)
            clauses, values = [], []
            for field in ('status', 'priority'):
                if q.get(field, [''])[0]:
                    clauses.append(field+' = ?')
                    values.append(q[field][0])
            term = q.get('q', [''])[0][:200]
            if term:
                clauses.append('(instr(lower(title),lower(?)) > 0 OR instr(lower(owner),lower(?)) > 0)')
                values.extend([term,term])
            sql = 'SELECT * FROM tasks'+ (' WHERE '+' AND '.join(clauses) if clauses else '')+' ORDER BY id DESC'
            with connect() as db:
                tasks = [dict(row) for row in db.execute(sql, values)]
                summary = dict(db.execute('SELECT status, COUNT(*) FROM tasks GROUP BY status').fetchall())
            if url.path == '/api/export':
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(['ID','Công việc','Người phụ trách','Ưu tiên','Trạng thái','Hạn hoàn thành'])
                def safe(value):
                    value = str(value)
                    return "'"+value if value.lstrip().startswith(('=', '+', '-', '@')) else value
                for task in tasks:
                    writer.writerow([safe(task[k]) for k in ('id','title','owner','priority','status','due')])
                return self.send(200, ('\ufeff'+output.getvalue()).encode('utf-8'), 'text/csv; charset=utf-8', {'Content-Disposition':'attachment; filename="taskflow.csv"'})
            return self.send(200, {'tasks':tasks, 'summary':{s:summary.get(s,0) for s in STATUSES}})
        return self.send(404, {'error':'Không tìm thấy đường dẫn'})

    def do_POST(self):
        self.mutate('POST')

    def do_PATCH(self):
        self.mutate('PATCH')

    def do_DELETE(self):
        self.mutate('DELETE')

    def mutate(self, method):
        path = urlsplit(self.path).path
        if not self.same_origin():
            return self.send(403, {'error':'Thiếu xác nhận yêu cầu từ ứng dụng'})
        if path == '/api/login' and method == 'POST':
            try:
                body = self.body_json()
            except ValueError as exc:
                return self.send(400, {'error':str(exc)})
            address = self.client_address[0]
            now = time.time()
            with LOCK:
                recent = [t for t in ATTEMPTS.get(address, []) if t > now-60]
                ATTEMPTS[address] = recent
                if len(recent) >= 10:
                    return self.send(429, {'error':'Thử lại sau một phút'})
                if not hmac.compare_digest(str(body.get('password','')).encode(), PASSWORD.encode()):
                    ATTEMPTS[address].append(now)
                    return self.send(401, {'error':'Mã truy cập chưa đúng'})
                ATTEMPTS.pop(address, None)
                token = secrets.token_urlsafe(32)
                for key in [k for k,v in SESSIONS.items() if v <= now]:
                    del SESSIONS[key]
                SESSIONS[token] = now+8*3600
            secure = '; Secure' if os.environ.get('COOKIE_SECURE') == '1' else ''
            return self.send(200, {'ok':True}, headers={'Set-Cookie':f'taskflow_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800{secure}'})
        if not self.authenticated():
            return self.send(401, {'error':'Vui lòng đăng nhập'})
        if path == '/api/logout' and method == 'POST':
            cookie = SimpleCookie(self.headers.get('Cookie',''))
            if 'taskflow_session' in cookie:
                with LOCK:
                    SESSIONS.pop(cookie['taskflow_session'].value, None)
            return self.send(200, {'ok':True}, headers={'Set-Cookie':'taskflow_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
        try:
            if path == '/api/tasks' and method == 'POST':
                body = self.validate(self.body_json())
                with connect() as db:
                    cur = db.execute('INSERT INTO tasks(title,owner,priority,status,due,created_at) VALUES(?,?,?,?,?,?)', [body[k] for k in ('title','owner','priority','status','due')]+[datetime.now(timezone.utc).isoformat()])
                    task_id = cur.lastrowid
                return self.send(201, {'id':task_id})
            parts = path.strip('/').split('/')
            if len(parts) == 3 and parts[:2] == ['api','tasks'] and parts[2].isdigit():
                task_id = int(parts[2])
                with connect() as db:
                    current = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
                    if current is None:
                        return self.send(404, {'error':'Công việc không tồn tại'})
                    if method == 'DELETE':
                        db.execute('DELETE FROM tasks WHERE id=?', (task_id,))
                        db.commit()
                        return self.send(200, {'ok':True})
                    if method == 'PATCH':
                        updates = self.body_json()
                        if not updates or any(k not in ('title','owner','priority','status','due') for k in updates):
                            raise ValueError('Trường cập nhật không hợp lệ')
                        body = self.validate({**dict(current), **updates})
                        db.execute('UPDATE tasks SET title=?,owner=?,priority=?,status=?,due=? WHERE id=?', [body[k] for k in ('title','owner','priority','status','due')]+[task_id])
                        db.commit()
                        return self.send(200, {'ok':True})
        except ValueError as exc:
            return self.send(400, {'error':str(exc)})
        except sqlite3.Error:
            return self.send(503, {'error':'Cơ sở dữ liệu tạm thời chưa sẵn sàng'})
        return self.send(404, {'error':'Không tìm thấy đường dẫn'})

    @staticmethod
    def validate(body):
        output = {}
        for field, maximum in (('title',140),('owner',60)):
            value = body.get(field,'')
            if not isinstance(value,str) or not value.strip() or len(value.strip()) > maximum:
                raise ValueError(f'{"Tên công việc" if field=="title" else "Người phụ trách"} cần từ 1 đến {maximum} ký tự')
            output[field] = value.strip()
        output['status'] = body.get('status','todo')
        output['priority'] = body.get('priority','medium')
        if output['status'] not in STATUSES or output['priority'] not in PRIORITIES:
            raise ValueError('Trạng thái hoặc ưu tiên không hợp lệ')
        try:
            output['due'] = date.fromisoformat(body.get('due','')).isoformat()
        except (ValueError,TypeError):
            raise ValueError('Hạn hoàn thành phải là ngày hợp lệ')
        return output


def main():
    parser = argparse.ArgumentParser(description='TaskFlow EC2 demo')
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8080)
    parser.add_argument('--open-browser',action='store_true')
    args = parser.parse_args()
    if MODE != 'local' and (PASSWORD == 'demo2026' or len(PASSWORD)<12):
        parser.error('EC2 requires DEMO_PASSWORD with at least 12 characters, different from the local password')
    init_db()
    server = ThreadingHTTPServer((args.host,args.port),Handler)
    print(f'TaskFlow: http://{args.host}:{args.port} | mode={MODE}', flush=True)
    if MODE == 'local':
        print('Local access code: demo2026 (unless DEMO_PASSWORD was set)', flush=True)
    if args.open_browser:
        threading.Timer(0.8,lambda:webbrowser.open(f'http://127.0.0.1:{args.port}')).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
