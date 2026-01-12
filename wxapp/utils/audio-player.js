class AudioPlayer {
    constructor() {
        this.ctx = null;
        this.nextStartTime = 0;
        this.isPlaying = false;
        this.sampleRate = 24000; // Default, will be updated by tts_start event
        this.audioQueue = [];
        this.isProcessing = false;
    }

    init() {
        if (!this.ctx) {
            this.ctx = wx.createWebAudioContext();
        }
    }

    setSampleRate(rate) {
        this.sampleRate = rate;
    }

    reset() {
        this.audioQueue = [];
        this.nextStartTime = 0;
        this.isPlaying = false;
        if (this.ctx) {
            // Suspend or close to stop current sound immediately?
            // Re-creating context might be safer to clear all scheduled buffers
            this.ctx.close().then(() => {
                this.ctx = wx.createWebAudioContext();
            });
        } else {
            this.ctx = wx.createWebAudioContext();
        }
    }

    // Input: ArrayBuffer of Int16 PCM
    pushPCM(arrayBuffer) {
        if (!this.ctx) this.init();

        // Convert Int16 to Float32
        const int16 = new Int16Array(arrayBuffer);
        const float32 = new Float32Array(int16.length);
        for (let i = 0; i < int16.length; i++) {
            float32[i] = int16[i] / 32768;
        }

        // Create AudioBuffer
        const audioBuffer = this.ctx.createBuffer(1, float32.length, this.sampleRate);
        audioBuffer.getChannelData(0).set(float32);

        this.scheduleBuffer(audioBuffer);
    }

    scheduleBuffer(audioBuffer) {
        const source = this.ctx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(this.ctx.destination);

        // Schedule playback
        // Ensure we don't schedule in the past
        const currentTime = this.ctx.currentTime;
        if (this.nextStartTime < currentTime) {
            this.nextStartTime = currentTime + 0.05; // Small buffer for start
        }

        source.start(this.nextStartTime);
        this.nextStartTime += audioBuffer.duration;
    }
}

module.exports = AudioPlayer;
