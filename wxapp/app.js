// app.js
const { post } = require('./utils/request');

App({
    globalData: {
        userInfo: null,
        token: null,
        // CONFIG: Change this URL when deploying to cloud or testing on device
        // Localhost for simulator: http://127.0.0.1:8000
        // LAN IP for device: http://192.168.x.x:8000
        baseUrl: 'http://127.0.0.1:8000',
        wsUrl: 'ws://127.0.0.1:8000/ws/voice'
    },

    onLaunch() {
        // Check if token exists
        const token = wx.getStorageSync('token');
        if (token) {
            this.globalData.token = token;
            this.checkSession();
        } else {
            // No token, try silent login
            this.login();
        }

        // Get system info for UI adaptation
        const sysInfo = wx.getSystemInfoSync();
        this.globalData.sysInfo = sysInfo;
    },

    login() {
        wx.login({
            success: async res => {
                if (res.code) {
                    // Send the code to your backend
                    try {
                        // Note: We use the full URL here or ensure request.js can access globalData
                        // Since request.js uses getApp().globalData, we need to make sure it's set.
                        // But getApp() might not be fully ready in onLaunch synchronous part? 
                        // Actually getApp() returns the instance. globalData is set above.

                        // However, request.js imports getApp() at top level which might be too early?
                        // No, request.js calls getApp() inside the function, which is fine.

                        const data = await post('/api/auth/wechat_login', { code: res.code });
                        if (data.ok) {
                            this.globalData.token = data.token;
                            this.globalData.userInfo = { id: data.user_id }; // Basic info
                            wx.setStorageSync('token', data.token);
                            console.log('Login successful', data);
                        } else {
                            console.error('Login failed', data);
                        }
                    } catch (err) {
                        console.error('Login error', err);
                    }
                } else {
                    console.log('Login failed！' + res.errMsg)
                }
            }
        })
    },

    checkSession() {
        // Optional: Verify if token is still valid via an API call like /api/me
        // For now, we assume it's valid until a 401 happens in request.js
    }
})
