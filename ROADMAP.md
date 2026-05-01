# Leochat — 项目路线图

> 轻量级自托管实时聊天室，支持 Web（管理后台）/ CLI / Android 三端接入。

---

## 基本信息

| 项目 | 详情 |
|------|------|
| **应用名称** | Leochat |
| **技术栈** | Python (Flask + Socket.IO), Flutter (Dart), prompt_toolkit |
| **协议** | Socket.IO (WebSocket) |
| **部署方案** | Docker + docker-compose |
| **当前状态** | 管理后台 Layer 1 实施中 |

---

## 功能清单

### ✅ 已实现 (Done)

#### 服务端
- [x] Flask + Socket.IO 实时消息广播
- [x] 速率限制（基于 IP，2秒窗口内最多10条消息）
- [x] 在线用户列表与加入/离开通知
- [x] CST 时区支持
- [x] Docker 部署支持（环境变量注入，配置不进镜像）
- [x] SQLite 数据持久化（用户与消息历史）
- [x] 消息身份验证（基于 SID 强制绑定，防止冒充）
- [x] 服务端统一生成消息时间戳
- [x] Web 管理后台密码锁（WEB_PASSWORD 环境变量）

#### CLI 客户端
- [x] prompt_toolkit 全屏 TUI
- [x] 消息手动视口管理（解决 ScrollablePane 不滚动 bug）
- [x] 消息对齐算法（动态用户名宽度计算 + CJK 宽度感知）
- [x] 系统消息与通知显示
- [x] 命令支持：`/users` `/exit` `/help`
- [x] Nerd Font 图标美化
- [x] 自动重连支持（带指数退避）
- [x] 配置文件系统（~/.config/leochat/config.toml，支持 CLI 参数/环境变量覆盖）

#### Android 客户端
- [x] Modern 登录界面（渐变背景 + 装饰元素）
- [x] 聊天气泡（发送/接收差异化样式）
- [x] 头像自动上色（基于用户名 hash）
- [x] WebSocket 实时通信
- [x] 系统消息显示
- [x] 动态服务器地址设置（持久化存储）
- [x] 退出登录 / 切换用户功能

---

## Web 管理后台路线图

### ✅ Layer 1 — 即时管控（已完成）

- [x] **删除消息** — 每条消息旁 × 按钮，管理员可移除任意消息，广播 `message_deleted` 事件
- [x] **踢人** — 用户列表旁 🚫 按钮，强制断开目标 Socket.IO 连接
- [x] **系统广播** — 顶部广播栏，管理员发系统公告，全局实时推送

### 📋 Layer 2 — 数据面板

- [ ] **消息日志** — 分页浏览历史消息，按用户名筛选
- [ ] **统计卡片** — 在线人数、今日消息数、历史消息总数
- [ ] **用户活跃度** — 谁发了多少消息、最近活跃时间

### 🏗️ Layer 3 — 完整后台

- [ ] **封禁管理** — IP 黑名单持久化
- [ ] **消息搜索** — 全文搜索历史消息
- [ ] **日志导出** — CSV/JSON 导出

---

## 技术债务与缺陷修复

### 🛡️ P0 — 阻塞上线级

- [x] **服务端添加数据持久化** — SQLite 存储。
- [x] **修复 Socket.IO 速率限制绕过漏洞** — 按 IP 地址限速。
- [x] **修复服务端消息身份伪造漏洞** — 服务端强制使用 session 绑定的用户名。
- [x] **修复 Flask debug 模式安全隐患** — `allow_unsafe_werkzeug=True`。
- [x] **Web 管理后台加锁** — WEB_PASSWORD + session 鉴权。
- [ ] **锁定 Docker 镜像 Python 版本** — 当前使用 `python:3.14.4-slim`（预发布），应切换到 `python:3.12-slim` 稳定版并生成 `uv.lock`。
- [ ] **移除 CLI Dockerfile 硬编码国内镜像源** — `sed` 硬编码清华源，在国际服务器不可达。镜像源应通过 `--build-arg` 注入。

### 🟡 P1 — 影响体验级

- [x] **CLI 客户端添加自动重连** — 已启用。
- [x] **CLI 消息滚动修复** — 替换 ScrollablePane 为手动视口管理。
- [x] **CLI 配置文件系统** — ~/.config/leochat/config.toml，支持多层优先级覆盖。
- [x] **Web 端 CDN 地址修复** — socket_io.min.js → socket.io.min.js。
- [x] **Android 客户端支持动态服务器地址** — shared_preferences 持久化。
- [x] **Android 客户端 logout / 切换用户** — 已添加退出按钮。
- [ ] **CLI 消息区虚拟滚动** — 长时间聊天（上千条）需行级虚拟化。

### 🟢 P2 — 安全加固与优化

- [ ] **Docker healthcheck** — 容器假活但 Socket.IO 已不可用。
- [ ] **Web 端自托管字体** — 当前通过 Google Fonts CDN 加载 Inter，离线环境白屏。
- [ ] **Web 端 CST 时间戳** — 当前客户端 JS 格式化时间，应统一 CST。

---

## 待办 (Planned)

- [ ] **多房间支持** — 创建/加入不同频道。
- [ ] **私信功能** — 用户间直接私密消息。
- [ ] **文件/图片分享** — 上传和预览。
- [ ] **消息搜索** — 全文搜索历史消息（管理后台 Layer 3）。

### ❌ 不做 (Out of Scope)

- ~~端到端加密~~（轻量自托管场景，不需要）
- ~~语音/视频通话~~
- ~~OAuth/第三方登录~~

---

## 进度追踪 (Phase View)

### Phase 1: 核心链路交付 ✅
- [x] Flask + Socket.IO 服务端
- [x] Web 端聊天界面
- [x] CLI 终端客户端
- [x] Android Flutter 客户端

### Phase 2: 安全加固与稳定性 ✅
- [x] 身份校验修复
- [x] 速率限制修复
- [x] 数据持久化 (SQLite)
- [x] 客户端重连与动态配置
- [x] Web 管理后台密码锁
- [x] CLI 配置文件系统

### Phase 3: 管理后台 Layer 1 ✅
- [x] 消息删除
- [x] 踢人
- [x] 系统广播

### Phase 4: 管理后台 Layer 2+ / 多房间
- [ ] 数据面板（日志/统计/活跃度）
- [ ] 多房间支持
- [ ] 私信功能
