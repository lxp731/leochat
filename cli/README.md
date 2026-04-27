# ChatRoom CLI

基于 Rich + prompt_toolkit 的终端聊天客户端。

## 启动

```bash
cd cli
uv sync
uv run python app.py
```

输入昵称后即可聊天。

## 命令

| 命令 | 作用 |
|------|------|
| `/exit` `/quit` | 退出 |
| `/users` | 显示在线用户 |
| `/help` | 帮助 |
| `Ctrl+C` | 退出 |

## 配置

| 环境变量 | 默认值 |
|----------|--------|
| `CHAT_SERVER` | `http://127.0.0.1:5000` |
| `SERVER_IP` | `127.0.0.1` |
| `SERVER_PORT` | `5000` |

或在项目根目录创建 `.env` 文件统一配置。

## 效果图

![cli-result](./assets/result.png)
