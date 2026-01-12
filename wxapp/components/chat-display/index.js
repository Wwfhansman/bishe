// components/chat-display/index.js
Component({
    properties: {
        text: {
            type: String,
            value: '',
            observer(newVal) {
                if (newVal) {
                    this.triggerAnimation();
                }
            }
        },
        role: {
            type: String,
            value: 'ai' // 'user' or 'ai'
        }
    },

    data: {
        currentRole: 'ai',
        animating: false
    },

    methods: {
        triggerAnimation() {
            // Reset animation
            this.setData({ animating: false, currentRole: this.properties.role }, () => {
                setTimeout(() => {
                    this.setData({ animating: true });
                }, 50);
            });
        }
    }
})
