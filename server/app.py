"""
Leochat — 轻量实时聊天服务器
─────────────────────────────────
Flask + Socket.IO, 支持速率限制、在线用户列表、环境变量配置、SQLite 持久化。
"""
import os
import random
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

RESERVED_NAMES_LOWER = {"system", "anonymous", "admin", "administrator"}
RESERVED_NAMES_EXACT = {"管理员", "系统"}

CST = timezone(timedelta(hours=8))

AVATAR_DIR = os.path.join(os.path.dirname(__file__), 'static', 'avatars')
AVATAR_FILES = [f for f in os.listdir(AVATAR_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))]

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
        try:
            conn.execute("ALTER TABLE users ADD COLUMN avatar TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT,
                text TEXT,
                time TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        try:
            conn.execute("ALTER TABLE messages ADD COLUMN revoked INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target TEXT NOT NULL,
                type TEXT NOT NULL,
                expires_at DATETIME,
                created_by TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sensitive_words (
                word TEXT PRIMARY KEY,
                created_by TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS announcement (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                text TEXT NOT NULL DEFAULT '',
                set_by TEXT DEFAULT '',
                set_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("INSERT OR IGNORE INTO announcement (id, text) VALUES (1, '')")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS room_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )
        """)
        for k, v in [
            ('room_name', 'Leochat'), ('welcome_msg', ''), ('max_msg_len', '2000'),
            ('max_history', '5000'), ('history_limit', '50'),
        ]:
            conn.execute("INSERT OR IGNORE INTO room_config (key, value) VALUES (?, ?)", (k, v))
        conn.commit()


def save_user(username):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO users (username, last_seen) VALUES (?, CURRENT_TIMESTAMP)",
            (username,)
        )
        conn.commit()


def save_user_avatar(username: str, avatar: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE users SET avatar = ? WHERE username = ?",
            (avatar, username)
        )
        conn.commit()


def get_user_avatar(username: str) -> str:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT avatar FROM users WHERE username = ?",
            (username,)
        ).fetchone()
    return (row[0] if row and row[0] else "")

def _cleanup_old_messages(max_history: int) -> int:
    """清理超出上限的最旧消息，返回删除条数"""
    with sqlite3.connect(DB_PATH) as conn:
        total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        excess = total - max_history
        if excess > 0:
            conn.execute(
                "DELETE FROM messages WHERE id IN (SELECT id FROM messages ORDER BY id ASC LIMIT ?)",
                (excess,)
            )
            conn.commit()
        return max(excess, 0)


def save_message(user, text, time_str) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "INSERT INTO messages (user, text, time) VALUES (?, ?, ?)",
            (user, text, time_str)
        )
        conn.commit()
        msg_id = cursor.lastrowid
    # 写入后检查是否需要清理
    config = _get_room_config()
    max_history = int(config.get('max_history', '5000'))
    deleted = _cleanup_old_messages(max_history)
    if deleted:
        print(f"[DB] 清理了 {deleted} 条旧消息（上限 {max_history}）")
    return msg_id


def delete_message(msg_id: int) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM messages WHERE id = ?", (msg_id,))
        conn.commit()

def get_history(limit=50):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT id, user, text, time, revoked FROM messages ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in reversed(rows)]


def _get_history_limit() -> int:
    config = _get_room_config()
    return max(10, min(200, int(config.get('history_limit', '50'))))


def get_messages_page(limit=50, offset=0, user_filter='', keyword=''):
    """分页查询消息，支持按用户名筛选和关键词搜索"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conditions = []
        params: list = []
        if user_filter:
            conditions.append("user = ?")
            params.append(user_filter)
        if keyword:
            conditions.append("text LIKE ?")
            params.append(f'%{keyword}%')
        where = (' WHERE ' + ' AND '.join(conditions)) if conditions else ''
        count_sql = f"SELECT COUNT(*) as cnt FROM messages{where}"
        total = conn.execute(count_sql, params).fetchone()['cnt']
        data_sql = f"SELECT id, user, text, time, revoked FROM messages{where} ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(data_sql, params).fetchall()
        return total, [dict(row) for row in reversed(rows)]


def get_stats():
    """返回今日消息数、今日访客数、历史消息总数"""
    today = datetime.now(CST).strftime("%Y-%m-%d")
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        today_msgs = conn.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE time LIKE ?",
            (f'{today}%',)
        ).fetchone()['cnt']
        total_msgs = conn.execute(
            "SELECT COUNT(*) as cnt FROM messages"
        ).fetchone()['cnt']
        total_users = conn.execute(
            "SELECT COUNT(*) as cnt FROM users"
        ).fetchone()['cnt']
        today_visitors = conn.execute(
            "SELECT COUNT(*) as cnt FROM users WHERE date(last_seen) = ?",
            (today,)
        ).fetchone()['cnt']
    return {
        'today_msgs': today_msgs,
        'total_msgs': total_msgs,
        'total_users': total_users,
        'today_visitors': today_visitors,
    }


# ── 禁言 / 封禁 ────────────────────────────────────────────

def _is_banned(username: str, ip: str = '') -> tuple[bool, str]:
    """检查用户或 IP 是否被封禁。返回 (是否被封, 原因)"""
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_PATH) as conn:
        # 过期封禁自动清理
        conn.execute("DELETE FROM bans WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,))
        conn.commit()
        # 检查永久封禁
        row = conn.execute(
            "SELECT target, type FROM bans WHERE (expires_at IS NULL) AND (target = ? OR (target = ? AND type = 'ban_ip')) LIMIT 1",
            (username, ip)
        ).fetchone()
        if row:
            return True, f'您已被封禁'
        # 检查临时封禁
        row = conn.execute(
            "SELECT target, type, expires_at FROM bans WHERE expires_at IS NOT NULL AND (target = ? OR (target = ? AND type = 'ban_ip')) LIMIT 1",
            (username, ip)
        ).fetchone()
        if row:
            return True, f'您已被封禁（至 {row[2]}）'
    return False, ''


def _is_muted(username: str) -> tuple[bool, str]:
    """检查用户是否被禁言。返回 (是否被禁, 原因)"""
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM bans WHERE type = 'mute' AND expires_at IS NOT NULL AND expires_at <= ?", (now,))
        conn.commit()
        row = conn.execute(
            "SELECT expires_at FROM bans WHERE type = 'mute' AND target = ? AND (expires_at IS NULL OR expires_at > ?) LIMIT 1",
            (username, now)
        ).fetchone()
    if row:
        if row[0]:
            return True, f'您已被禁言（至 {row[0]}）'
        return True, '您已被永久禁言'
    return False, ''


def _add_ban(target: str, ban_type: str, duration_minutes: int = 0, created_by: str = '') -> None:
    """添加封禁/禁言记录"""
    expires = None
    if duration_minutes > 0:
        expires = (datetime.now(CST) + timedelta(minutes=duration_minutes)).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO bans (target, type, expires_at, created_by) VALUES (?, ?, ?, ?)",
            (target, ban_type, expires, created_by)
        )
        conn.commit()


def _remove_ban(target: str, ban_type: str = '') -> None:
    """解除封禁/禁言"""
    with sqlite3.connect(DB_PATH) as conn:
        if ban_type:
            conn.execute("DELETE FROM bans WHERE target = ? AND type = ?", (target, ban_type))
        else:
            conn.execute("DELETE FROM bans WHERE target = ?", (target,))
        conn.commit()


def _get_bans() -> list[dict]:
    """获取所有封禁/禁言记录"""
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM bans WHERE type = 'mute' AND expires_at IS NOT NULL AND expires_at <= ?", (now,))
        conn.commit()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, target, type, expires_at, created_by, created_at FROM bans ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


# ── 敏感词 ────────────────────────────────────────────────

_SENSITIVE_WORDS: list[str] = []


def _load_sensitive_words() -> list[str]:
    """从数据库加载敏感词到内存缓存"""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT word FROM sensitive_words").fetchall()
    return [r[0] for r in rows]


def _add_sensitive_word(word: str, created_by: str = '') -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sensitive_words (word, created_by) VALUES (?, ?)",
            (word, created_by)
        )
        conn.commit()
    _SENSITIVE_WORDS.append(word)


def _remove_sensitive_word(word: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM sensitive_words WHERE word = ?", (word,))
        conn.commit()
    if word in _SENSITIVE_WORDS:
        _SENSITIVE_WORDS.remove(word)


def _filter_text(text: str) -> str:
    """过滤敏感词，替换为 ***"""
    result = text
    for w in _SENSITIVE_WORDS:
        if w and w in result:
            result = result.replace(w, '***')
    return result


# ── 消息撤回 ────────────────────────────────────────────────

def _revoke_message(msg_id: int) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE messages SET revoked = 1 WHERE id = ?", (msg_id,))
        conn.commit()

# 初始化数据库
init_db()
_SENSITIVE_WORDS = _load_sensitive_words()


# ── 置顶公告 ────────────────────────────────────────────────

def _get_announcement() -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT text, set_by, set_at FROM announcement WHERE id = 1").fetchone()
    return {'text': row['text'] if row else '', 'set_by': row['set_by'] if row else '', 'set_at': row['set_at'] if row else ''}


def _set_announcement(text: str, set_by: str = '') -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO announcement (id, text, set_by, set_at) VALUES (1, ?, ?, CURRENT_TIMESTAMP)",
            (text, set_by)
        )
        conn.commit()


# ── 房间配置 ────────────────────────────────────────────────

def _get_room_config() -> dict[str, str]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT key, value FROM room_config").fetchall()
    return {r[0]: r[1] for r in rows}


def _set_room_config(key: str, value: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO room_config (key, value) VALUES (?, ?)",
            (key, value)
        )
        conn.commit()

# ── 状态 ──────────────────────────────────────────────────
_client_timestamps: dict[str, list[float]] = defaultdict(list)
_sid_to_user: dict[str, str] = {}          # sid → username
_user_to_sids: dict[str, set[str]] = defaultdict(set)
_user_avatar: dict[str, str] = {}          # username → avatar filename
_user_meta: dict[str, dict] = {}           # sid → {ip, connect_time, last_msg_time}
_admin_sids: set[str] = set()              # web 管理后台的 sid，拥有管理权限


def _pick_avatar(username: str) -> str:
    """为用户随机分配头像，尽量不与聊天室内其他人重复"""
    used = {v for k, v in _user_avatar.items() if k != username}
    available = [f for f in AVATAR_FILES if f not in used]
    pool = available if available else AVATAR_FILES
    return random.choice(pool)


def _now_str() -> str:
    return datetime.now(CST).strftime("%H:%M:%S")


def _broadcast_userlist() -> None:
    # 所有人收到用户名列表
    basic = [{"name": u, "avatar": _user_avatar.get(u, "")} for u in dict.fromkeys(_sid_to_user.values())]
    socketio.emit("userlist", {"users": basic})
    # 管理员额外收到 sid / 元数据（用于踢人 + 用户详情）
    admin_data = []
    for s, u in _sid_to_user.items():
        meta = _user_meta.get(s, {})
        admin_data.append({
            "name": u,
            "sid": s,
            "avatar": _user_avatar.get(u, ""),
            "ip": meta.get('ip', ''),
            "connect_time": meta.get('connect_time', ''),
            "last_msg_time": meta.get('last_msg_time', ''),
        })
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
    # 允许静态资源、登录页
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
    _user_meta[sid] = {
        'ip': request.remote_addr or 'unknown',
        'connect_time': _now_str(),
        'last_msg_time': '',
    }
    if _is_web_client():
        _admin_sids.add(sid)
    # 发送服务端 CST 时间，前端用于日期分割线和时间显示
    now_cst = datetime.now(CST)
    config = _get_room_config()
    emit("server_time", {
        "timestamp": now_cst.isoformat(),
        "date": now_cst.strftime("%Y-%m-%d"),
        "time": now_cst.strftime("%H:%M:%S"),
        "room_name": config.get("room_name", "Leochat"),
    })
    print(f"[+] {sid} connected{' (admin)' if sid in _admin_sids else ''}")


@socketio.on("disconnect")
def handle_disconnect():
    sid = getattr(request, 'sid')
    _admin_sids.discard(sid)
    _user_meta.pop(sid, None)
    username = _sid_to_user.pop(sid, None)
    if username:
        _user_to_sids[username].discard(sid)
        if not _user_to_sids[username]:
            del _user_to_sids[username]
            _user_avatar.pop(username, None)
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

    # 保留名检查
    if username.lower() in RESERVED_NAMES_LOWER or username in RESERVED_NAMES_EXACT:
        emit("error", {"text": "该用户名不可使用，请换一个。"})
        return

    sid = getattr(request, 'sid')

    # 同名检查：另一个 sid 已经占用该用户名
    if username in _user_to_sids and sid not in _user_to_sids[username]:
        emit("error", {"text": "该用户名已被使用，请换一个。"})
        return

    # 封禁检查
    ip = request.remote_addr or ''
    banned, reason = _is_banned(username, ip)
    if banned:
        emit("error", {"text": reason})
        return
    old_name = _sid_to_user.get(sid)

    if old_name and old_name != username:
        _user_to_sids[old_name].discard(sid)
        if not _user_to_sids[old_name]:
            del _user_to_sids[old_name]

    _sid_to_user[sid] = username
    _user_to_sids[username].add(sid)

    if username != old_name:
        save_user(username)
        # 头像：优先从数据库恢复，若无或被占用则随机分配
        saved = get_user_avatar(username)
        if saved and saved not in {v for k, v in _user_avatar.items() if k != username}:
            _user_avatar[username] = saved
        else:
            avatar = _pick_avatar(username)
            _user_avatar[username] = avatar
            save_user_avatar(username, avatar)
        socketio.emit("system", {"text": f"{username} has joined the chat."})

        # 推送置顶公告和欢迎语给新用户
        ann = _get_announcement()
        if ann['text']:
            emit("announcement", ann, to=sid)
        config = _get_room_config()
        if config.get('welcome_msg', '').strip():
            emit("system", {"text": f"👋 {config['welcome_msg']}"}, to=sid)

        # 推送历史消息给新加入的用户
        history = get_history(limit=_get_history_limit())
        for msg in history:
            avatar = _user_avatar.get(msg['user'], '')
            if not avatar:
                avatar = get_user_avatar(msg['user'])
            msg['avatar'] = avatar
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
    # 更新最后发言时间
    if sid in _user_meta:
        _user_meta[sid]['last_msg_time'] = _now_str()
    user = _sid_to_user.get(sid, "Anonymous")
    config = _get_room_config()
    max_len = int(config.get('max_msg_len', MAX_MSG_LEN))
    text = str(data.get("text", ""))[:max_len]
    ts = _now_str()

    if not text.strip():
        return

    # 禁言检查
    muted, reason = _is_muted(user)
    if muted:
        emit("error", {"text": reason})
        return

    # 敏感词过滤
    text = _filter_text(text)
    if not text.strip():
        return

    if not _check_rate(rate_key):
        emit("error", {"text": "发送太快，请稍候。"})
        return

    # 持久化消息并获取 ID
    msg_id = save_message(user, text, ts)

    print(f"[MSG] {user}: {text[:80]}{'…' if len(text) > 80 else ''}")
    socketio.emit("message", {"id": msg_id, "user": user, "text": text, "time": ts, "avatar": _user_avatar.get(user, '')})


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


# ── 管理员数据查询 ────────────────────────────────────────

@socketio.on("get_messages")
def handle_get_messages(data):
    if not _require_auth() or not _is_admin():
        return
    limit = int(data.get('limit', 50)) if isinstance(data, dict) else 50
    offset = int(data.get('offset', 0)) if isinstance(data, dict) else 0
    user_filter = str(data.get('user', '')) if isinstance(data, dict) else ''
    keyword = str(data.get('keyword', '')) if isinstance(data, dict) else ''
    total, messages = get_messages_page(limit, offset, user_filter, keyword)
    for msg in messages:
        msg['avatar'] = _user_avatar.get(msg['user'], '')
    emit("messages_page", {"messages": messages, "total": total, "limit": limit, "offset": offset})


@socketio.on("get_stats")
def handle_get_stats():
    if not _require_auth():
        return
    emit("stats", get_stats())


# ── 禁言 / 封禁 ────────────────────────────────────────────

@socketio.on("mute_user")
def handle_mute_user(data):
    if not _require_auth() or not _is_admin():
        return
    target = str(data.get('target', '')).strip() if isinstance(data, dict) else ''
    minutes = int(data.get('minutes', 5)) if isinstance(data, dict) else 5
    if not target:
        return
    _add_ban(target, 'mute', minutes)
    print(f"[ADMIN] 禁言 {target} {minutes} 分钟")
    emit("system", {"text": f"{target} 已被禁言 {minutes} 分钟"}, broadcast=True)
    _broadcast_userlist()


@socketio.on("unmute_user")
def handle_unmute_user(data):
    if not _require_auth() or not _is_admin():
        return
    target = str(data.get('target', '')).strip() if isinstance(data, dict) else ''
    if not target:
        return
    _remove_ban(target, 'mute')
    print(f"[ADMIN] 解除禁言 {target}")
    emit("system", {"text": f"{target} 已被解除禁言"}, broadcast=True)


@socketio.on("ban_user")
def handle_ban_user(data):
    if not _require_auth() or not _is_admin():
        return
    target = str(data.get('target', '')).strip() if isinstance(data, dict) else ''
    minutes = int(data.get('minutes', 0)) if isinstance(data, dict) else 0
    if not target:
        return
    _add_ban(target, 'ban', minutes)
    label = f'{minutes} 分钟' if minutes > 0 else '永久'
    print(f"[ADMIN] 封禁 {target} ({label})")
    # 断开被封用户的所有连接
    for s in list(_user_to_sids.get(target, set())):
        socketio.server.disconnect(s)
    emit("system", {"text": f"{target} 已被封禁（{label}）"}, broadcast=True)
    _broadcast_userlist()


@socketio.on("unban_user")
def handle_unban_user(data):
    if not _require_auth() or not _is_admin():
        return
    target = str(data.get('target', '')).strip() if isinstance(data, dict) else ''
    if not target:
        return
    _remove_ban(target, 'ban')
    print(f"[ADMIN] 解除封禁 {target}")
    emit("system", {"text": f"{target} 已被解除封禁"}, broadcast=True)


@socketio.on("list_bans")
def handle_list_bans():
    if not _require_auth() or not _is_admin():
        return
    emit("ban_list", {"bans": _get_bans()})


# ── 敏感词 ────────────────────────────────────────────────

@socketio.on("add_sensitive_word")
def handle_add_sensitive_word(data):
    if not _require_auth() or not _is_admin():
        return
    word = str(data.get('word', '')).strip() if isinstance(data, dict) else ''
    if not word:
        return
    _add_sensitive_word(word)
    print(f"[ADMIN] 添加敏感词: {word}")
    emit("sensitive_words", {"words": list(_SENSITIVE_WORDS)})


@socketio.on("remove_sensitive_word")
def handle_remove_sensitive_word(data):
    if not _require_auth() or not _is_admin():
        return
    word = str(data.get('word', '')).strip() if isinstance(data, dict) else ''
    if not word:
        return
    _remove_sensitive_word(word)
    print(f"[ADMIN] 删除敏感词: {word}")
    emit("sensitive_words", {"words": list(_SENSITIVE_WORDS)})


@socketio.on("list_sensitive_words")
def handle_list_sensitive_words():
    if not _require_auth() or not _is_admin():
        return
    emit("sensitive_words", {"words": list(_SENSITIVE_WORDS)})


# ── 消息撤回 ────────────────────────────────────────────────

@socketio.on("revoke_message")
def handle_revoke_message(data):
    if not _require_auth() or not _is_admin():
        return
    msg_id = data.get('id') if isinstance(data, dict) else None
    if msg_id is None:
        return
    _revoke_message(int(msg_id))
    print(f"[ADMIN] 撤回消息 {msg_id}")
    socketio.emit("message_revoked", {"id": msg_id})


# ── 置顶公告 ────────────────────────────────────────────────

@socketio.on("get_announcement")
def handle_get_announcement():
    if not _require_auth() or not _is_admin():
        return
    emit("announcement", _get_announcement())


@socketio.on("set_announcement")
def handle_set_announcement(data):
    if not _require_auth() or not _is_admin():
        return
    text = str(data.get('text', '')).strip() if isinstance(data, dict) else ''
    if not text:
        return
    _set_announcement(text)
    print(f"[ADMIN] 设置公告: {text[:50]}")
    socketio.emit("announcement", _get_announcement())


@socketio.on("clear_announcement")
def handle_clear_announcement():
    if not _require_auth() or not _is_admin():
        return
    _set_announcement('')
    print(f"[ADMIN] 清除公告")
    socketio.emit("announcement_cleared")


# ── 房间配置 ────────────────────────────────────────────────

@socketio.on("get_room_config")
def handle_get_room_config():
    if not _require_auth() or not _is_admin():
        return
    emit("room_config", _get_room_config())


@socketio.on("set_room_config")
def handle_set_room_config(data):
    if not _require_auth() or not _is_admin():
        return
    if not isinstance(data, dict):
        return
    key = str(data.get('key', '')).strip()
    value = str(data.get('value', '')).strip()
    if not key:
        return
    allowed = {'room_name', 'welcome_msg', 'max_msg_len', 'max_history', 'history_limit'}
    if key not in allowed:
        return
    _set_room_config(key, value)
    print(f"[ADMIN] 配置 {key} = {value[:30]}")
    emit("room_config", _get_room_config())


@socketio.on("purge_messages")
def handle_purge_messages():
    if not _require_auth() or not _is_admin():
        return
    config = _get_room_config()
    max_history = int(config.get('max_history', '5000'))
    deleted = _cleanup_old_messages(max_history)
    print(f"[ADMIN] 手动清理了 {deleted} 条旧消息")
    emit("system", {"text": f"管理员清理了 {deleted} 条旧消息"}, broadcast=True)
    emit("stats", get_stats())


# ── 聊天导出 ────────────────────────────────────────────────

@socketio.on("export_chat")
def handle_export_chat(data):
    if not _require_auth() or not _is_admin():
        return
    fmt = str(data.get('format', 'json')).strip().lower() if isinstance(data, dict) else 'json'
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, user, text, time, revoked FROM messages ORDER BY id ASC"
        ).fetchall()
    msgs = [dict(r) for r in rows]
    if fmt == 'txt':
        lines = [f"[{m['time']}] {m['user']}: {m['text']}" for m in msgs]
        emit("export_data", {"data": '\n'.join(lines), "format": "txt"})
    else:
        import json
        emit("export_data", {"data": json.dumps(msgs, ensure_ascii=False, indent=2), "format": "json"})


if __name__ == "__main__":
    # allow_unsafe_werkzeug 必须为 True：在 Docker 容器中 Werkzeug 就是预期运行时
    socketio.run(app, host="0.0.0.0", port=CHAT_PORT,
                 debug=CHAT_DEBUG, allow_unsafe_werkzeug=True)
