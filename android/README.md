# ChatRoom Android

Flutter 移动客户端，支持 Android / iOS / Web。

## 启动

```bash
cd android
flutter pub get
flutter run
```

## 配置

服务器地址通过编译常量设置，修改 `lib/main.dart`：

```dart
const String kServerUrl = String.fromEnvironment(
  'CHAT_SERVER',
  defaultValue: 'http://10.0.2.2:5000',  // Android 模拟器 → 宿主机
);
```

或编译时指定：

```bash
flutter run --dart-define=CHAT_SERVER=http://your-server:5000
```

## 依赖

- Flutter SDK ≥ 3.8
- `socket_io_client`
