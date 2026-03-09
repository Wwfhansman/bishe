import 'package:audio_session/audio_session.dart';

class AudioSessionService {
  Future<void> initAudioSession() async {
    final session = await AudioSession.instance;
    // Combine category options using the | operator (cannot be done in const context)
    final categoryOptions = AVAudioSessionCategoryOptions.allowBluetooth |
        AVAudioSessionCategoryOptions.defaultToSpeaker |
        AVAudioSessionCategoryOptions.allowBluetoothA2dp;

    await session.configure(AudioSessionConfiguration(
      // iOS: Ensure voice chat mode is enabled for hardware AEC
      avAudioSessionCategory: AVAudioSessionCategory.playAndRecord,
      avAudioSessionCategoryOptions: categoryOptions,
      avAudioSessionMode: AVAudioSessionMode.voiceChat,
      avAudioSessionRouteSharingPolicy: AVAudioSessionRouteSharingPolicy.defaultPolicy,
      avAudioSessionSetActiveOptions: AVAudioSessionSetActiveOptions.none,

      // Android: Critical! setting usage to voiceCommunication enables hardware AEC
      androidAudioAttributes: const AndroidAudioAttributes(
        contentType: AndroidAudioContentType.speech,
        flags: AndroidAudioFlags.none,
        usage: AndroidAudioUsage.voiceCommunication,
      ),
      androidAudioFocusGainType: AndroidAudioFocusGainType.gain,
      androidWillPauseWhenDucked: true,
    ));
  }
}
