"""
Leochat — 轻量实时聊天服务器
─────────────────────────────────
Flask + Socket.IO, 支持速率限制、在线用户列表、环境变量配置、SQLite 持久化。
"""
import os
import time
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import SocketIO, emit

# ── 环境变量加载 ──────────────────────────────────────────
def _load_env():
    # 仅加载当前目录下的 .env
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

_load_env()

# ── 配置 ──────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(24).hex())
CHAT_DEBUG = os.environ.get("CHAT_DEBUG", "false").lower() in ("1", "true", "yes")
CHAT_PORT = int(os.environ.get("CHAT_PORT", "5000"))
# WEB_PASSWORD: web 管理后台密码。未设置时自动生成随机密码并打印到日志
WEB_PASSWORD = os.environ.get("WEB_PASSWORD", "")
if WEB_PASSWORD:
    print(f"[*] WEB_PASSWORD 已从环境变量加载")
else:
    WEB_PASSWORD = os.urandom(8).hex()
    print(f"[!] WEB_PASSWORD 未设置，已生成随机密码: {WEB_PASSWORD}")
DB_PATH = os.environ.get("DB_PATH", "leochat.db")
MAX_MSG_LEN = 2000
MAX_NAME_LEN = 20
RATE_WINDOW = 2          # 速率限制窗口 (秒)
RATE_MAX = 10            # 窗口内最大消息数 (调大以优化体验)

CST = timezone(timedelta(hours=8))

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
socketio = SocketIO(app, cors_allowed_origins="*")

# ── 数据库 ────────────────────────────────────────────────
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT,
                text TEXT,
                time TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def save_user(username):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO users (username, last_seen) VALUES (?, CURRENT_TIMESTAMP)",
            (username,)
        )
        conn.commit()

def save_message(user, text, time_str) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "INSERT INTO messages (user, text, time) VALUES (?, ?, ?)",
            (user, text, time_str)
        )
        conn.commit()
        return cursor.lastrowid


def delete_message(msg_id: int) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM messages WHERE id = ?", (msg_id,))
        conn.commit()

def get_history(limit=50):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT id, user, text, time FROM messages ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in reversed(rows)]

# 初始化数据库
init_db()

# ── 状态 ──────────────────────────────────────────────────
_client_timestamps: dict[str, list[float]] = defaultdict(list)
_sid_to_user: dict[str, str] = {}          # sid → username
_user_to_sids: dict[str, set[str]] = defaultdict(set)
_admin_sids: set[str] = set()              # web 管理后台的 sid，拥有管理权限


def _now_str() -> str:
    return datetime.now(CST).strftime("%H:%M:%S")


def _broadcast_userlist() -> None:
    # 所有人收到用户名列表
    basic = [{"name": u} for u in dict.fromkeys(_sid_to_user.values())]
    socketio.emit("userlist", {"users": basic})
    # 管理员额外收到 sid（用于踢人）
    admin_data = [{"name": u, "sid": s} for s, u in _sid_to_user.items()]
    for admin_sid in _admin_sids:
        emit("userlist", {"users": admin_data, "admin": True}, to=admin_sid)


def _check_rate(ip_or_sid: str) -> bool:
    now = time.time()
    ts = _client_timestamps[ip_or_sid]
    ts[:] = [t for t in ts if now - t < RATE_WINDOW]
    ts.append(now)
    return len(ts) <= RATE_MAX


# ── Web 鉴权 ──────────────────────────────────────────────

def _is_web_client() -> bool:
    """通过检查请求中是否携带 cookie 来判断 web 浏览器 vs CLI/Android"""
    return bool(request.cookies)


def _require_auth() -> bool:
    """返回 True 表示允许，False 表示拒绝"""
    if not WEB_PASSWORD:
        return True
    if not _is_web_client():
        return True  # CLI/Android → 直接放行
    return session.get("authenticated", False)


# ── HTTP ──────────────────────────────────────────────────

@app.before_request
def _check_auth():
    """拦截未认证的 web 请求"""
    # Socket.IO 端点由其事件处理器单独校验
    if request.path.startswith("/socket.io"):
        return None
    # 允许静态资源和登录页
    if request.path.startswith("/static/") or request.path == "/login":
        return None
    # 需要认证
    if WEB_PASSWORD and not session.get("authenticated"):
        return redirect(url_for("login"))
    return None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == WEB_PASSWORD:
            session["authenticated"] = True
            return redirect(url_for("index"))
        error = "密码错误"
    return render_template("login.html", error=error)


# ── 连接 / 断线 ───────────────────────────────────────────
@socketio.on("connect")
def handle_connect(auth=None):
    if not _require_auth():
        return False  # 拒绝未认证的 web 连接
    sid = getattr(request, 'sid')
    if _is_web_client():
        _admin_sids.add(sid)
    print(f"[+] {sid} connected{' (admin)' if sid in _admin_sids else ''}")


@socketio.on("disconnect")
def handle_disconnect():
    sid = getattr(request, 'sid')
    _admin_sids.discard(sid)
    username = _sid_to_user.pop(sid, None)
    if username:
        _user_to_sids[username].discard(sid)
        if not _user_to_sids[username]:
            del _user_to_sids[username]
            socketio.emit("system", {"text": f"{username} has left the chat."})
        _broadcast_userlist()
    
    # 清理限流相关的内存占用
    if addr := request.remote_addr:
        _client_timestamps.pop(addr, None)
    if sid:
        _client_timestamps.pop(sid, None)
    
    print(f"[-] {sid} disconnected ({username or 'unknown'})")


# ── 用户注册 ──────────────────────────────────────────────
@socketio.on("join")
def handle_join(data):
    if not _require_auth():
        return
    if not isinstance(data, dict):
        return
    username = str(data.get("user", ""))[:MAX_NAME_LEN].strip()
    if not username:
        return

    sid = getattr(request, 'sid')
    old_name = _sid_to_user.get(sid)

    if old_name and old_name != username:
        _user_to_sids[old_name].discard(sid)
        if not _user_to_sids[old_name]:
            del _user_to_sids[old_name]

    _sid_to_user[sid] = username
    _user_to_sids[username].add(sid)

    if username != old_name:
        save_user(username)
        socketio.emit("system", {"text": f"{username} has joined the chat."})
        
        # 推送历史消息给新加入的用户
        history = get_history()
        for msg in history:
            emit("message", msg, to=sid)
            
    _broadcast_userlist()


# ── 消息 ──────────────────────────────────────────────────
@socketio.on("send_message")
def handle_message(data):
    if not _require_auth():
        return
    if not isinstance(data, dict):
        return

    sid = getattr(request, 'sid')
    rate_key = request.remote_addr or sid
    user = _sid_to_user.get(sid, "Anonymous")
    text = str(data.get("text", ""))[:MAX_MSG_LEN]
    ts = _now_str()

    if not text.strip():
        return

    if not _check_rate(rate_key):
        emit("error", {"text": "发送太快，请稍候。"})
        return

    # 持久化消息并获取 ID
    msg_id = save_message(user, text, ts)

    print(f"[MSG] {user}: {text[:80]}{'…' if len(text) > 80 else ''}")
    socketio.emit("message", {"id": msg_id, "user": user, "text": text, "time": ts})


# ── 管理员功能 ────────────────────────────────────────────

def _is_admin() -> bool:
    """当前连接是否为 web 管理后台"""
    return getattr(request, 'sid', None) in _admin_sids


@socketio.on("delete_message")
def handle_delete_message(data):
    if not _require_auth() or not _is_admin():
        return
    if not isinstance(data, dict):
        return

    msg_id = data.get("id")
    if msg_id is None:
        return

    delete_message(int(msg_id))
    print(f"[ADMIN] 消息 {msg_id} 已被管理员删除")
    socketio.emit("message_deleted", {"id": msg_id})


@socketio.on("kick_user")
def handle_kick_user(data):
    if not _require_auth() or not _is_admin():
        return
    if not isinstance(data, dict):
        return

    target_sid = data.get("sid")
    if not target_sid or target_sid == getattr(request, 'sid'):
        return  # 不能踢自己

    target_user = _sid_to_user.get(target_sid, "unknown")
    print(f"[ADMIN] 管理员踢出用户: {target_user} ({target_sid})")
    socketio.emit("system", {"text": f"{target_user} 已被管理员移出聊天室"})
    socketio.server.disconnect(target_sid)
    _broadcast_userlist()


@socketio.on("broadcast")
def handle_broadcast(data):
    if not _require_auth() or not _is_admin():
        return
    if not isinstance(data, dict):
        return

    text = str(data.get("text", ""))[:MAX_MSG_LEN].strip()
    if not text:
        return

    print(f"[ADMIN] 系统公告: {text[:80]}{'…' if len(text) > 80 else ''}")
    socketio.emit("system", {"text": f"📢 {text}"})


if __name__ == "__main__":
    # allow_unsafe_werkzeug 必须为 True：在 Docker 容器中 Werkzeug 就是预期运行时
    socketio.run(app, host="0.0.0.0", port=CHAT_PORT,
                 debug=CHAT_DEBUG, allow_unsafe_werkzeug=True)
