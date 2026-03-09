import 'dart:typed_data';
import 'package:record/record.dart';

class RecordService {
  final AudioRecorder _record = AudioRecorder();

  Future<bool> hasPermission() async {
    return await _record.hasPermission();
  }

  /// Starts an audio stream of 16kHz PCM 16-bit mono.
  /// Used for sending raw audio data over WebSocket.
  Future<Stream<Uint8List>?> startStream() async {
    if (await hasPermission()) {
      return await _record.startStream(
        const RecordConfig(
          encoder: AudioEncoder.pcm16bits,
          sampleRate: 16000,
          numChannels: 1,
          echoCancel: true,     // Request hardware echo cancellation
          noiseSuppress: true,  // Request noise suppression
          autoGain: true,       // Auto gain control
          // CRITICAL FOR AEC ON ANDROID:
          androidConfig: AndroidRecordConfig(
            audioSource: AndroidAudioSource.voiceCommunication,
          ),
        ),
      );
    }
    return null;
  }

  Future<void> stop() async {
    if (await _record.isRecording()) {
      await _record.stop();
    }
  }

  void dispose() {
    _record.dispose();
  }
}
