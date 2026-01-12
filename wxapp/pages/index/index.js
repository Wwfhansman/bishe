// pages/index/index.js
const app = getApp();
const WebSocketClient = require('../../utils/websocket');
const AudioPlayer = require('../../utils/audio-player');

Page({
  data: {
    status: 'idle', // idle, listening, processing, speaking
    volume: 0,
    displayText: '点击球体开始',
    displayRole: 'ai',
    ws: null,
    sessionId: null
  },

  onLoad() {
    this.audioPlayer = new AudioPlayer();
    this.recorderManager = wx.getRecorderManager();
    this.setupRecorder();
    this.initWebSocket();

    // Keep screen on
    wx.setKeepScreenOn({ keepScreenOn: true });
  },

  onUnload() {
    if (this.data.ws) {
      this.data.ws.close();
    }
    this.stopRecording();
  },

  setupRecorder() {
    this.recorderManager.onFrameRecorded((res) => {
      const { frameBuffer, isLastFrame } = res;
      if (this.data.ws && this.data.ws.isConnected && this.data.status === 'listening') {
        this.data.ws.sendBinary(frameBuffer);
        this.calculateVolume(frameBuffer);
      }
    });

    this.recorderManager.onStart(() => {
      console.log('Recorder started');
    });

    this.recorderManager.onStop(() => {
      console.log('Recorder stopped');
    });

    this.recorderManager.onError((err) => {
      console.error('Recorder error:', err);
      this.setData({ displayText: '录音设备异常' });
    });
  },

  calculateVolume(buffer) {
    const data = new Int16Array(buffer);
    let sum = 0;
    for (let i = 0; i < data.length; i += 10) {
      sum += Math.abs(data[i]);
    }
    const avg = sum / (data.length / 10);
    const volume = Math.min(100, (avg / 1000) * 100);
    this.setData({ volume });
  },

  async initWebSocket() {
    // Ensure we have a session_id
    if (!this.data.sessionId) {
      try {
        const { post } = require('../../utils/request');
        const res = await post('/api/sessions', {});
        if (res && res.session_id) {
          this.setData({ sessionId: res.session_id });
        } else {
          console.error('Failed to create session');
          return;
        }
      } catch (e) {
        console.error('Error creating session', e);
        return;
      }
    }

    const wsUrl = `${app.globalData.wsUrl}?session_id=${this.data.sessionId}`;
    const ws = new WebSocketClient(wsUrl);

    ws.on('open', () => {
      console.log('WS Connected');
      this.setData({ status: 'idle', displayText: '点击球体开始' });
      ws.send({ cmd: 'init' });
    });

    ws.on('close', () => {
      console.log('WS Closed');
      this.setData({ status: 'idle', displayText: '连接断开，正在重连...' });
      this.stopRecording();
    });

    ws.on('asr_text', (data) => {
      this.setData({
        displayText: data.text,
        displayRole: 'user',
        status: 'processing'
      });
    });

    ws.on('llm_text', (data) => {
      this.setData({
        displayText: data.text,
        displayRole: 'ai',
        status: 'speaking'
      });
    });

    ws.on('tts_start', (data) => {
      this.setData({ status: 'speaking' });
      if (data.rate) {
        this.audioPlayer.setSampleRate(data.rate);
      }
    });

    ws.on('tts_done', () => {
      this.setData({ status: 'listening' });
      this.startRecording();
    });

    ws.on('tts_interrupted', () => {
      console.log('TTS Interrupted');
      this.audioPlayer.reset();
      this.setData({ status: 'listening' });
    });

    ws.on('binary', (data) => {
      this.audioPlayer.pushPCM(data);
    });

    ws.connect();
    this.setData({ ws });
  },

  handleSphereTap() {
    const { status } = this.data;
    if (status === 'idle') {
      this.startListening();
      this.setData({ status: 'listening', displayText: '正在聆听...' });
      this.audioPlayer.init();
    } else {
      this.stopRecording();
      this.audioPlayer.reset();
      this.setData({ status: 'idle', displayText: '已暂停' });
      if (this.data.ws) {
        this.data.ws.send({ cmd: 'stop' });
      }
    }
  },

  startRecording() {
    const options = {
      duration: 600000,
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 48000,
      format: 'PCM',
      frameSize: 6
    };
    try {
      this.recorderManager.start(options);
    } catch (e) {
      console.error("Start record failed", e);
    }
  },

  stopRecording() {
    this.recorderManager.stop();
  }
})