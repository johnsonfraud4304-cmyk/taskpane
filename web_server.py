"""
TaskPane Web 面板 — 后端
- 提供 HTML 页面、任务 API、LLM 解析 API
- 端口 8911（避开常用冲突）
"""
import http.server
import socketserver
import threading
import json
import sqlite3
import urllib.parse
from pathlib import Path
from datetime import datetime

# 任务数据存储
DB_PATH = None
PLUGIN_DIR = None
WEB_DIR = None
PORT = 8911

# 复用 taskpane_app 的解析函数
import sys
sys.path.insert(0, str(Path(__file__).parent))
from taskpane_app import call_ollama, save_task, list_tasks, init_db, check_reminders


class TaskPaneHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # 安静日志
        pass

    def _send(self, status, content_type, body):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == '/':
            self._send(200, 'text/html; charset=utf-8',
                       (WEB_DIR / 'index.html').read_text())
        elif path == '/api/tasks':
            status = urllib.parse.urlparse(self.path).query
            status = urllib.parse.parse_qs(status).get('status', ['pending'])[0]
            self._send(200, 'application/json',
                       json.dumps(list_tasks(status), ensure_ascii=False, default=str))
        elif path == '/api/reminders':
            reminded = check_reminders()
            self._send(200, 'application/json',
                       json.dumps([{"task": t, "msg": m} for t, m in reminded],
                                 ensure_ascii=False, default=str))
        elif path == '/api/plugins':
            plugins = []
            for f in PLUGIN_DIR.glob('*.json'):
                try:
                    plugins.append(json.loads(f.read_text()))
                except Exception:
                    pass
            self._send(200, 'application/json',
                       json.dumps(plugins, ensure_ascii=False))
        else:
            self._send(404, 'text/plain', 'Not found')

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8') if length else '{}'
        try:
            data = json.loads(body)
        except:
            data = {}

        if path == '/api/parse':
            text = data.get('text', '').strip()
            if not text:
                self._send(400, 'application/json', '{"error": "empty text"}')
                return
            parsed, err = call_ollama(text)
            if err:
                self._send(500, 'application/json',
                           json.dumps({"error": err}, ensure_ascii=False))
                return
            tid = None
            if parsed and parsed.get('is_task'):
                tid = save_task(parsed, text, "panel")
            self._send(200, 'application/json',
                       json.dumps({"parsed": parsed, "task_id": tid},
                                 ensure_ascii=False, default=str))

        elif path == '/api/tasks':
            # 更新任务状态
            task_id = data.get('id')
            status = data.get('status')
            if task_id and status in ('pending', 'done', 'cancelled'):
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("UPDATE tasks SET status=? WHERE id=?", (status, task_id))
                conn.commit()
                conn.close()
                self._send(200, 'application/json', '{"ok": true}')
            else:
                self._send(400, 'application/json', '{"error": "bad params"}')

        else:
            self._send(404, 'text/plain', 'Not found')


def start_server_thread(port, web_dir, db_path, plugin_dir):
    global PORT, WEB_DIR, DB_PATH, PLUGIN_DIR
    PORT = port
    WEB_DIR = web_dir
    DB_PATH = db_path
    PLUGIN_DIR = plugin_dir
    init_db()

    class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    server = ThreadingServer(('127.0.0.1', PORT), TaskPaneHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"[TaskPane web] http://127.0.0.1:{PORT}", flush=True)
    return server