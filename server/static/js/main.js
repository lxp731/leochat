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
  // Stats
  statTodayMsgs: $('statTodayMsgs'),
  statTodayVisits: $('statTodayVisits'),
  statTotalMsgs: $('statTotalMsgs'),
  statTotalUsers: $('statTotalUsers'),
  // Search
  searchKeyword: $('searchKeyword'),
  searchUser: $('searchUser'),
  searchBtn: $('searchBtn'),
  loadMoreBtn: $('loadMoreBtn'),
  // Sensitive words
  sensitiveInput: $('sensitiveInput'),
  sensitiveAddBtn: $('sensitiveAddBtn'),
  sensitiveList: $('sensitiveList'),
  // Announcement
  announcementBanner: $('announcementBanner'),
  annContent: $('annContent'),
  annClear: $('annClear'),
  pinAnnBtn: $('pinAnnBtn'),
  // Settings
  settingsBtn: $('settingsBtn'),
  settingsModal: $('settingsModal'),
  cfgRoomName: $('cfgRoomName'),
  cfgWelcome: $('cfgWelcome'),
  cfgMaxMsgLen: $('cfgMaxMsgLen'),
  cfgSaveBtn: $('cfgSaveBtn'),
  cfgCancelBtn: $('cfgCancelBtn'),
  // Export
  exportBtn: $('exportBtn'),
};

let historyOffset = 0;
let historyTotal = 0;
let historyFilter = { user: '', keyword: '' };

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
  const userData = users.get(user);
  const avatarFile = userData?.avatar || '';
  if (avatarFile) {
    const img = document.createElement('img');
    img.src = `/static/avatars/${avatarFile}`;
    img.alt = init(user);
    av.appendChild(img);
  } else {
    av.style.background = avColor(user);
    av.textContent = init(user);
  }
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

  // 撤回按钮（管理员可见）
  const rev = document.createElement('button');
  rev.className = 'msg-revoke';
  rev.textContent = '↩';
  rev.title = '撤回此消息';
  rev.addEventListener('click', () => revokeMsg(msgId));

  row.appendChild(aw);
  row.appendChild(bw);
  bw.appendChild(del);
  bw.appendChild(rev);
  elements.messages.appendChild(row);
  maybeScroll();
}

function deleteMsg(msgId) {
  if (msgId == null) return;
  if (!confirm('确定要删除这条消息吗？')) return;
  socket.emit('delete_message', { id: msgId });
}

function revokeMsg(msgId) {
  if (msgId == null) return;
  if (!confirm('确定要撤回这条消息吗？')) return;
  socket.emit('revoke_message', { id: msgId });
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

function appendSearchMsg(msg) {
  // Simplified message render for search results (prepend to top)
  const user = msg.user || '';
  const row = document.createElement('div');
  row.className = 'msg-row';
  if (msg.id != null) row.dataset.msgId = msg.id;

  const aw = document.createElement('div');
  aw.className = 'msg-avatar-wrap';
  const nm = document.createElement('div');
  nm.className = 'msg-user';
  nm.style.color = avColor(user);
  nm.textContent = esc(user);
  const av = document.createElement('div');
  av.className = 'msg-avatar';
  if (msg.avatar) {
    const img = document.createElement('img');
    img.src = `/static/avatars/${msg.avatar}`;
    img.alt = init(user);
    av.appendChild(img);
  } else {
    av.style.background = avColor(user);
    av.textContent = init(user);
  }
  aw.appendChild(nm);
  aw.appendChild(av);

  const bw = document.createElement('div');
  bw.className = 'msg-bubble-wrap';
  const t = document.createElement('span');
  t.className = 'msg-time';
  t.textContent = msg.time || '';
  const bb = document.createElement('div');
  bb.className = 'msg-bubble';
  bb.textContent = msg.text;
  bw.appendChild(bb);
  bw.appendChild(t);

  row.appendChild(aw);
  row.appendChild(bw);
  if (msg.id != null) {
    const del = document.createElement('button');
    del.className = 'msg-delete';
    del.textContent = '×';
    del.title = '删除此消息';
    del.addEventListener('click', () => deleteMsg(msg.id));
    bw.appendChild(del);
  }
  elements.messages.insertBefore(row, elements.messages.firstChild);
}

function doSearch(reset) {
  const keyword = elements.searchKeyword.value.trim();
  const user = elements.searchUser.value.trim();
  historyFilter = { user, keyword };
  socket.emit('get_messages', { limit: 50, offset: 0, user, keyword });
  elements.loadMoreBtn.style.display = '';
}

function loadMore() {
  socket.emit('get_messages', {
    limit: 50,
    offset: historyOffset,
    user: historyFilter.user,
    keyword: historyFilter.keyword,
  });
}

// ── 用户列表 ─────────────────────────────────────────

function updateUL() {
  elements.onlineCount.textContent = `${users.size} 人在线`;
  elements.userList.innerHTML = Array.from(users.values())
    .map(u => {
      const hasAvatar = !!(u.avatar);
      const avatarContent = hasAvatar
        ? `<img src="/static/avatars/${esc(u.avatar)}" alt="${esc(u.name)}">`
        : esc(init(u.name));
      const avatarStyle = hasAvatar
        ? ''
        : `style="background:${avColor(u.name)}"`;
      const detail = (u.ip || u.connect_time)
        ? `<div class="user-detail">${[u.ip, u.connect_time ? '🕐' + u.connect_time : '', u.last_msg_time ? '💬' + u.last_msg_time : ''].filter(Boolean).join(' · ')}</div>`
        : '';
      return `
      <div class="user-item">
        <div class="user-avatar-sidebar" ${avatarStyle}>${avatarContent}</div>
        <div style="flex:1;min-width:0">
          <span>${esc(u.name)}</span>
          ${detail}
        </div>
        ${u.sid ? `
          <button class="mute-btn" data-name="${esc(u.name)}" title="禁言 ${esc(u.name)}">🔇</button>
          <button class="ban-btn" data-name="${esc(u.name)}" title="封禁 ${esc(u.name)}">⛔</button>
          <button class="kick-btn" data-sid="${esc(u.sid)}" title="踢出 ${esc(u.name)}">🚫</button>
        ` : '<span class="status-dot"></span>'}
      </div>
    `}).join('');

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

  // 绑定禁言事件
  elements.userList.querySelectorAll('.mute-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const name = btn.dataset.name;
      const mins = prompt(`禁言 ${name}，输入分钟数：`, '5');
      if (mins !== null && parseInt(mins) > 0) {
        socket.emit('mute_user', { target: name, minutes: parseInt(mins) });
      }
    });
  });

  // 绑定封禁事件
  elements.userList.querySelectorAll('.ban-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const name = btn.dataset.name;
      const mins = prompt(`封禁 ${name}，输入分钟数（0=永久）：`, '0');
      if (mins !== null) {
        socket.emit('ban_user', { target: name, minutes: parseInt(mins) || 0 });
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
  socket.emit('get_stats');
  socket.emit('list_sensitive_words');
  socket.emit('get_announcement');
  socket.emit('get_room_config');
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
  // 确保 users 中有该用户且头像字段已填充（system 事件可能已抢先创建无头像记录）
  if (data.user && data.user !== 'System') {
    const u = users.get(data.user);
    if (!u) {
      users.set(data.user, { name: data.user, sid: '', avatar: data.avatar || '' });
    } else if (data.avatar && !u.avatar) {
      u.avatar = data.avatar;
    }
  }
  appendMsg(data.id, data.user, data.text, 'msg', data.time);
});

socket.on('message_deleted', data => {
  removeMsgElement(data.id);
});

socket.on('message_revoked', data => {
  const el = elements.messages.querySelector(`[data-msg-id="${data.id}"]`);
  if (el) {
    const bubble = el.querySelector('.msg-bubble');
    if (bubble) {
      bubble.innerHTML = '<i style="opacity:0.5">管理员撤回了一条消息</i>';
    }
  }
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

socket.on('announcement', data => {
  if (data.text) {
    elements.announcementBanner.style.display = 'flex';
    elements.annContent.textContent = '📌 ' + data.text;
  }
});

socket.on('announcement_cleared', () => {
  elements.announcementBanner.style.display = 'none';
});

socket.on('room_config', data => {
  elements.cfgRoomName.value = data.room_name || 'Leochat';
  elements.cfgWelcome.value = data.welcome_msg || '';
  elements.cfgMaxMsgLen.value = data.max_msg_len || '2000';
});

socket.on('export_data', data => {
  const blob = new Blob([data.data], { type: data.format === 'json' ? 'application/json' : 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `leochat_export.${data.format}`;
  a.click();
  URL.revokeObjectURL(url);
  showToast('聊天记录已导出');
});

socket.on('sensitive_words', data => {
  const words = data.words || [];
  elements.sensitiveList.innerHTML = words.map(w =>
    `<span class="sensitive-tag" data-word="${esc(w)}">${esc(w)} ×</span>`
  ).join('');
  elements.sensitiveList.querySelectorAll('.sensitive-tag').forEach(tag => {
    tag.addEventListener('click', () => {
      const w = tag.dataset.word;
      if (confirm(`删除敏感词 "${w}"？`)) {
        socket.emit('remove_sensitive_word', { word: w });
      }
    });
  });
});

socket.on('userlist', data => {
  users.clear();
  (data.users || []).forEach(u => users.set(u.name, {
    name: u.name,
    sid: u.sid || '',
    avatar: u.avatar || '',
    ip: u.ip || '',
    connect_time: u.connect_time || '',
    last_msg_time: u.last_msg_time || '',
  }));
  updateUL();
});

socket.on('stats', data => {
  elements.statTodayMsgs.textContent = data.today_msgs ?? 0;
  elements.statTodayVisits.textContent = data.today_visitors ?? 0;
  elements.statTotalMsgs.textContent = data.total_msgs ?? 0;
  elements.statTotalUsers.textContent = data.total_users ?? 0;
});

socket.on('messages_page', data => {
  if (data.offset === 0) {
    // New search — clear existing messages
    elements.messages.querySelectorAll('.msg-row,.msg-system').forEach(el => el.remove());
    historyOffset = 0;
  }
  const msgs = data.messages || [];
  historyTotal = data.total || 0;
  historyOffset = (data.offset || 0) + msgs.length;
  // Prepend messages at the top (they're older)
  const frag = document.createDocumentFragment();
  // Insert in correct order (oldest first, which is the order from server)
  for (const m of msgs) {
    // Store avatar for rendering
    if (m.user && m.avatar && !users.has(m.user)) {
      users.set(m.user, { name: m.user, sid: '', avatar: m.avatar });
    }
    // Build a temporary row and append to fragment
    const tmp = elements.messages.appendChild.bind(elements.messages);
  }
  // Actually, we need to prepend. Let's build in order and prepend.
  msgs.forEach(m => appendSearchMsg(m));
  elements.loadMoreBtn.style.display = historyOffset < historyTotal ? '' : 'none';
  // Scroll to show where we are (first prepended message)
  if (msgs.length > 0 && data.offset > 0) {
    const firstPrepended = elements.messages.querySelector(`[data-msg-id="${msgs[0].id}"]`);
    if (firstPrepended) firstPrepended.scrollIntoView({ block: 'center' });
  }
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

elements.searchBtn.addEventListener('click', () => doSearch(true));
elements.loadMoreBtn.addEventListener('click', () => loadMore());

elements.searchKeyword.addEventListener('keydown', e => {
  if (e.key === 'Enter') doSearch(true);
});
elements.searchUser.addEventListener('keydown', e => {
  if (e.key === 'Enter') doSearch(true);
});

elements.sensitiveAddBtn.addEventListener('click', () => {
  const word = elements.sensitiveInput.value.trim();
  if (!word) return;
  socket.emit('add_sensitive_word', { word });
  elements.sensitiveInput.value = '';
});

elements.sensitiveInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') {
    const word = elements.sensitiveInput.value.trim();
    if (!word) return;
    socket.emit('add_sensitive_word', { word });
    elements.sensitiveInput.value = '';
  }
});

// ── 置顶公告 ─────────────────────────────────────────

elements.pinAnnBtn.addEventListener('click', () => {
  const text = elements.broadcast.value.trim();
  if (!text) { showToast('请先在广播栏输入公告内容'); return; }
  socket.emit('set_announcement', { text });
  elements.broadcast.value = '';
  showToast('公告已置顶');
});

elements.annClear.addEventListener('click', () => {
  if (confirm('确定要清除置顶公告吗？')) {
    socket.emit('clear_announcement');
  }
});

// ── 房间设置 ─────────────────────────────────────────

elements.settingsBtn.addEventListener('click', () => {
  socket.emit('get_room_config');
  elements.settingsModal.style.display = 'flex';
});

elements.cfgCancelBtn.addEventListener('click', () => {
  elements.settingsModal.style.display = 'none';
});

elements.settingsModal.addEventListener('click', e => {
  if (e.target === elements.settingsModal) {
    elements.settingsModal.style.display = 'none';
  }
});

elements.cfgSaveBtn.addEventListener('click', () => {
  const settings = [
    { key: 'room_name', value: elements.cfgRoomName.value.trim() },
    { key: 'welcome_msg', value: elements.cfgWelcome.value.trim() },
    { key: 'max_msg_len', value: elements.cfgMaxMsgLen.value.trim() || '2000' },
  ];
  settings.forEach(s => { if (s.value) socket.emit('set_room_config', s); });
  elements.settingsModal.style.display = 'none';
  showToast('设置已保存');
});

// ── 导出 ─────────────────────────────────────────────

elements.exportBtn.addEventListener('click', () => {
  const fmt = confirm('确定导出为 JSON 格式？\n(取消则导出 TXT)') ? 'json' : 'txt';
  socket.emit('export_chat', { format: fmt });
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
