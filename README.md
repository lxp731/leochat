# ChatRoom

多端实时聊天室，Monorepo。

```
chatroom/
├── server/    # Python 后端服务
├── android/   # Flutter 移动客户端（Android/Web）
└── cli/       # Python CLI 客户端
```

## 快速开始

```bash
# 启动服务端
cd server && docker compose up -d

# CLI 客户端
cd cli && python app.py

# Android 客户端
cd android && flutter run
```
