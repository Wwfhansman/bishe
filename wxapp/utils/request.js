const app = getApp()

const request = (url, options = {}) => {
    return new Promise((resolve, reject) => {
        // Get base URL from globalData (need to ensure app is initialized or pass it in)
        // For simplicity, we might access getApp() inside, but be careful about timing.
        // Better to import a config or assume getApp().globalData is ready.
        const baseUrl = getApp().globalData.baseUrl;

        // Handle relative URLs
        const fullUrl = url.startsWith('http') ? url : `${baseUrl}${url}`;

        const token = wx.getStorageSync('token');

        const header = {
            'Content-Type': 'application/json',
            ...options.header
        };

        if (token) {
            header['Authorization'] = `Bearer ${token}`;
        }

        wx.request({
            url: fullUrl,
            method: options.method || 'GET',
            data: options.data || {},
            header: header,
            success: (res) => {
                if (res.statusCode >= 200 && res.statusCode < 300) {
                    resolve(res.data);
                } else {
                    if (res.statusCode === 401) {
                        // Token expired or invalid
                        wx.removeStorageSync('token');
                        // Optional: Redirect to login or show toast
                        wx.showToast({
                            title: '请重新登录',
                            icon: 'none'
                        });
                    }
                    reject(res);
                }
            },
            fail: (err) => {
                wx.showToast({
                    title: '网络请求失败',
                    icon: 'none'
                });
                reject(err);
            }
        });
    });
};

const get = (url, data = {}) => {
    return request(url, { method: 'GET', data });
};

const post = (url, data = {}) => {
    return request(url, { method: 'POST', data });
};

module.exports = {
    request,
    get,
    post
};
