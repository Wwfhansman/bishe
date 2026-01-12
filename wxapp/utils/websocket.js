class WebSocketClient {
    constructor(url) {
        this.url = url;
        this.socketTask = null;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectInterval = 3000;
        this.eventListeners = {};
        this.heartbeatTimer = null;
    }

    connect() {
        if (this.isConnected) return;

        const token = wx.getStorageSync('token');
        // Append token to URL query params for authentication if needed, 
        // or send it in the first message. 
        // The backend server.py looks for `token` query param in `ws_voice`.
        let fullUrl = this.url;
        if (token) {
            const separator = fullUrl.includes('?') ? '&' : '?';
            fullUrl += `${separator}token=${token}`;
        }

        this.socketTask = wx.connectSocket({
            url: fullUrl,
            success: () => {
                console.log('WebSocket connecting...');
            },
            fail: (err) => {
                console.error('WebSocket connection failed', err);
                this.handleReconnect();
            }
        });

        this.socketTask.onOpen(() => {
            console.log('WebSocket connected');
            this.isConnected = true;
            this.reconnectAttempts = 0;
            this.startHeartbeat();
            this.emit('open');
        });

        this.socketTask.onMessage((res) => {
            try {
                const data = JSON.parse(res.data);
                // If the message has an 'event' field, emit that specific event
                if (data.event) {
                    this.emit(data.event, data);
                }
                // Also emit a generic 'message' event
                this.emit('message', data);
            } catch (e) {
                // Handle binary data or non-JSON text
                this.emit('binary', res.data);
            }
        });

        this.socketTask.onClose((res) => {
            console.log('WebSocket closed', res);
            this.isConnected = false;
            this.stopHeartbeat();
            this.emit('close', res);
            // Only reconnect if not manually closed (code 1000 usually means normal closure)
            if (res.code !== 1000) {
                this.handleReconnect();
            }
        });

        this.socketTask.onError((err) => {
            console.error('WebSocket error', err);
            this.isConnected = false;
            this.emit('error', err);
        });
    }

    send(data) {
        if (this.isConnected && this.socketTask) {
            const payload = typeof data === 'object' ? JSON.stringify(data) : data;
            this.socketTask.send({
                data: payload,
                fail: (err) => {
                    console.error('Send failed', err);
                }
            });
        } else {
            console.warn('WebSocket not connected, cannot send');
        }
    }

    sendBinary(buffer) {
        if (this.isConnected && this.socketTask) {
            this.socketTask.send({
                data: buffer,
                fail: (err) => {
                    console.error('Send binary failed', err);
                }
            });
        }
    }

    close() {
        if (this.socketTask) {
            this.socketTask.close({
                code: 1000,
                reason: 'User closed'
            });
            this.socketTask = null;
            this.isConnected = false;
        }
    }

    handleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`Reconnecting... Attempt ${this.reconnectAttempts}`);
            setTimeout(() => {
                this.connect();
            }, this.reconnectInterval);
        } else {
            console.error('Max reconnect attempts reached');
            this.emit('max_reconnect');
        }
    }

    on(event, callback) {
        if (!this.eventListeners[event]) {
            this.eventListeners[event] = [];
        }
        this.eventListeners[event].push(callback);
    }

    off(event, callback) {
        if (this.eventListeners[event]) {
            this.eventListeners[event] = this.eventListeners[event].filter(cb => cb !== callback);
        }
    }

    emit(event, data) {
        if (this.eventListeners[event]) {
            this.eventListeners[event].forEach(cb => cb(data));
        }
    }

    startHeartbeat() {
        // Optional: Send a ping every 30 seconds to keep connection alive
        // if the backend requires it.
        // this.heartbeatTimer = setInterval(() => {
        //     this.send({ type: 'ping' });
        // }, 30000);
    }

    stopHeartbeat() {
        if (this.heartbeatTimer) {
            clearInterval(this.heartbeatTimer);
            this.heartbeatTimer = null;
        }
    }
}

module.exports = WebSocketClient;
