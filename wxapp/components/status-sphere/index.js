// components/status-sphere/index.js
Component({
    properties: {
        status: {
            type: String,
            value: 'idle' // idle, listening, processing, speaking
        },
        volume: {
            type: Number,
            value: 0
        }
    },

    methods: {
        handleTap() {
            this.triggerEvent('sphereTap');
        }
    }
})
