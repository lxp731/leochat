# Leochat Android

基于 Flutter 开发的 Leochat 移动客户端。

## 快速开始

### 1. 安装依赖

```bash
flutter pub get
```

### 2. 运行

在运行或打包时，你需要通过 `--dart-define` 指定服务器的 IP 地址和端口。

```bash
flutter run --dart-define=SERVER_IP=192.168.1.45 --dart-define=SERVER_PORT=5000
```

*注意：请确保你的安卓设备可以访问到该 IP 地址（通常是局域网 IP）。*

---

## 环境变量配置

移动端通过 Flutter 的环境变量功能在编译时注入服务器配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SERVER_IP` | `192.168.1.45` | 服务器的局域网 IP 地址 |
| `SERVER_PORT` | `5000` | 服务器监听的端口 |

---

## 打包 APK

如果你想生成安装包（APK），可以使用以下命令进行构建：

```bash
flutter build apk --release --dart-define=SERVER_IP=你的服务器IP --dart-define=SERVER_PORT=5000
```

生成的 APK 文件通常位于 `build/app/outputs/flutter-apk/app-release.apk`。

---

## 技术栈

- **Flutter 3.x**
- **socket_io_client**: 用于 WebSocket 通信
- **Material 3**: 现代化 UI 设计
