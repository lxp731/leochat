
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:socket_io_client/socket_io_client.dart' as IO;
import 'dart:math' as math;

const String serverIp = String.fromEnvironment('SERVER_IP', defaultValue: '192.168.1.45');
const String serverPort = String.fromEnvironment('SERVER_PORT', defaultValue: '5000');
const String kServerUrl = 'http://:';

void main() {
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

// ── 现代化的登录界面 ────────────────────────────────────────────

class UsernameScreen extends StatefulWidget {
  const UsernameScreen({super.key});

  @override
  State<UsernameScreen> createState() => _UsernameScreenState();
}

class _UsernameScreenState extends State<UsernameScreen> {
  final TextEditingController _controller = TextEditingController();

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
                  const SizedBox(height: 48),
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

class _ChatScreenState extends State<ChatScreen> {
  late IO.Socket _socket;
  final List<Map<String, dynamic>> _messages = [];
  final TextEditingController _msgCtrl = TextEditingController();
  final ScrollController _scrollCtrl = ScrollController();
  bool _connected = false;

  @override
  void initState() {
    super.initState();
    _connect();
  }

  void _connect() {
    _socket = IO.io(kServerUrl, <String, dynamic>{
      'transports': ['websocket'],
      'autoConnect': false,
    });

    _socket.onConnect((_) => setState(() => _connected = true));
    _socket.onDisconnect((_) => setState(() => _connected = false));
    _socket.on('message', (data) {
      if (data is Map) {
        setState(() => _messages.add(Map<String, dynamic>.from(data)));
        _scrollToBottom();
      }
    });
    _socket.on('system', (data) {
      if (data is Map) {
        setState(() => _messages.add({'user': 'System', 'text': data['text'], 'isSystem': true}));
        _scrollToBottom();
      }
    });
    _socket.connect();
  }

  void _sendMessage() {
    final text = _msgCtrl.text.trim();
    if (text.isEmpty) return;
    _socket.emit('send_message', {'user': widget.username, 'text': text});
    _msgCtrl.clear();
  }

  void _scrollToBottom() {
    Future.delayed(const Duration(milliseconds: 100), () {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(_scrollCtrl.position.maxScrollExtent, duration: const Duration(milliseconds: 300), curve: Curves.easeOut);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        backgroundColor: Colors.white,
        elevation: 0,
        centerTitle: false,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Leochat', style: TextStyle(fontWeight: FontWeight.w900, color: Color(0xFF1E293B))),
            Row(
              children: [
                Container(
                  width: 8, height: 8,
                  decoration: BoxDecoration(color: _connected ? Colors.green : Colors.red, shape: BoxShape.circle),
                ),
                const SizedBox(width: 6),
                Text(_connected ? 'Online' : 'Connecting...', style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
              ],
            ),
          ],
        ),
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
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
                return _MessageBubble(message: msg, isMe: isMe);
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
                decoration: const InputDecoration(hintText: 'Type message...', border: InputBorder.none),
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

  const _MessageBubble({required this.message, required this.isMe});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        mainAxisAlignment: isMe ? MainAxisAlignment.end : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          if (!isMe) _buildAvatar(),
          const SizedBox(width: 8),
          Flexible(
            child: Column(
              crossAxisAlignment: isMe ? CrossAxisAlignment.end : CrossAxisAlignment.start,
              children: [
                if (!isMe)
                  Padding(
                    padding: const EdgeInsets.only(left: 4, bottom: 4),
                    child: Text(message['user'], style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: Colors.black54)),
                  ),
                Container(
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
                      BoxShadow(color: isMe ? const Color(0xFF6366F1).withOpacity(0.3) : Colors.black.withOpacity(0.03), blurRadius: 10, offset: const Offset(0, 5))
                    ],
                  ),
                  child: Text(
                    message['text'],
                    style: TextStyle(color: isMe ? Colors.white : const Color(0xFF1E293B), fontSize: 16),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAvatar() {
    final name = message['user'] as String;
    return CircleAvatar(
      radius: 18,
      backgroundColor: Color((name.hashCode * 0xFFFFFF).toInt()).withOpacity(1.0).withBlue(200),
      child: Text(name.substring(0, 1).toUpperCase(), style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold)),
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
