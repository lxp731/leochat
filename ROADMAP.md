# Leochat — 项目路线图

> 轻量级自托管实时聊天室，支持 Web / CLI / Android 三端接入。

---

## 基本信息

| 项目 | 详情 |
|------|------|
| **应用名称** | Leochat |
| **技术栈** | Python (Flask + Socket.IO), Flutter (Dart), prompt_toolkit |
| **协议** | Socket.IO (WebSocket) |
| **部署方案** | Docker + docker-compose |
| **当前状态** | 基础功能已实现，存在较多技术债务 |

---

## 功能清单

### ✅ 已实现 (Done)

#### 服务端
- [x] Flask + Socket.IO 实时消息广播
- [x] 速率限制（2秒窗口内最多5条消息）
- [x] 在线用户列表与加入/离开通知
- [x] CST 时区支持
- [x] Docker 部署支持
- [x] Web 端聊天界面

#### CLI 客户端
- [x] prompt_toolkit 全屏 TUI
- [x] 消息对齐算法（动态用户名宽度计算）
- [x] 系统消息与通知显示
- [x] 命令支持：`/users` `/exit` `/help`
- [x] Nerd Font 图标美化

#### Android 客户端
- [x] Modern 登录界面（渐变背景 + 装饰元素）
- [x] 聊天气泡（发送/接收差异化样式）
- [x] 头像自动上色（基于用户名 hash）
- [x] WebSocket 实时通信
- [x] 系统消息显示

---

## 技术债务与缺陷修复（按优先级排序）

### 🛡️ P0 — 阻塞上线级

- [ ] **服务端添加数据持久化** — 当前所有状态全在内存中（`_sid_to_user`、`_user_to_sids`、`_client_timestamps`），服务重启即全量丢失。至少需要 SQLite 持久化用户信息，或引入 Redis 作为会话存储。`_client_timestamps` 字典永不清理 stale SID，长期运行会内存泄漏。
- [ ] **修复 Socket.IO 速率限制绕过漏洞** — 速率限制按 SID（连接 ID）计算，不是按 IP 或身份 token。攻击者可通过短时间重连（获取新 SID）重置计数器，轻松绕过限流。应将限流键改为 IP 或用户名。
- [ ] **修复服务端消息身份伪造漏洞** — `send_message` 事件不验证发送者的用户名字段是否与 `_sid_to_user` 中一致。任何人可以通过直接调用 Socket.IO 客户端仿冒在线用户发言。应在服务端忽略客户端传入的 `user` 字段，改为从 `_sid_to_user` 中取得真实用户名。
- [ ] **修复 Flask debug 模式安全隐患** — `socketio.run()` 中 `allow_unsafe_werkzeug=True` 始终启用。配合 `debug=True` 时 Werkzeug 会暴露完整 traceback 和交互式调试器到 `0.0.0.0:5000`。应默认关闭 `allow_unsafe_werkzeug`，仅在开发环境启用。
- [ ] **锁定 Docker 镜像 Python 版本** — `server/Dockerfile` 使用 `python:3.14.4-slim`（预发布版本）且 `uv sync` 不生成 lockfile，依赖版本浮动。应切换到 `python:3.12-slim` 稳定版，并生成 `uv.lock`。
- [ ] **移除 CLI Dockerfile 中的硬编码国内镜像源** — `sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g'` 硬编码清华源，在国际服务器上不可达。镜像源应通过构建参数 `--build-arg` 注入或直接在基础镜像中配置。

### 🟡 P1 — 影响体验级

- [ ] **CLI 客户端添加自动重连** — `socketio.Client(reconnection=False)` 导致一次断线即永久断开，用户必须手动重启。应启用 reconnection 并添加指数退避策略。
- [ ] **CLI 消息区添加虚拟滚动** — 当前 `ScrollablePane` + `FormattedTextControl` 直接渲染全部消息，长时间聊天（上千条）会导致 UI 越来越卡。应实现行级虚拟化渲染。
- [ ] **Android 客户端支持动态服务器地址** — `serverIp` 硬编码默认值 `192.168.1.45`，用户无法在 app 内修改。应添加设置页让用户输入/修改服务器地址，并使用 SharedPreferences 持久化。
- [ ] **Web 前端添加 Subresource Integrity (SRI)** — `socket.io` JS 从 CDN 加载时缺少 integrity hash，存在 supply chain 攻击风险。应添加 `integrity` 属性或自托管 JS。
- [ ] **消息时间戳改为服务端生成** — `send_message` 事件直接信任客户端传入的 `time` 字段，用户可伪造时间。服务端应在收到消息时用 `time.time()` 或 `datetime.now()` 生成真实时间戳。
- [ ] **Android 客户端 logout / 切换用户** — 当前客户端没有退出当前会话并重新输入昵称的功能。

### 🟢 P2 — 安全加固与优化

- [ ] **Web 前端自托管字体** — 当前通过 Google Fonts CDN 加载 Inter 字体，离线环境或无互联网时会造成页面长时间白屏。应将字体静态文件放入 `static/fonts/` 并使用 `font-display: swap`。
- [ ] **CLI docker-compose 移除 `network_mode: host`** — CLI 客户端只需出站连接，不需要 host 网络模式（绕过 Docker 网络隔离）。应使用默认 bridge 网络。
- [ ] **添加消息持久化到服务端** — 新加入的用户看不到历史消息。可将最近 N 条消息缓存在内存/数据库中并在用户 join 时推送。
- [ ] **添加 Docker healthcheck** — `docker-compose.yaml` 缺少健康检查，容器可能假活但 Socket.IO 已不可用。
- [ ] **Web 端添加 CST 时间戳显示** — 当前 Web 端消息由客户端 JS 格式化时间，应统一使用 CST 时区。

---

## 待办 (Planned)

- [ ] **消息持久化存储** — 支持历史消息回看。
- [ ] **多房间支持** — 用户可以创建/加入不同频道的房间。
- [ ] **私信功能** — 用户间直接私密消息。
- [ ] **文件/图片分享** — 支持上传和预览。
- [ ] **消息搜索** — 全文搜索历史消息。

### ❌ 不做 (Out of Scope)

- ~~端到端加密~~（轻量自托管场景，不需要）
- ~~语音/视频通话~~
- ~~OAuth/第三方登录~~

---

## 技术指标

- **服务端**: Python 3.12+, 单进程可承载 ~200 并发 WebSocket 连接
- **消息延迟**: < 50ms (局域网)
- **部署**: Docker 单容器，< 100MB 镜像大小
- **内存占用**: 服务端 < 100MB (空闲)

---

## 进度追踪 (Phase View)

### Phase 1: 核心链路交付 (Completed)
- [x] Flask + Socket.IO 服务端
- [x] Web 端聊天界面
- [x] CLI 终端客户端
- [x] Android Flutter 客户端

### Phase 2: 安全加固与稳定性 (Current)
- [ ] 身份校验修复
- [ ] 速率限制修复
- [ ] 数据持久化
- [ ] Docker 镜像规范化

### Phase 3: 功能丰富化 (Future)
- [ ] 多房间
- [ ] 私信
- [ ] 文件分享
