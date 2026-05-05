import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:socket_io_client/socket_io_client.dart' as IO;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

// 默认值从环境变量读取
const String defaultIp = String.fromEnvironment('SERVER_IP', defaultValue: '192.168.1.45');
const String defaultPort = String.fromEnvironment('SERVER_PORT', defaultValue: '5000');
String kServerUrl = 'http://$defaultIp:$defaultPort';

final FlutterLocalNotificationsPlugin flutterLocalNotificationsPlugin = FlutterLocalNotificationsPlugin();

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  // 初始化本地通知
  const AndroidInitializationSettings initializationSettingsAndroid = AndroidInitializationSettings('@mipmap/ic_launcher');
  const InitializationSettings initializationSettings = InitializationSettings(android: initializationSettingsAndroid);
  await flutterLocalNotificationsPlugin.initialize(
    settings: initializationSettings,
  );

  // 加载保存的服务器地址
  final prefs = await SharedPreferences.getInstance();
  final savedUrl = prefs.getString('server_url');
  if (savedUrl != null && savedUrl.isNotEmpty) {
    kServerUrl = savedUrl;
  }

  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.dark,
  ));
  runApp(const LeochatApp());
}

class LeochatApp extends StatelessWidget {
  const LeochatApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Leochat',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF6366F1),
          primary: const Color(0xFF6366F1),
          secondary: const Color(0xFFF43F5E),
        ),
        fontFamily: 'Roboto',
      ),
      home: const UsernameScreen(),
    );
  }
}

// ── 全局头像构建工具 ────────────────────────────────────────────
Widget buildAvatarWidget(String name, String avatarUrl, double size) {
  Widget fallback() {
    return CircleAvatar(
      radius: size / 2,
      backgroundColor: Color((name.hashCode * 0xFFFFFF).toInt()).withOpacity(1.0).withBlue(200),
      child: Text(
        name.isNotEmpty ? name.substring(0, 1).toUpperCase() : 'A',
        style: TextStyle(color: Colors.white, fontSize: size * 0.4, fontWeight: FontWeight.bold),
      ),
    );
  }

  if (avatarUrl.isNotEmpty) {
    return ClipOval(
      child: Image.network(
        '$kServerUrl/static/avatars/$avatarUrl',
        width: size,
        height: size,
        fit: BoxFit.cover,
        errorBuilder: (context, error, stackTrace) => fallback(),
        loadingBuilder: (context, child, loadingProgress) {
          if (loadingProgress == null) return child;
          return fallback();
        },
      ),
    );
  }
  return fallback();
}

// ── 现代化的登录界面 ────────────────────────────────────────────

class UsernameScreen extends StatefulWidget {
  const UsernameScreen({super.key});

  @override
  State<UsernameScreen> createState() => _UsernameScreenState();
}

class _UsernameScreenState extends State<UsernameScreen> {
  final TextEditingController _controller = TextEditingController();

  void _showSettings() {
    final uri = Uri.tryParse(kServerUrl) ?? Uri.parse('http://192.168.1.45:5000');
    final ipController = TextEditingController(text: uri.host);
    final portController = TextEditingController(text: uri.port == 0 ? '5000' : uri.port.toString());

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Server Settings'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: ipController,
              decoration: const InputDecoration(
                labelText: 'Server IP',
                hintText: '192.168.1.45',
              ),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: portController,
              decoration: const InputDecoration(
                labelText: 'Server Port',
                hintText: '5000',
              ),
              keyboardType: TextInputType.number,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () async {
              final ip = ipController.text.trim();
              final port = portController.text.trim();
              if (ip.isNotEmpty && port.isNotEmpty) {
                final newUrl = 'http://$ip:$port';
                final prefs = await SharedPreferences.getInstance();
                await prefs.setString('server_url', newUrl);
                setState(() {
                  kServerUrl = newUrl;
                });
                if (context.mounted) Navigator.pop(context);
              }
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        children: [
          // 背景渐变
          Positioned.fill(
            child: Container(
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [Color(0xFFEEF2FF), Color(0xFFE0E7FF), Color(0xFFC7D2FE)],
                ),
              ),
            ),
          ),
          // 装饰圆圈
          Positioned(
            top: -50,
            right: -50,
            child: CircleAvatar(radius: 100, backgroundColor: Colors.white.withOpacity(0.3)),
          ),
          // 设置按钮
          Positioned(
            top: MediaQuery.of(context).padding.top + 10,
            right: 10,
            child: IconButton(
              icon: const Icon(Icons.settings, color: Color(0xFF6366F1)),
              onPressed: _showSettings,
            ),
          ),
          Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(32),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  // Logo
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: const Color(0xFF6366F1).withOpacity(0.2),
                          blurRadius: 20,
                          offset: const Offset(0, 10),
                        )
                      ],
                    ),
                    child: const Icon(Icons.auto_awesome, size: 60, color: Color(0xFF6366F1)),
                  ),
                  const SizedBox(height: 24),
                  const Text(
                    'Leochat',
                    style: TextStyle(fontSize: 32, fontWeight: FontWeight.w900, letterSpacing: -1, color: Color(0xFF1E293B)),
                  ),
                  const Text(
                    'Connect with the world',
                    style: TextStyle(fontSize: 16, color: Color(0xFF64748B)),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'Server: $kServerUrl',
                    style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                  ),
                  const SizedBox(height: 36),
                  // 输入框
                  Container(
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(20),
                      boxShadow: [
                        BoxShadow(color: Colors.black.withOpacity(0.05), blurRadius: 15, offset: const Offset(0, 5))
                      ],
                    ),
                    child: TextField(
                      controller: _controller,
                      decoration: const InputDecoration(
                        hintText: 'Your nickname',
                        prefixIcon: Icon(Icons.person_outline),
                        border: InputBorder.none,
                        contentPadding: EdgeInsets.symmetric(horizontal: 20, vertical: 18),
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),
                  // 按钮
                  SizedBox(
                    width: double.infinity,
                    height: 60,
                    child: ElevatedButton(
                      onPressed: () {
                        final name = _controller.text.trim();
                        if (name.isEmpty) return;
                        Navigator.push(context, MaterialPageRoute(builder: (_) => ChatScreen(username: name)));
                      },
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF6366F1),
                        foregroundColor: Colors.white,
                        shape: RoundedRectangleType(borderRadius: BorderRadius.circular(20)),
                        elevation: 0,
                      ),
                      child: const Text('Start Chatting', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ── 现代化的聊天界面 ────────────────────────────────────────────

class ChatScreen extends StatefulWidget {
  final String username;
  const ChatScreen({super.key, required this.username});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> with WidgetsBindingObserver {
  late IO.Socket _socket;
  final List<Map<String, dynamic>> _messages = [];
  final Map<String, String> _userAvatars = {};
  List<Map<String, dynamic>> _onlineUsersList = [];
  
  final TextEditingController _msgCtrl = TextEditingController();
  final ScrollController _scrollCtrl = ScrollController();
  
  bool _connected = false;
  int _onlineCount = 0;
  String? _errorText;
  String? _announcementText;
  
  bool _isMuted = false;
  bool _isBackground = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _requestNotificationPermission();
    _loadMuteState();
    _connect();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _socket.dispose();
    _msgCtrl.dispose();
    _scrollCtrl.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _isBackground = state == AppLifecycleState.paused || 
                    state == AppLifecycleState.inactive || 
                    state == AppLifecycleState.hidden;
  }

  Future<void> _requestNotificationPermission() async {
    final AndroidFlutterLocalNotificationsPlugin? androidImplementation =
        flutterLocalNotificationsPlugin.resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>();
    await androidImplementation?.requestNotificationsPermission();
  }

  Future<void> _loadMuteState() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _isMuted = prefs.getBool('is_muted') ?? false;
    });
  }

  Future<void> _toggleMute() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _isMuted = !_isMuted;
    });
    await prefs.setBool('is_muted', _isMuted);
  }

  Future<void> _showNotification(String title, String body) async {
    if (_isMuted) return;
    const AndroidNotificationDetails androidDetails = AndroidNotificationDetails(
      'leochat_channel', 
      'LeoChat Messages',
      channelDescription: 'Notifications for new chat messages',
      importance: Importance.max,
      priority: Priority.high,
      playSound: true,
      enableVibration: true,
      fullScreenIntent: true, // 点亮屏幕
    );
    const NotificationDetails platformDetails = NotificationDetails(android: androidDetails);
    await flutterLocalNotificationsPlugin.show(
      id: DateTime.now().millisecondsSinceEpoch % 100000, 
      title: title, 
      body: body, 
      notificationDetails: platformDetails
    );
  }

  void _connect() {
    debugPrint("Attempting to connect to: $kServerUrl");
    _socket = IO.io(kServerUrl, {
      'transports': ['websocket'],
      'autoConnect': false,
    });

    _socket.onConnect((_) {
      if (mounted) setState(() => _connected = true);
      _socket.emit('join', {'user': widget.username});
    });
    
    _socket.onConnectError((data) => debugPrint('Connect Error: $data'));
    _socket.onConnectTimeout((data) => debugPrint('Connect Timeout: $data'));
    _socket.onError((data) => debugPrint('Socket Error: $data'));
    _socket.onDisconnect((_) {
      if (mounted) setState(() => _connected = false);
    });

    _socket.on('message', (data) {
      if (data is Map && mounted) {
        setState(() {
          final isDuplicate = _messages.any((m) =>
            m['user'] == data['user'] &&
            m['text'] == data['text'] &&
            m['time'] == data['time']
          );
          if (!isDuplicate) {
            _messages.insert(0, Map<String, dynamic>.from(data));
          }
          if (data['user'] != null && data['avatar'] != null && data['avatar'].toString().isNotEmpty) {
            _userAvatars[data['user'].toString()] = data['avatar'].toString();
          }
        });
        
        // 收到他人消息且在后台时，发送通知
        if (_isBackground && data['user'] != widget.username) {
          _showNotification(data['user']?.toString() ?? 'Message', data['text']?.toString() ?? '');
        }
        
        _scrollToBottom();
      }
    });
    
    _socket.on('system', (data) {
      if (data is Map && mounted) {
        setState(() => _messages.insert(0, {'user': 'System', 'text': data['text'], 'isSystem': true}));
        _scrollToBottom();
      }
    });
    
    _socket.on('userlist', (data) {
      if (data is Map && mounted) {
        setState(() {
          final users = (data['users'] as List? ?? []);
          _onlineUsersList = List<Map<String, dynamic>>.from(users);
          _onlineCount = users.length;
          for (final u in users) {
            if (u is Map && u['name'] != null && u['avatar'] != null && u['avatar'].toString().isNotEmpty) {
              _userAvatars[u['name'].toString()] = u['avatar'].toString();
            }
          }
        });
      }
    });
    
    _socket.on('message_deleted', (data) {
      if (data is Map && mounted) {
        setState(() {
          _messages.removeWhere((m) => m['id'] == data['id']);
        });
      }
    });
    
    _socket.on('message_revoked', (data) {
      if (data is Map && mounted) {
        setState(() {
          final idx = _messages.indexWhere((m) => m['id'] == data['id']);
          if (idx != -1) {
            _messages[idx] = Map<String, dynamic>.from(_messages[idx])
              ..['text'] = '管理员撤回了一条消息'
              ..['revoked'] = true;
          }
        });
      }
    });
    
    _socket.on('error', (data) {
      if (data is Map && mounted) {
        setState(() => _errorText = data['text']?.toString() ?? 'Error');
      }
    });
    
    _socket.on('announcement', (data) {
      if (data is Map && mounted) {
        setState(() => _announcementText = data['text']?.toString() ?? '');
      }
    });
    
    _socket.on('announcement_cleared', (_) {
      if (mounted) setState(() => _announcementText = null);
    });
    
    _socket.connect();
  }

  void _sendMessage() {
    final text = _msgCtrl.text.trim();
    if (text.isEmpty) return;
    _socket.emit('send_message', {'text': text}); 
    _msgCtrl.clear();
  }

  void _scrollToBottom() {
    Future.delayed(const Duration(milliseconds: 100), () {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(0, duration: const Duration(milliseconds: 300), curve: Curves.easeOut);
      }
    });
  }

  void _showOnlineUsers() {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.white,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (context) {
        return SafeArea(
          child: ConstrainedBox(
            constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.7),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const SizedBox(height: 12),
                Container(width: 40, height: 4, decoration: BoxDecoration(color: Colors.grey.shade300, borderRadius: BorderRadius.circular(2))),
                const SizedBox(height: 16),
                Text('当前在线 (${_onlineUsersList.length}人)', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                const Divider(height: 32),
                Flexible(
                  child: ListView.builder(
                    shrinkWrap: true,
                    itemCount: _onlineUsersList.length,
                    itemBuilder: (context, index) {
                      final u = _onlineUsersList[index];
                      final name = u['name']?.toString() ?? 'Unknown';
                      final avatarUrl = u['avatar']?.toString() ?? '';
                      return ListTile(
                        leading: buildAvatarWidget(name, avatarUrl, 40),
                        title: Text(name, style: const TextStyle(fontWeight: FontWeight.w600)),
                      );
                    },
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_errorText != null) {
      final text = _errorText!;
      _errorText = null;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(text), backgroundColor: Colors.red.shade700),
          );
        }
      });
    }
    
    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        backgroundColor: Colors.white,
        elevation: 0,
        // 左侧默认返回按钮，或者你可以自定义
        leading: const BackButton(color: Colors.black87),
        // 绝对居中的标题
        centerTitle: true,
        title: GestureDetector(
          onTap: _showOnlineUsers,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Leochat', style: TextStyle(fontWeight: FontWeight.w900, color: Color(0xFF1E293B), fontSize: 18)),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 8, height: 8,
                    decoration: BoxDecoration(color: _connected ? Colors.green : Colors.red, shape: BoxShape.circle),
                  ),
                  const SizedBox(width: 6),
                  Text(
                    _connected ? '$_onlineCount 人在线' : 'Connecting...', 
                    style: TextStyle(fontSize: 12, color: Colors.grey.shade600)
                  ),
                ],
              ),
            ],
          ),
        ),
        // 右侧静音按钮
        actions: [
          IconButton(
            icon: Icon(
              _isMuted ? Icons.notifications_off : Icons.notifications_active, 
              color: _isMuted ? Colors.grey : const Color(0xFF6366F1)
            ),
            onPressed: _toggleMute,
            tooltip: _isMuted ? '取消静音' : '静音通知',
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: Column(
        children: [
          if (_announcementText != null)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              color: Colors.amber.shade100,
              child: Row(
                children: [
                  const Text('📌 ', style: TextStyle(fontSize: 14)),
                  Expanded(
                    child: Text(
                      _announcementText!,
                      style: TextStyle(fontSize: 13, color: Colors.amber.shade900),
                    ),
                  ),
                ],
              ),
            ),
          Expanded(
            child: ListView.builder(
              reverse: true,
              controller: _scrollCtrl,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
              itemCount: _messages.length,
              itemBuilder: (ctx, i) {
                final msg = _messages[i];
                if (msg['isSystem'] == true) {
                  return Center(
                    child: Container(
                      margin: const EdgeInsets.symmetric(vertical: 12),
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                      decoration: BoxDecoration(color: Colors.black.withOpacity(0.05), borderRadius: BorderRadius.circular(20)),
                      child: Text(msg['text'], style: const TextStyle(fontSize: 12, color: Colors.blueGrey)),
                    ),
                  );
                }
                final isMe = msg['user'] == widget.username;
                final avatarFile = _userAvatars[msg['user']] ?? '';
                return _MessageBubble(message: msg, isMe: isMe, avatarUrl: avatarFile);
              },
            ),
          ),
          _buildInputArea(),
        ],
      ),
    );
  }

  Widget _buildInputArea() {
    return Container(
      padding: EdgeInsets.fromLTRB(16, 8, 16, MediaQuery.of(context).padding.bottom + 8),
      decoration: const BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.vertical(top: Radius.circular(30)),
        boxShadow: [BoxShadow(color: Colors.black12, blurRadius: 10)],
      ),
      child: Row(
        children: [
          Expanded(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              decoration: BoxDecoration(color: const Color(0xFFF1F5F9), borderRadius: BorderRadius.circular(25)),
              child: TextField(
                controller: _msgCtrl,
                minLines: 1,
                maxLines: 5,
                textInputAction: TextInputAction.newline,
                decoration: const InputDecoration(hintText: 'Type message...', border: InputBorder.none),
                onSubmitted: (_) => _sendMessage(),
              ),
            ),
          ),
          const SizedBox(width: 12),
          GestureDetector(
            onTap: _connected ? _sendMessage : null,
            child: Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: _connected ? const Color(0xFF6366F1) : Colors.grey.shade400,
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.send_rounded, color: Colors.white, size: 24),
            ),
          ),
        ],
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  final Map<String, dynamic> message;
  final bool isMe;
  final String avatarUrl;

  const _MessageBubble({required this.message, required this.isMe, this.avatarUrl = ''});

  @override
  Widget build(BuildContext context) {
    final name = (message['user'] as String?) ?? 'A';
    final avatar = buildAvatarWidget(name, avatarUrl, 36);
    
    final nameWidget = Padding(
      padding: EdgeInsets.only(
        left: isMe ? 0 : 4,
        right: isMe ? 4 : 0,
        bottom: 4,
      ),
      child: Text(
        message['user'] ?? 'Unknown',
        style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: Colors.black54),
      ),
    );
    final bubble = Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        gradient: isMe ? const LinearGradient(colors: [Color(0xFF6366F1), Color(0xFF818CF8)]) : null,
        color: isMe ? null : Colors.white,
        borderRadius: BorderRadius.only(
          topLeft: const Radius.circular(20),
          topRight: const Radius.circular(20),
          bottomLeft: Radius.circular(isMe ? 20 : 0),
          bottomRight: Radius.circular(isMe ? 0 : 20),
        ),
        boxShadow: [
          BoxShadow(
            color: isMe ? const Color(0xFF6366F1).withOpacity(0.3) : Colors.black.withOpacity(0.03),
            blurRadius: 10,
            offset: const Offset(0, 5),
          )
        ],
      ),
      child: Text(
        message['text'] ?? '',
        style: TextStyle(
          color: isMe ? Colors.white : const Color(0xFF1E293B),
          fontSize: 16,
          fontStyle: message['revoked'] == true ? FontStyle.italic : FontStyle.normal,
        ),
      ),
    );

    final content = Flexible(
      child: Column(
        crossAxisAlignment: isMe ? CrossAxisAlignment.end : CrossAxisAlignment.start,
        children: [nameWidget, bubble],
      ),
    );

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        mainAxisAlignment: isMe ? MainAxisAlignment.end : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: isMe ? [content, const SizedBox(width: 8), avatar] : [avatar, const SizedBox(width: 8), content],
      ),
    );
  }
}

// 辅助类用于圆角按钮
class RoundedRectangleType extends OutlinedBorder {
  final BorderRadius borderRadius;
  const RoundedRectangleType({this.borderRadius = BorderRadius.zero});
  @override
  OutlinedBorder copyWith({BorderSide? side}) => this;
  @override
  Path getInnerPath(Rect rect, {TextDirection? textDirection}) => Path()..addRRect(borderRadius.resolve(textDirection).toRRect(rect));
  @override
  Path getOuterPath(Rect rect, {TextDirection? textDirection}) => Path()..addRRect(borderRadius.resolve(textDirection).toRRect(rect));
  @override
  void paint(Canvas canvas, Rect rect, {TextDirection? textDirection}) {}
  @override
  ShapeBorder scale(double t) => this;
}