import 'package:flutter/material.dart';
import 'package:socket_io_client/socket_io_client.dart' as IO;

/// 服务器地址 — 通过 build 参数或环境配置
const String kServerUrl = String.fromEnvironment('CHAT_SERVER', defaultValue: 'http://10.0.2.2:5000');

void main() {
  runApp(const ChatApp());
}

class ChatApp extends StatelessWidget {
  const ChatApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'ChatRoom',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(primarySwatch: Colors.blue),
      home: const UsernameScreen(),
    );
  }
}

// ── 用户名输入 ────────────────────────────────────────────

class UsernameScreen extends StatefulWidget {
  const UsernameScreen({super.key});

  @override
  State<UsernameScreen> createState() => _UsernameScreenState();
}

class _UsernameScreenState extends State<UsernameScreen> {
  final _controller = TextEditingController();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Enter Your Name')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            TextField(
              controller: _controller,
              maxLength: 20,
              decoration: const InputDecoration(
                labelText: 'Username',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 20),
            ElevatedButton(
              onPressed: () {
                final username = _controller.text.trim();
                if (username.isEmpty) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Please enter a username')),
                  );
                  return;
                }
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => ChatScreen(username: username),
                  ),
                );
              },
              child: const Text('Join Chat'),
            ),
          ],
        ),
      ),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }
}

// ── 聊天主界面 ────────────────────────────────────────────

class ChatScreen extends StatefulWidget {
  final String username;
  const ChatScreen({super.key, required this.username});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  late IO.Socket _socket;
  final List<Map<String, dynamic>> _messages = [];
  final _msgCtrl = TextEditingController();
  final _scrollCtrl = ScrollController();
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

    _socket.onConnect((_) {
      if (!mounted) return;
      setState(() => _connected = true);
    });

    _socket.onDisconnect((_) {
      if (!mounted) return;
      setState(() => _connected = false);
    });

    _socket.on('message', (data) {
      if (!mounted) return;
      if (data is Map) {
        setState(() => _messages.add(Map<String, dynamic>.from(data)));
        _scrollToBottom();
      }
    });

    _socket.on('system', (data) {
      if (!mounted) return;
      if (data is Map) {
        setState(() => _messages.add({
          'user': '',
          'text': data['text'] ?? '',
          '_system': true,
        }));
        _scrollToBottom();
      }
    });

    _socket.on('error', (data) {
      if (!mounted) return;
      final text = data is Map ? data['text'] ?? 'Unknown error' : '$data';
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
    });

    _socket.connect();
  }

  void _sendMessage() {
    final text = _msgCtrl.text.trim();
    if (text.isEmpty || !_connected) return;
    _socket.emit('send_message', {'user': widget.username, 'text': text});
    _msgCtrl.clear();
    _scrollToBottom();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  void dispose() {
    _socket.disconnect();
    _socket.dispose();
    _msgCtrl.dispose();
    _scrollCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: true,
      child: Scaffold(
        appBar: AppBar(
          title: Text('Chat — ${widget.username}'),
          actions: [
            Padding(
              padding: const EdgeInsets.only(right: 12),
              child: Icon(
                Icons.circle,
                size: 10,
                color: _connected ? Colors.green : Colors.red,
              ),
            ),
          ],
        ),
        body: Column(
          children: [
            Expanded(
              child: ListView.builder(
                controller: _scrollCtrl,
                itemCount: _messages.length,
                itemBuilder: (ctx, i) {
                  final msg = _messages[i];
                  if (msg['_system'] == true) {
                    return _SystemBubble(text: msg['text'] ?? '');
                  }
                  final isMe = msg['user'] == widget.username;
                  return _MessageBubble(message: msg, isMe: isMe);
                },
              ),
            ),
            const Divider(height: 1),
            _buildInputBar(),
          ],
        ),
      ),
    );
  }

  Widget _buildInputBar() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      color: Colors.white,
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: _msgCtrl,
              maxLength: 2000,
              buildCounter: (_, {required currentLength, maxLength, required isFocused}) => null,
              onSubmitted: (_) => _sendMessage(),
              decoration: InputDecoration(
                hintText: 'Type a message...',
                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(24),
                  borderSide: BorderSide(color: Colors.grey.shade300),
                ),
                filled: true,
                fillColor: Colors.grey.shade100,
              ),
            ),
          ),
          const SizedBox(width: 8),
          CircleAvatar(
            backgroundColor: _connected ? Colors.blue : Colors.grey,
            child: IconButton(
              icon: const Icon(Icons.send, color: Colors.white, size: 20),
              onPressed: _connected ? _sendMessage : null,
            ),
          ),
        ],
      ),
    );
  }
}

// ── 消息气泡 ──────────────────────────────────────────────

class _MessageBubble extends StatelessWidget {
  final Map<String, dynamic> message;
  final bool isMe;

  const _MessageBubble({required this.message, required this.isMe});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: isMe ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4, horizontal: 12),
        padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 12),
        decoration: BoxDecoration(
          color: isMe ? Colors.blue.shade100 : Colors.grey.shade300,
          borderRadius: BorderRadius.circular(12),
        ),
        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.75),
        child: Column(
          crossAxisAlignment: isMe ? CrossAxisAlignment.end : CrossAxisAlignment.start,
          children: [
            if (!isMe)
              Text(message['user'] ?? '',
                   style: const TextStyle(fontSize: 12, color: Colors.black54)),
            const SizedBox(height: 2),
            Text(message['text'] ?? '', style: const TextStyle(fontSize: 16)),
          ],
        ),
      ),
    );
  }
}

// ── 系统消息 ──────────────────────────────────────────────

class _SystemBubble extends StatelessWidget {
  final String text;
  const _SystemBubble({required this.text});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
        decoration: BoxDecoration(
          color: Colors.grey.shade200,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Text(text, style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
      ),
    );
  }
}
