import 'dart:io';
import 'package:flutter/services.dart';
import 'package:flutter_sound/flutter_sound.dart';

class AudioPlayService {
  final FlutterSoundPlayer _player = FlutterSoundPlayer();
  static const MethodChannel _channel = MethodChannel('com.nini.app_flutter/audio_playback');
  
  bool _isInit = false;
  int _currentSampleRate = 24000;

  Future<void> init() async {
    if (_isInit) return;
    if (!Platform.isAndroid) {
      await _player.openPlayer();
    }
    _isInit = true;
  }

  // Prepares the player to accept streaming PCM16 push data.
  Future<void> startStream({int sampleRate = 24000}) async {
    if (!_isInit) await init();
    _currentSampleRate = sampleRate;
    
    if (Platform.isAndroid) {
      await _channel.invokeMethod('init', {'sampleRate': sampleRate});
    } else {
      // Stop any existing playback before resetting the stream
      if (!_player.isStopped) {
        await stop();
      }
      
      await _player.startPlayerFromStream(
        codec: Codec.pcm16,
        numChannels: 1,
        sampleRate: sampleRate,
        interleaved: true,
        bufferSize: 8192,
      );
    }
  }

  // Feeds standard PCM16 binary chunks into the player sink
  void feedData(Uint8List data) {
    if (Platform.isAndroid) {
      // Send directly to the native AudioTrack which respects VoiceCommunication usage
      _channel.invokeMethod('feed', {'data': data});
    } else {
      if (!_player.isStopped && _player.uint8ListSink != null) {
        _player.uint8ListSink!.add(data);
      }
    }
  }

  Future<void> stop() async {
    if (Platform.isAndroid) {
      await _channel.invokeMethod('stop');
    } else {
      if (!_player.isStopped) {
        await _player.stopPlayer();
      }
    }
  }

  // Instantly discard any queued audio (used when AI is interrupted)
  Future<void> reset() async {
    await stop();
  }

  void dispose() {
    if (!Platform.isAndroid) {
      _player.closePlayer();
    } else {
      stop();
    }
  }
}
