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
| **当前状态** | 基础功能已实现，部分关键技术债务已修复 |

---

## 功能清单

### ✅ 已实现 (Done)

#### 服务端
- [x] Flask + Socket.IO 实时消息广播
- [x] 速率限制（基于 IP，2秒窗口内最多5条消息）
- [x] 在线用户列表与加入/离开通知
- [x] CST 时区支持
- [x] Docker 部署支持
- [x] Web 端聊天界面
- [x] SQLite 数据持久化（用户与消息历史）
- [x] 消息身份验证（基于 SID 强制绑定，防止冒充）
- [x] 服务端统一生成消息时间戳

#### CLI 客户端
- [x] prompt_toolkit 全屏 TUI
- [x] 消息对齐算法（动态用户名宽度计算）
- [x] 系统消息与通知显示
- [x] 命令支持：`/users` `/exit` `/help`
- [x] Nerd Font 图标美化
- [x] 自动重连支持（带指数退避）

#### Android 客户端
- [x] Modern 登录界面（渐变背景 + 装饰元素）
- [x] 聊天气泡（发送/接收差异化样式）
- [x] 头像自动上色（基于用户名 hash）
- [x] WebSocket 实时通信
- [x] 系统消息显示
- [x] 动态服务器地址设置（持久化存储）
- [x] 退出登录 / 切换用户功能

---

## 技术债务与缺陷修复（按优先级排序）

### 🛡️ P0 — 阻塞上线级

- [x] **服务端添加数据持久化** — 已引入 SQLite 存储用户信息与消息历史。
- [x] **修复 Socket.IO 速率限制绕过漏洞** — 已改为按 IP 地址限速。
- [x] **修复服务端消息身份伪造漏洞** — 服务端已强制使用 session 绑定的用户名。
- [x] **修复 Flask debug 模式安全隐患** — `allow_unsafe_werkzeug` 已与 `CHAT_DEBUG` 环境变量联动。
- [ ] **锁定 Docker 镜像 Python 版本** — `server/Dockerfile` 使用 `python:3.14.4-slim`（预发布版本）且 `uv sync` 不生成 lockfile，依赖版本浮动。应切换到 `python:3.12-slim` 稳定版，并生成 `uv.lock`。
- [ ] **移除 CLI Dockerfile 中的硬编码国内镜像源** — `sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g'` 硬编码清华源，在国际服务器上不可达。镜像源应通过构建参数 `--build-arg` 注入或直接在基础镜像中配置。

### 🟡 P1 — 影响体验级

- [x] **CLI 客户端添加自动重连** — 已启用自动重连逻辑。
- [ ] **CLI 消息区添加虚拟滚动** — 当前 `ScrollablePane` + `FormattedTextControl` 直接渲染全部消息，长时间聊天（上千条）会导致 UI 越来越卡。应实现行级虚拟化渲染。
- [x] **Android 客户端支持动态服务器地址** — 已添加设置界面并使用 shared_preferences 持久化。
- [x] **Web 前端添加 Subresource Integrity (SRI)** — 已为 Socket.IO 脚本添加 integrity 校验。
- [x] **消息时间戳改为服务端生成** — 服务端已统一接管时间戳生成。
- [x] **Android 客户端 logout / 切换用户** — 已在 AppBar 添加退出按钮。

### 🟢 P2 — 安全加固与优化

- [ ] **Web 前端自托管字体** — 当前通过 Google Fonts CDN 加载 Inter 字体，离线环境或无互联网时会造成页面长时间白屏。应将字体静态文件放入 `static/fonts/` 并使用 `font-display: swap`。
- [x] **CLI docker-compose 移除 `network_mode: host`** — 已切换到默认的 bridge 网络以提高隔离性。
- [x] **添加消息持久化到服务端** — 已实现，新加入的用户会自动同步最近的历史消息。
- [ ] **添加 Docker healthcheck** — `docker-compose.yaml` 缺少健康检查，容器可能假活但 Socket.IO 已不可用。
- [ ] **Web 端添加 CST 时间戳显示** — 当前 Web 端消息由客户端 JS 格式化时间，应统一使用 CST 时区。

---

## 待办 (Planned)

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

### Phase 2: 安全加固与稳定性 (Completed)
- [x] 身份校验修复
- [x] 速率限制修复
- [x] 数据持久化 (SQLite)
- [x] 客户端重连与动态配置

### Phase 3: 功能丰富化 (Future)
- [ ] 多房间
- [ ] 私信
- [ ] 文件分享
