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

from flask import Flask, render_template, request
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

def save_message(user, text, time_str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO messages (user, text, time) VALUES (?, ?, ?)",
            (user, text, time_str)
        )
        conn.commit()

def get_history(limit=50):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT user, text, time FROM messages ORDER BY id DESC LIMIT ?",
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


def _now_str() -> str:
    return datetime.now(CST).strftime("%H:%M:%S")


def _broadcast_userlist() -> None:
    users = list(dict.fromkeys(_sid_to_user.values()))
    # 使用 socketio.emit 确保全局广播的确定性
    socketio.emit("userlist", {"users": users})


def _check_rate(ip_or_sid: str) -> bool:
    now = time.time()
    ts = _client_timestamps[ip_or_sid]
    ts[:] = [t for t in ts if now - t < RATE_WINDOW]
    ts.append(now)
    return len(ts) <= RATE_MAX


# ── HTTP ──────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


# ── 连接 / 断线 ───────────────────────────────────────────
@socketio.on("connect")
def handle_connect(auth=None):
    sid = getattr(request, 'sid')
    print(f"[+] {sid} connected")


@socketio.on("disconnect")
def handle_disconnect():
    sid = getattr(request, 'sid')
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

    # 持久化消息
    save_message(user, text, ts)

    print(f"[MSG] {user}: {text[:80]}{'…' if len(text) > 80 else ''}")
    # 真正的全局广播
    socketio.emit("message", {"user": user, "text": text, "time": ts})


if __name__ == "__main__":
    # allow_unsafe_werkzeug 必须为 True：在 Docker 容器中 Werkzeug 就是预期运行时
    socketio.run(app, host="0.0.0.0", port=CHAT_PORT,
                 debug=CHAT_DEBUG, allow_unsafe_werkzeug=True)
