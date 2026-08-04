/* ════════════════════════════════════════════
   API Client — fetch 封装, 错误处理, 分页支持
   P0-fix: 429 自动重试 (指数退避, 最多3次)
   ════════════════════════════════════════════ */

// 自动检测部署路径前缀: :8000直接访问 → '', /test/反向代理 → '/test'
const API_BASE = (() => {
    try {
        const p = location.pathname;
        if (p.startsWith('/test/') || p === '/test') return '/test';
        return '';
    } catch (e) { return ''; }
})();

// 429 重试配置
const MAX_RETRIES = 3;
const RETRY_BASE_DELAY_MS = 1000;  // 首次重试等 1s

class APIError extends Error {
    constructor(status, body) {
        super(`API ${status}: ${body}`);
        this.status = status;
        this.body = body;
    }
}

export const api = {
    async request(method, path, { body, params } = {}) {
        let url = `${API_BASE}${path}`;
        if (params) {
            const qs = new URLSearchParams();
            Object.entries(params).forEach(([k, v]) => {
                if (v !== '' && v !== undefined && v !== null) qs.set(k, v);
            });
            const qsStr = qs.toString();
            if (qsStr) url += '?' + qsStr;
        }

        const opts = {
            method,
            headers: { 'Content-Type': 'application/json' },
        };
        if (body && method !== 'GET') {
            opts.body = JSON.stringify(body);
        }

        // P0-fix: 429 自动重试 (指数退避)
        let lastError = null;
        for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
            const res = await fetch(url, opts);

            if (res.ok) {
                const text = await res.text();
                try { return JSON.parse(text); } catch (e) { return text; }
            }

            // 429 速率限制 → 自动重试
            if (res.status === 429 && attempt < MAX_RETRIES) {
                let retryAfter = 1;
                try {
                    const body = await res.json();
                    retryAfter = body.retry_after_seconds || 1;
                } catch (e) {
                    // 无法解析 body, 使用默认退避
                    retryAfter = Math.min(RETRY_BASE_DELAY_MS * Math.pow(2, attempt) / 1000, 30);
                }
                const delayMs = Math.max(retryAfter * 1000, RETRY_BASE_DELAY_MS * Math.pow(2, attempt));
                console.warn(`[API] 429 rate limited on ${path}, retrying in ${(delayMs/1000).toFixed(1)}s (attempt ${attempt + 1}/${MAX_RETRIES})`);
                await new Promise(r => setTimeout(r, delayMs));
                lastError = new APIError(429, 'Rate limited, retrying...');
                continue;
            }

            // 其他错误 → 直接抛出
            let detail = '';
            try { detail = await res.text(); } catch (e) { /* ignore */ }
            throw new APIError(res.status, detail);
        }

        // 重试耗尽
        throw lastError || new APIError(429, 'Rate limit retries exhausted');
    },

    get(path, params)    { return this.request('GET', path, { params }); },
    post(path, body)     { return this.request('POST', path, { body }); },
    put(path, body)      { return this.request('PUT', path, { body }); },
    delete(path, body)   { return this.request('DELETE', path, { body }); },
};

export default api;
