import 'dart:async';
import 'package:flutter/foundation.dart';
import '../services/api_service.dart';
import '../services/audio_session_service.dart';
import '../services/record_service.dart';
import '../services/audio_play_service.dart';
import '../services/websocket_service.dart';

/// Custom enum to avoid conflict with Flutter's built-in ConnectionState
enum VoiceConnectionState { disconnected, connecting, connected }

class AppStateProvider with ChangeNotifier {
  final ApiService apiService = ApiService();
  final AudioSessionService audioSessionService = AudioSessionService();
  final RecordService recordService = RecordService();
  final AudioPlayService audioPlayService = AudioPlayService();
  final WebSocketService webSocketService = WebSocketService();

  bool isAuthenticated = false;
  String? userId;
  String? currentSessionId;
  List<dynamic> sessions = [];

  VoiceConnectionState connectionState = VoiceConnectionState.disconnected;
  bool isRecording = false;
  bool isAIPlayback = false;

  String asrText = "";
  String llmText = "";

  StreamSubscription? _recordSub;

  AppStateProvider() {
    _initAuth();
  }

  Future<void> _initAuth() async {
    final token = await apiService.getToken();
    userId = await apiService.getUserId();
    if (token != null) {
      isAuthenticated = true;
      await fetchSessions();
    }
    notifyListeners();
  }

  Future<bool> login(String username, String password) async {
    final res = await apiService.login(username, password);
    if (res['ok'] == true) {
      isAuthenticated = true;
      userId = res['user_id'];
      await fetchSessions();
      notifyListeners();
      return true;
    }
    return false;
  }

  Future<bool> register(String username, String password) async {
    final res = await apiService.register(username, password);
    if (res['ok'] == true) {
      isAuthenticated = true;
      userId = res['user_id'];
      await fetchSessions();
      notifyListeners();
      return true;
    }
    return false;
  }

  // BUG FIX #2: Also clear user_id when logging out
  Future<void> logout() async {
    await stopVoiceChat();  // Clean up any active session
    await apiService.clearToken();
    await apiService.clearUserId();  // <-- was missing!
    isAuthenticated = false;
    userId = null;
    currentSessionId = null;
    sessions = [];
    asrText = "";
    llmText = "";
    notifyListeners();
  }

  Future<void> fetchSessions() async {
    sessions = await apiService.getSessions();
    notifyListeners();
  }

  Future<void> startNewSession() async {
    currentSessionId = await apiService.createSession();
    await fetchSessions();
    notifyListeners();
  }

  void selectSession(String sessionId) {
    currentSessionId = sessionId;
    notifyListeners();
  }

  Future<void> startVoiceChat() async {
    if (currentSessionId == null) {
      await startNewSession();
    }
    if (currentSessionId == null) return;

    connectionState = VoiceConnectionState.connecting;
    notifyListeners();

    // BUG FIX #1: Init hardware AEC mode FIRST, then wait for it to take effect
    await audioSessionService.initAudioSession();

    // BUG FIX #3: Initialize audio player BEFORE connecting WebSocket
    // so it's ready when the backend sends the greeting TTS
    await audioPlayService.init();

    // Set up WebSocket callbacks
    webSocketService.onJsonMessage = (json) {
      if (json['event'] == 'asr_text') {
        asrText = json['text'] ?? '';
      } else if (json['event'] == 'llm_text') {
        llmText = json['text'] ?? '';
      } else if (json['event'] == 'tts_start') {
        isAIPlayback = true;
        final rate = json['rate'] ?? 24000;
        audioPlayService.startStream(sampleRate: rate);
      } else if (json['event'] == 'tts_done') {
        isAIPlayback = false;
      } else if (json['event'] == 'tts_reset') {
        audioPlayService.reset();
        isAIPlayback = false;
      }
      notifyListeners();
    };

    webSocketService.onBinaryMessage = (data) {
      audioPlayService.feedData(data);
    };

    webSocketService.onClosed = () {
      stopVoiceChat();
    };

    webSocketService.onError = (e) {
      // Handle error
    };

    // Connect WebSocket - this will send 'init' and trigger backend greeting
    await webSocketService.connect(currentSessionId!, apiService: apiService);
    connectionState = VoiceConnectionState.connected;

    // BUG FIX #1: Add a small delay after AEC init so the hardware mode is fully active
    // before we start recording. Without this, the first few hundred ms of recording
    // may not have AEC applied.
    await Future.delayed(const Duration(milliseconds: 300));

    // Start mic recording and push to ws
    final stream = await recordService.startStream();
    if (stream != null) {
      isRecording = true;
      _recordSub = stream.listen((data) {
        if (connectionState == VoiceConnectionState.connected) {
          webSocketService.sendBinary(data);
        }
      });
    }

    notifyListeners();
  }

  Future<void> stopVoiceChat() async {
    connectionState = VoiceConnectionState.disconnected;
    isRecording = false;
    isAIPlayback = false;
    
    await _recordSub?.cancel();
    _recordSub = null;
    
    await recordService.stop();
    await audioPlayService.stop();
    webSocketService.disconnect();
    
    notifyListeners();
  }

  void interruptAI() {
    webSocketService.sendStop();
    audioPlayService.reset();
    isAIPlayback = false;
    notifyListeners();
  }

  @override
  void dispose() {
    stopVoiceChat();
    recordService.dispose();
    audioPlayService.dispose();
    super.dispose();
  }
}
