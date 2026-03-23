package com.nini.app_flutter

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTrack
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.util.concurrent.LinkedBlockingQueue
import kotlin.concurrent.thread

class MainActivity: FlutterActivity() {
    private val CHANNEL = "com.nini.app_flutter/audio_playback"
    private val MAX_AUDIO_QUEUE_SIZE = 32
    private var audioTrack: AudioTrack? = null
    private var audioQueue = LinkedBlockingQueue<ByteArray>(MAX_AUDIO_QUEUE_SIZE)
    @Volatile private var isPlaying = false
    private var playThread: Thread? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL).setMethodCallHandler { call, result ->
            when (call.method) {
                "init" -> {
                    val sampleRate = call.argument<Int>("sampleRate") ?: 16000
                    initAudioTrack(sampleRate)
                    result.success(null)
                }
                "feed" -> {
                    val data = call.argument<ByteArray>("data")
                    if (data != null) {
                        if (!audioQueue.offer(data)) {
                            audioQueue.poll()
                            audioQueue.offer(data)
                        }
                    }
                    result.success(null)
                }
                "stop" -> {
                    audioQueue.clear() // Drop all pending chunks instantly
                    try {
                        audioTrack?.pause()
                        audioTrack?.flush() // Discard unplayed buffer
                        // Note: We don't release here. We just leave it ready for the next TTS.
                        audioTrack?.play()
                    } catch (e: Exception) {
                        e.printStackTrace()
                    }
                    result.success(null)
                }
                else -> result.notImplemented()
            }
        }
    }

    private fun initAudioTrack(sampleRate: Int) {
        stopAudioTrack()
        audioQueue = LinkedBlockingQueue(MAX_AUDIO_QUEUE_SIZE)
        
        // Fix Low Volume: Force VoiceCommunication to use Speakerphone instead of Earpiece
        val audioManager = getSystemService(Context.AUDIO_SERVICE) as AudioManager
        audioManager.mode = AudioManager.MODE_IN_COMMUNICATION
        audioManager.isSpeakerphoneOn = true

        val minBufferSize = AudioTrack.getMinBufferSize(
            sampleRate,
            AudioFormat.CHANNEL_OUT_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )
        audioTrack = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(sampleRate)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build()
            )
            .setBufferSizeInBytes(minBufferSize * 4) // extra buffer for network jitter
            .setTransferMode(AudioTrack.MODE_STREAM)
            .build()
        
        audioTrack?.play()
        isPlaying = true

        playThread = thread {
            while (isPlaying) {
                try {
                    val chunk = audioQueue.take() // Blocks until data is available
                    audioTrack?.write(chunk, 0, chunk.size)
                } catch (e: InterruptedException) {
                    break
                } catch (e: Exception) {
                    e.printStackTrace()
                }
            }
        }
    }

    private fun stopAudioTrack() {
        isPlaying = false
        playThread?.interrupt()
        playThread = null
        try {
            audioTrack?.apply {
                pause()
                flush()
                release()
            }
            audioTrack = null
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }
    
    override fun onDestroy() {
        stopAudioTrack()
        super.onDestroy()
    }
}
