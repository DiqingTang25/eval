/* ════════════════════════════════════════════
   WebSocket Client — 自动重连 + 事件分发
   ════════════════════════════════════════════ */

export class WSClient {
    constructor(url) {
        this.url = url;
        this.ws = null;
        this.listeners = new Map();
        this.reconnectAttempts = 0;
        this.maxRetries = 5;
        this.baseDelay = 1000;
        this.shouldReconnect = true;
    }

    connect() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) return;

        this.shouldReconnect = true;
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.ws = new WebSocket(`${proto}//${location.host}${this.url}`);

        this.ws.onopen = () => {
            this.reconnectAttempts = 0;
            this.dispatch('connected', {});
        };

        this.ws.onmessage = (e) => {
            try {
                const msg = JSON.parse(e.data);
                if (msg.type) {
                    this.dispatch(msg.type, msg);
                }
                this.dispatch('message', msg);
            } catch (err) {
                console.warn('WS parse error:', err);
            }
        };

        this.ws.onclose = () => {
            this.dispatch('disconnected', {});
            this._tryReconnect();
        };

        this.ws.onerror = (err) => {
            console.warn('WS error:', err);
        };
    }

    _tryReconnect() {
        if (!this.shouldReconnect) return;
        if (this.reconnectAttempts >= this.maxRetries) {
            console.warn('WS: max reconnect attempts reached');
            return;
        }
        const delay = Math.min(this.baseDelay * Math.pow(2, this.reconnectAttempts), 30000);
        this.reconnectAttempts++;
        setTimeout(() => this.connect(), delay);
    }

    disconnect() {
        this.shouldReconnect = false;
        if (this.ws) { this.ws.close(); this.ws = null; }
    }

    on(event, callback) {
        if (!this.listeners.has(event)) this.listeners.set(event, []);
        this.listeners.get(event).push(callback);
        return () => this.off(event, callback);  // 返回取消订阅函数
    }

    off(event, callback) {
        const cbs = this.listeners.get(event);
        if (cbs) {
            this.listeners.set(event, cbs.filter(cb => cb !== callback));
        }
    }

    dispatch(event, data) {
        const cbs = this.listeners.get(event);
        if (cbs) {
            cbs.forEach(cb => { try { cb(data); } catch (e) { console.warn('WS listener error:', e); } });
        }
    }

    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        }
    }
}

// 自动检测部署路径前缀 (与 api.js 保持一致)
const WS_BASE = (() => {
    try {
        const p = location.pathname;
        if (p.startsWith('/test/') || p === '/test') return '/test';
        return '';
    } catch (e) { return ''; }
})();

export const ws = new WSClient(`${WS_BASE}/ws`);
window.ws = ws;  // 暴露到全局，供 index.html 内联脚本使用
export default ws;
