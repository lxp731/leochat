# Leochat Server

Flask + Socket.IO 实时聊天服务器。

## 启动

开发环境启动：
```bash
cd server
uv sync
uv run python app.py
```

生产环境启动 (Gunicorn + Gevent)：
```bash
cd server
uv sync
uv run gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 -b 0.0.0.0:5000 app:app
```

服务运行在 `http://0.0.0.0:5000`，浏览器打开即可使用 Web 客户端。

## Docker

```bash
docker compose up -d
```

## 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `SECRET_KEY` | 随机 | Flask 密钥 |
| `CHAT_PORT` | `5000` | 监听端口 |
| `CHAT_DEBUG` | `false` | 调试模式 |

## API

Socket.IO 事件协议见项目根目录 [README](../README.md#协议设计)。

## 效果图

![server-result](../assets/server/result.png)
