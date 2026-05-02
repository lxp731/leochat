/**
 * Leochat 管理后台 — Client Application
 */

const me = { name: '' };
const users = new Map();   // name → {name, sid}
let connected = false;
let lastDate = '';

const $ = (id) => document.getElementById(id);

const elements = {
  messages: $('messages'),
  messageInput: $('message'),
  usernameInput: $('username'),
  sendBtn: $('sendBtn'),
  scrollBtn: $('scrollBtn'),
  toast: $('toast'),
  statusDot: $('statusDot'),
  connStatus: $('connStatus'),
  onlineCount: $('onlineCount'),
  userList: $('userList'),
  sidebarFooter: $('sidebarFooter'),
  sidebar: document.querySelector('.sidebar'),
  broadcast: $('broadcast'),
  broadcastBtn: $('broadcastBtn'),
};

const socket = io();

// ── Utils ────────────────────────────────────────────

const esc = (s) => String(s)
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;');

const now = () => new Date().toLocaleTimeString('zh-CN', {
  hour: '2-digit', minute: '2-digit'
});

const dstr = () => new Date().toLocaleDateString('zh-CN', {
  month: 'long', day: 'numeric', weekday: 'short'
});

const avColor = (n) => {
  let h = 0;
  for (let i = 0; i < n.length; i++) h = n.charCodeAt(i) + ((h << 5) - h);
  return `hsl(${Math.abs(h) % 360}, 65%, 60%)`;
};

const init = (n) => (n || '?').slice(0, 2).toUpperCase();

// ── 消息渲染 ─────────────────────────────────────────

function checkDate() {
  const d = dstr();
  if (d === lastDate) return;
  lastDate = d;
  const div = document.createElement('div');
  div.className = 'msg-date-divider';
  div.innerHTML = `<span>${d}</span>`;
  elements.messages.appendChild(div);
}

function appendMsg(msgId, user, text, cls, time) {
  checkDate();

  if (cls === 'system') {
    const d = document.createElement('div');
    d.className = 'msg-system';
    d.innerHTML = `<i>${esc(text)}</i>`;
    elements.messages.appendChild(d);
    maybeScroll();
    return;
  }

  if (cls === 'error') {
    const d = document.createElement('div');
    d.className = 'msg-error';
    d.textContent = text;
    elements.messages.appendChild(d);
    maybeScroll();
    return;
  }

  const isMe = !!(user && me.name && user === me.name);
  const row = document.createElement('div');
  row.className = `msg-row${isMe ? ' msg-row-me' : ''}`;
  if (msgId != null) row.dataset.msgId = msgId;

  // Avatar
  const aw = document.createElement('div');
  aw.className = 'msg-avatar-wrap';
  const nm = document.createElement('div');
  nm.className = 'msg-user';
  nm.style.color = avColor(user);
  nm.textContent = esc(user);
  const av = document.createElement('div');
  av.className = 'msg-avatar';
  av.style.background = avColor(user);
  av.textContent = init(user);
  aw.appendChild(nm);
  aw.appendChild(av);

  // Bubble
  const bw = document.createElement('div');
  bw.className = 'msg-bubble-wrap';
  const t = document.createElement('span');
  t.className = 'msg-time';
  t.textContent = time || now();
  const bb = document.createElement('div');
  bb.className = 'msg-bubble';
  bb.textContent = text;
  bw.appendChild(bb);
  bw.appendChild(t);

  // 删除按钮（管理员可见）
  const del = document.createElement('button');
  del.className = 'msg-delete';
  del.textContent = '×';
  del.title = '删除此消息';
  del.addEventListener('click', () => deleteMsg(msgId));

  row.appendChild(aw);
  row.appendChild(bw);
  bw.appendChild(del);
  elements.messages.appendChild(row);
  maybeScroll();
}

function deleteMsg(msgId) {
  if (msgId == null) return;
  if (!confirm('确定要删除这条消息吗？')) return;
  socket.emit('delete_message', { id: msgId });
}

function removeMsgElement(msgId) {
  const el = elements.messages.querySelector(`[data-msg-id="${msgId}"]`);
  if (el) {
    el.style.transition = 'opacity 0.2s, transform 0.2s';
    el.style.opacity = '0';
    el.style.transform = 'translateX(20px)';
    setTimeout(() => el.remove(), 200);
  }
}

// ── 用户列表 ─────────────────────────────────────────

function updateUL() {
  elements.onlineCount.textContent = `${users.size} 人在线`;
  elements.userList.innerHTML = Array.from(users.values())
    .map(u => `
      <div class="user-item">
        <div class="user-avatar-sidebar" style="background:${avColor(u.name)}">${esc(init(u.name))}</div>
        <span>${esc(u.name)}</span>
        ${u.sid ? `
          <button class="kick-btn" data-sid="${esc(u.sid)}" title="踢出 ${esc(u.name)}">🚫</button>
        ` : '<span class="status-dot"></span>'}
      </div>
    `).join('');

  // 绑定踢人事件
  elements.userList.querySelectorAll('.kick-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const sid = btn.dataset.sid;
      const name = btn.title.replace('踢出 ', '');
      if (confirm(`确定要踢出 ${name} 吗？`)) {
        socket.emit('kick_user', { sid });
      }
    });
  });
}

// ── 滚动 ─────────────────────────────────────────────

function maybeScroll() {
  const isAtBottom = elements.messages.scrollHeight - elements.messages.scrollTop - elements.messages.clientHeight < 100;
  if (isAtBottom) {
    elements.messages.scrollTop = elements.messages.scrollHeight;
  }
  elements.scrollBtn.classList.toggle('visible', !isAtBottom && elements.messages.scrollHeight > elements.messages.clientHeight + 100);
}

function showToast(m) {
  elements.toast.textContent = m;
  elements.toast.classList.add('show');
  setTimeout(() => elements.toast.classList.remove('show'), 3000);
}

// ── Socket.IO 事件 ───────────────────────────────────

socket.on('connect', () => {
  connected = true;
  elements.statusDot.style.background = '#4ade80';
  elements.connStatus.innerHTML = '🟢 已连接';
  elements.sidebarFooter.textContent = '管理后台已就绪';
  if (me.name) socket.emit('join', { user: me.name });
});

socket.on('disconnect', () => {
  connected = false;
  users.clear();
  updateUL();
  elements.statusDot.style.background = '#ef4444';
  elements.connStatus.innerHTML = '🔴 断线';
  elements.sidebarFooter.textContent = '连接已断开';
});

socket.on('message', data => {
  appendMsg(data.id, data.user, data.text, 'msg', data.time);
  if (data.user && data.user !== 'System' && !users.has(data.user)) {
    users.set(data.user, { name: data.user, sid: '' });
    updateUL();
  }
});

socket.on('message_deleted', data => {
  removeMsgElement(data.id);
});

socket.on('system', data => {
  appendMsg(null, '', data.text, 'system');
  const t = data.text || '';
  if (t.includes('joined')) {
    const m = t.match(/(.+?)\s+has joined/);
    if (m) { users.set(m[1], { name: m[1], sid: '' }); updateUL(); }
  } else if (t.includes('left') || t.includes('移出')) {
    const m = t.match(/(.+?)\s+(has left|已被管理员)/);
    if (m) { users.delete(m[1]); updateUL(); }
  }
});

socket.on('error', data => showToast(data.text || '发生错误'));

socket.on('userlist', data => {
  users.clear();
  (data.users || []).forEach(u => users.set(u.name, { name: u.name, sid: u.sid || '' }));
  updateUL();
});

// ── 发送消息 ─────────────────────────────────────────

function send() {
  const name = elements.usernameInput.value.trim();
  const text = elements.messageInput.value.trim();

  if (!name) { showToast('请输入管理员昵称'); elements.usernameInput.focus(); return; }
  if (!text) return;
  if (!connected) { showToast('连接已断开，请刷新页面'); return; }

  me.name = name;
  socket.emit('send_message', { user: name, text, time: now() });
  elements.messageInput.value = '';
  elements.messageInput.focus();
}

// ── 系统广播 ─────────────────────────────────────────

function sendBroadcast() {
  const text = elements.broadcast.value.trim();
  if (!text) return;
  if (!connected) { showToast('连接已断开，请刷新页面'); return; }
  socket.emit('broadcast', { text });
  elements.broadcast.value = '';
}

// ── 事件监听 ─────────────────────────────────────────

elements.sendBtn.addEventListener('click', send);
elements.broadcastBtn.addEventListener('click', sendBroadcast);

elements.messageInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});

elements.broadcast.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendBroadcast();
  }
});

elements.scrollBtn.addEventListener('click', () => {
  elements.messages.scrollTo({ top: elements.messages.scrollHeight, behavior: 'smooth' });
});

elements.messages.addEventListener('scroll', maybeScroll);

elements.usernameInput.value = localStorage.getItem('chatroom_admin_name') || '';
const savedName = elements.usernameInput.value.trim();
if (savedName) {
  me.name = savedName;
  if (connected) {
    socket.emit('join', { user: savedName });
  }
}
elements.usernameInput.addEventListener('change', () => {
  const name = elements.usernameInput.value.trim();
  localStorage.setItem('chatroom_admin_name', name);
  if (connected && name) {
    me.name = name;
    socket.emit('join', { user: name });
  }
});

// ── 移动端侧栏 ───────────────────────────────────────

document.addEventListener('click', (e) => {
  if (window.innerWidth <= 768) {
    if (e.target.closest('.sidebar-header')) {
      elements.sidebar.classList.toggle('open');
    } else if (!e.target.closest('.sidebar')) {
      elements.sidebar.classList.remove('open');
    }
  }
});
