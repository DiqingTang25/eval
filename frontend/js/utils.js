/* ════════════════════════════════════════════
   工具函数 — 格式化 / DOM 操作 / Toast
   ════════════════════════════════════════════ */

export function formatDate(isoStr) {
    if (!isoStr) return '-';
    try {
        const d = new Date(isoStr);
        // Use current language for date formatting
        const lang = (typeof window !== 'undefined' && window.getLang) ? window.getLang() : 'zh';
        const locale = lang === 'en' ? 'en-US' : 'zh-CN';
        return d.toLocaleString(locale, { hour12: false });
    } catch (e) { return isoStr; }
}

export function formatDuration(seconds) {
    if (seconds == null) return '-';
    const s = parseFloat(seconds);
    if (s < 1) return `${(s * 1000).toFixed(0)}ms`;
    if (s < 60) return `${s.toFixed(1)}s`;
    return `${Math.floor(s / 60)}m ${(s % 60).toFixed(0)}s`;
}

export function truncate(text, maxLen = 100) {
    if (!text) return '';
    if (text.length <= maxLen) return text;
    return text.slice(0, maxLen) + '...';
}

export function scoreColor(score) {
    if (score >= 4.0) return 'sm-high';
    if (score >= 3.0) return 'sm-mid';
    return 'sm-low';
}

export function scoreText(score) {
    const t = (typeof window !== 'undefined' && window.t) ? window.t : function(k,d){return d;};
    if (score >= 4.5) return t('score_excellent', '卓越');
    if (score >= 4.0) return t('score_good', '优秀');
    if (score >= 3.0) return t('score_fair', '良好');
    if (score >= 2.0) return t('score_poor', '需改进');
    return t('score_fail', '不合格');
}

export function ringColor(score) {
    if (score >= 80) return 'ring-green';
    if (score >= 50) return 'ring-yellow';
    return 'ring-red';
}

export function debounce(fn, delay = 300) {
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), delay);
    };
}

export function showToast(message, type = 'info', duration = 3000) {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

export function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

export function $$(selector, parent = document) {
    return Array.from(parent.querySelectorAll(selector));
}

export function $(selector, parent = document) {
    return parent.querySelector(selector);
}

export function show(el) { if (el) el.style.display = ''; }
export function hide(el) { if (el) el.style.display = 'none'; }
