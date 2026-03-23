import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'api_service.dart';
import '../utils/constants.dart';

class WebSocketService {
  WebSocketChannel? _channel;
  StreamSubscription? _subscription;
  
  /// Callbacks to dispatch received events to the UI/Audio logic
  Function(Map<String, dynamic>)? onJsonMessage;
  Function(Uint8List)? onBinaryMessage;
  Function()? onClosed;
  Function(dynamic)? onError;

  Future<void> connect(String sessionId, {required ApiService apiService}) async {
    disconnect();
    final token = await apiService.getToken();
    final url = Uri.parse(ConstantConfigs.wsUrl).replace(queryParameters: {
      'session_id': sessionId,
      if (token != null) 'token': token,
    });
    
    _channel = WebSocketChannel.connect(url);
    _subscription = _channel?.stream.listen((message) {
      if (message is String) {
        try {
          final json = jsonDecode(message);
          onJsonMessage?.call(json);
        } catch (e) {
          // Fallback log or ignore malformed JSON
        }
      } else if (message is List<int>) {
        // Binary ArrayBuffer (TTS output PCM)
        onBinaryMessage?.call(Uint8List.fromList(message));
      }
    }, onDone: () {
      onClosed?.call();
      _channel = null;
    }, onError: (error) {
      onError?.call(error);
      onClosed?.call();
      _channel = null;
    });
    
    // Initialize handshake logic from index.html (cmd: init)
    sendJson({'cmd': 'init'});
  }

  void sendJson(Map<String, dynamic> data) {
    _channel?.sink.add(jsonEncode(data));
  }

  void sendBinary(Uint8List data) {
    _channel?.sink.add(data);
  }

  /// Stop current TTS generation on server
  void sendStop() {
    sendJson({'cmd': 'stop'});
  }

  /// Disconnect web socket completely
  void disconnect() {
    _subscription?.cancel();
    _subscription = null;
    _channel?.sink.close();
    _channel = null;
  }
}
