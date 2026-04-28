/**
 * ChatRoom Client Application
 */

const me = { name: '' };
const users = new Map();
let connected = false;
let lastDate = '';

// Helper: Get element by ID
const $ = (id) => document.getElementById(id);

// DOM Elements
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
  sidebar: document.querySelector('.sidebar')
};

const socket = io();

// Utils
const esc = (s) => String(s)
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;');

const now = () => new Date().toLocaleTimeString('zh-CN', { 
  hour: '2-digit', 
  minute: '2-digit' 
});

const dstr = () => new Date().toLocaleDateString('zh-CN', { 
  month: 'long', 
  day: 'numeric', 
  weekday: 'short' 
});

const avColor = (n) => {
  let h = 0;
  for (let i = 0; i < n.length; i++) {
    h = n.charCodeAt(i) + ((h << 5) - h);
  }
  return `hsl(${Math.abs(h) % 360}, 65%, 60%)`;
};

const init = (n) => (n || '?').slice(0, 2).toUpperCase();

// Functions
function checkDate() {
  const d = dstr();
  if (d === lastDate) return;
  lastDate = d;
  
  const div = document.createElement('div');
  div.className = 'msg-date-divider';
  div.innerHTML = `<span>${d}</span>`;
  elements.messages.appendChild(div);
}

function appendMsg(user, text, cls, time) {
  checkDate();
  
  if (cls === 'system') {
    const d = document.createElement('div');
    d.className = 'msg-system';
    d.innerHTML = `<i>${text}</i>`;
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

  // Avatar Wrap
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

  // Bubble Wrap
  const bw = document.createElement('div');
  bw.className = 'msg-bubble-wrap';
  
  const t = document.createElement('span');
  t.className = 'msg-time';
  t.textContent = time || now();
  
  const bb = document.createElement('div');
  bb.className = 'msg-bubble';
  bb.textContent = text; // span not needed if we just use textContent

  bw.appendChild(bb);
  bw.appendChild(t);

  // ③ 组装行：统一先头像后气泡，CSS 会处理反转
  row.appendChild(aw);
  row.appendChild(bw);
  
  elements.messages.appendChild(row);
  maybeScroll();
}

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

function updateUL() {
  elements.onlineCount.textContent = `${users.size} 人在线`;
  elements.userList.innerHTML = Array.from(users.values())
    .map(u => `
      <div class="user-item">
        <div class="user-avatar-sidebar" style="background:${avColor(u)}">${esc(init(u))}</div>
        <span>${esc(u)}</span>
        <span class="status-dot"></span>
      </div>
    `).join('');
}

// Socket Event Handlers
socket.on('connect', () => {
  connected = true;
  elements.statusDot.style.background = '#4ade80';
  elements.connStatus.innerHTML = '🟢 已连接';
  elements.sidebarFooter.textContent = '已连接到服务器';
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
  appendMsg(data.user, data.text, 'msg', data.time);
  if (data.user && data.user !== 'System' && !users.has(data.user)) {
    users.set(data.user, data.user);
    updateUL();
  }
});

socket.on('system', data => {
  appendMsg('', data.text, 'system');
  const t = data.text || '';
  if (t.includes('joined')) {
    const m = t.match(/(.+?)\s+has joined/);
    if (m) {
      users.set(m[1], m[1]);
      updateUL();
    }
  } else if (t.includes('left')) {
    const m = t.match(/(.+?)\s+has left/);
    if (m) {
      users.delete(m[1]);
      updateUL();
    }
  }
});

socket.on('error', data => showToast(data.text || '发生错误'));

socket.on('userlist', data => {
  users.clear();
  data.users.forEach(u => users.set(u, u));
  updateUL();
});

// Actions
function send() {
  const name = elements.usernameInput.value.trim();
  const text = elements.messageInput.value.trim();
  
  if (!name) {
    showToast('请输入您的昵称');
    elements.usernameInput.focus();
    return;
  }
  if (!text) return;
  if (!connected) {
    showToast('连接已断开，请刷新页面');
    return;
  }
  
  me.name = name;
  socket.emit('send_message', { user: name, text, time: now() });
  elements.messageInput.value = '';
  elements.messageInput.focus();
}

// Event Listeners
elements.sendBtn.addEventListener('click', send);

elements.messageInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});

elements.scrollBtn.addEventListener('click', () => {
  elements.messages.scrollTo({
    top: elements.messages.scrollHeight,
    behavior: 'smooth'
  });
});

elements.messages.addEventListener('scroll', maybeScroll);

elements.usernameInput.value = localStorage.getItem('chatroom_name') || '';
elements.usernameInput.addEventListener('change', () => {
  const name = elements.usernameInput.value.trim();
  localStorage.setItem('chatroom_name', name);
  if (connected && name) {
    me.name = name;
    socket.emit('join', { user: name });
  }
});

// Mobile Sidebar Toggle (Optional enhancement)
document.addEventListener('click', (e) => {
  if (window.innerWidth <= 768) {
    if (e.target.closest('.sidebar-header')) {
      elements.sidebar.classList.toggle('open');
    } else if (!e.target.closest('.sidebar')) {
      elements.sidebar.classList.remove('open');
    }
  }
});
