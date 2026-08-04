/* ════════════════════════════════════════════
   Web Evaluator Page — Lighthouse 风格
   ════════════════════════════════════════════ */

import api from '../api.js';
import { showToast, ringColor } from '../utils.js';

const WebEvalPage = {
    state: { initialized: false },

    init() { this.state.initialized = true; },
    render() { this.renderLayout(); this.loadResults(); },
    destroy() {},

    renderLayout() {
        document.getElementById('page-web-eval').innerHTML = `
          <div class="page-header"><h2>🌐 网页评测</h2></div>
          <div class="controls">
            <input id="weUrl" value="http://124.174.108.70" style="width:400px">
            <button class="btn btn-primary" id="weRunBtn">🔍 开始评测</button>
            <button class="btn btn-outline btn-sm" id="weRefreshBtn">🔄 刷新</button>
          </div>
          <div class="ring-cards" id="weRingCards"><div class="qa-empty">点击"开始评测"对网页进行全维度检测</div></div>
          <div class="web-eval-detail" id="weDetail"></div>
          <div class="card mt-4"><h3 style="color:var(--text-secondary);font-size:14px;margin-bottom:12px">📋 历史评测</h3><div id="weHistory">加载中...</div></div>
        `;
        this.bindEvents();
    },

    bindEvents() {
        document.getElementById('weRunBtn').addEventListener('click', () => this.run());
        document.getElementById('weRefreshBtn').addEventListener('click', () => this.loadResults());
    },

    async run() {
        document.getElementById('weRingCards').innerHTML = '<div class="qa-empty">⏳ 正在评测网页...</div>';
        try {
            const url = document.getElementById('weUrl').value;
            const data = await api.get(`/api/web-eval/run?url=${encodeURIComponent(url)}`);
            if (data.ok) {
                this.renderScoreRings(data.detail);
                this.renderDetailTable(data.detail);
                this.loadResults();
            } else {
                showToast('评测失败', 'error');
            }
        } catch (e) {
            showToast('请求失败: ' + e.message, 'error');
            document.getElementById('weRingCards').innerHTML = '<div class="qa-empty">点击"开始评测"</div>';
        }
    },

    renderScoreRings(data) {
        const perf = data.performance || {};
        const a11y = data.accessibility || {};
        const bp = data.best_practices || {};
        const ai = data.ai_function || {};
        const ux = data.ui_ux || {};
        const ct = data.content || {};
        const cards = [
            { label: '综合', score: data.overall_score || 0 },
            { label: '性能', score: perf.score || 0, detail: `LCP:${perf.lcp || 0}ms` },
            { label: '可访问性', score: a11y.score || 0 },
            { label: '最佳实践', score: bp.score || 0, detail: bp.https ? 'HTTPS✅' : 'HTTPS❌' },
            { label: 'AI对话', score: ai.score || 0, detail: `延迟:${ai.response_latency_ms || 0}ms` },
            { label: 'UI/UX', score: ux.score || 0 },
            { label: '内容', score: ct.score || 0 },
        ];
        document.getElementById('weRingCards').innerHTML = cards.map(c => `
          <div style="text-align:center">
            <div class="score-ring ${ringColor(c.score)}">
              <span class="ring-value">${c.score}</span>
              <span class="ring-label">${c.label}</span>
            </div>
            <div style="font-size:11px;color:var(--text-muted);margin-top:4px">${c.detail || ''}</div>
          </div>
        `).join('');
    },

    renderDetailTable(data) {
        const perf = data.performance || {};
        const bp = data.best_practices || {};
        const a11y = data.accessibility || {};
        const violations = a11y.violations || [];
        const ai = data.ai_function || {};

        document.getElementById('weDetail').innerHTML = `<table class="data-table" style="margin-top:16px">
          <tr><th>指标</th><th>值</th><th>评估</th></tr>
          <tr><td>LCP</td><td>${perf.lcp || 0}ms</td><td>${perf.lcp < 2500 ? '✅' : '⚠️'}</td></tr>
          <tr><td>TTFB</td><td>${perf.ttfb || 0}ms</td><td>${perf.ttfb < 800 ? '✅' : '⚠️'}</td></tr>
          <tr><td>CLS</td><td>${perf.cls || 0}</td><td>${perf.cls < 0.1 ? '✅' : '⚠️'}</td></tr>
          <tr><td>HTTPS</td><td>${bp.https ? '✅' : '❌'}</td><td>-</td></tr>
          <tr><td>可访问性违规</td><td>${violations.length}项</td><td>${violations.length === 0 ? '✅' : '⚠️'}</td></tr>
          <tr><td>AI延迟</td><td>${ai.response_latency_ms || 0}ms</td><td>${(ai.response_latency_ms || 0) < 3000 ? '✅' : '⚠️'}</td></tr>
        </table>
        ${violations.length > 0 ? `<div style="margin-top:12px"><h4 style="color:var(--accent-red)">⚠️ 可访问性违规:</h4>${violations.map(v => `<div style="font-size:12px;color:var(--text-secondary)">• <b>${v.id}</b>: ${v.help}</div>`).join('')}</div>` : ''}`;
    },

    async loadResults() {
        try {
            const data = await api.get('/api/web-eval/results', { page_size: 10 });
            if (!data.items?.length) {
                document.getElementById('weHistory').innerHTML = '<span class="text-muted">暂无历史评测</span>';
                return;
            }
            document.getElementById('weHistory').innerHTML = data.items.map(r => `
              <div style="padding:6px 0;border-bottom:1px solid var(--bg-tertiary);font-size:12px">
                🌐 ${r.url} · 综合: <b>${r.overall_score}</b> · ${new Date(r.created_at).toLocaleDateString('zh-CN')}
              </div>
            `).join('');
        } catch (e) { /* ignore */ }
    },
};

export default WebEvalPage;
