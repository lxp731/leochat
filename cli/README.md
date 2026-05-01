# Leochat CLI

基于 prompt_toolkit 的全屏 TUI 聊天客户端。

## 快速开始

```bash
cd cli
uv sync
uv run python app.py
```

首次运行会进入配置向导，输入昵称和服务器地址后自动保存。之后启动直达聊天界面。

## 配置

配置文件位于 `~/.config/leochat/config.toml`：

```toml
[user]
name = "Burgess"

[server]
host = "127.0.0.1"
port = 5000
```

配置优先级（高 → 低）：

```
CLI 参数 > 环境变量 > config.toml > 内置默认值
```

### CLI 参数

```bash
python app.py -s 192.168.1.100:5000   # 指定服务器
python app.py -u guest                 # 指定用户名
python app.py -h                       # 查看所有选项
```

### 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `LEOCHAT_SERVER` | 服务器地址 | `192.168.1.100:5000` |
| `LEOCHAT_USER` | 用户名 | `Burgess` |

## 聊天命令

| 命令 | 作用 |
|------|------|
| `/exit` `/quit` | 退出 |
| `/users` | 显示在线用户 |
| `/help` | 帮助 |
| `Ctrl+C` / `Ctrl+D` | 退出 |

## 打包为二进制

```bash
uv run python -m nuitka --standalone --onefile app.py
```

打包后修改配置只需编辑 `~/.config/leochat/config.toml`，无需重新编译。

## 效果图

![cli-result](./assets/result.png)
