/* ════════════════════════════════════════════
   Web Evaluator Page — Lighthouse 风格
   ════════════════════════════════════════════ */

import api from '../api.js';
import { showToast, ringColor } from '../utils.js';
import { t, getLang, onLangChange } from '../i18n-bridge.js';

const WebEvalPage = {
    state: { initialized: false },

    init() {
        this.state.initialized = true;
        onLangChange(() => {
            if (document.getElementById('page-web-eval') &&
                document.getElementById('page-web-eval').classList.contains('active')) {
                this.render();
            }
        });
    },
    render() { this.renderLayout(); this.loadResults(); },
    destroy() {},

    renderLayout() {
        document.getElementById('page-web-eval').innerHTML = `
          <div class="page-header"><h2>🌐 ${t('we_title')}</h2></div>
          <div class="controls">
            <input id="weUrl" value="http://124.174.108.70" style="width:400px">
            <button class="btn btn-primary" id="weRunBtn">${t('we_start_btn')}</button>
            <button class="btn btn-outline btn-sm" id="weRefreshBtn">${t('we_refresh_btn')}</button>
          </div>
          <div class="ring-cards" id="weRingCards"><div class="qa-empty">${t('we_hint')}</div></div>
          <div class="web-eval-detail" id="weDetail"></div>
          <div class="card mt-4"><h3 style="color:var(--text-secondary);font-size:14px;margin-bottom:12px">${t('we_history_title')}</h3><div id="weHistory">${t('sys_loading')}</div></div>
        `;
        this.bindEvents();
    },

    bindEvents() {
        document.getElementById('weRunBtn').addEventListener('click', () => this.run());
        document.getElementById('weRefreshBtn').addEventListener('click', () => this.loadResults());
    },

    async run() {
        document.getElementById('weRingCards').innerHTML = `<div class="qa-empty">${t('we_evaluating')}</div>`;
        try {
            const url = document.getElementById('weUrl').value;
            const data = await api.get(`/api/web-eval/run?url=${encodeURIComponent(url)}`);
            if (data.ok) {
                this.renderScoreRings(data.detail);
                this.renderDetailTable(data.detail);
                this.loadResults();
            } else {
                showToast(t('we_run_failed'), 'error');
            }
        } catch (e) {
            showToast(t('request_failed', e.message), 'error');
            document.getElementById('weRingCards').innerHTML = `<div class="qa-empty">${t('we_hint')}</div>`;
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
            { label: t('rp_compare_th_overall'), score: data.overall_score || 0 },
            { label: t('we_dim_performance'), score: perf.score || 0, detail: `${t('we_lcp')}:${perf.lcp || 0}ms` },
            { label: t('we_dim_accessibility'), score: a11y.score || 0 },
            { label: t('we_dim_best_practices'), score: bp.score || 0, detail: bp.https ? 'HTTPS✅' : 'HTTPS❌' },
            { label: t('we_dim_ai_function'), score: ai.score || 0, detail: `${t('we_ai_latency')}:${ai.response_latency_ms || 0}ms` },
            { label: t('we_dim_ui_ux'), score: ux.score || 0 },
            { label: t('we_dim_content'), score: ct.score || 0 },
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
          <tr><th>${t('we_detail_indicator')}</th><th>${t('we_detail_value')}</th><th>${t('we_detail_eval')}</th></tr>
          <tr><td>${t('we_lcp')}</td><td>${perf.lcp || 0}ms</td><td>${perf.lcp < 2500 ? '✅' : '⚠️'}</td></tr>
          <tr><td>${t('we_ttfb')}</td><td>${perf.ttfb || 0}ms</td><td>${perf.ttfb < 800 ? '✅' : '⚠️'}</td></tr>
          <tr><td>${t('we_cls')}</td><td>${perf.cls || 0}</td><td>${perf.cls < 0.1 ? '✅' : '⚠️'}</td></tr>
          <tr><td>${t('we_https')}</td><td>${bp.https ? '✅' : '❌'}</td><td>-</td></tr>
          <tr><td>${t('we_a11y_violations')}</td><td>${violations.length}${t('we_violation_count')}</td><td>${violations.length === 0 ? '✅' : '⚠️'}</td></tr>
          <tr><td>${t('we_ai_latency')}</td><td>${ai.response_latency_ms || 0}ms</td><td>${(ai.response_latency_ms || 0) < 3000 ? '✅' : '⚠️'}</td></tr>
        </table>
        ${violations.length > 0 ? `<div style="margin-top:12px"><h4 style="color:var(--accent-red)">⚠️ ${t('we_a11y_violations')}:</h4>${violations.map(v => `<div style="font-size:12px;color:var(--text-secondary)">• <b>${v.id}</b>: ${v.help}</div>`).join('')}</div>` : ''}`;
    },

    async loadResults() {
        try {
            const data = await api.get('/api/web-eval/results', { page_size: 10 });
            if (!data.items?.length) {
                document.getElementById('weHistory').innerHTML = `<span class="text-muted">${t('we_no_history')}</span>`;
                return;
            }
            document.getElementById('weHistory').innerHTML = data.items.map(r => `
              <div style="padding:6px 0;border-bottom:1px solid var(--bg-tertiary);font-size:12px">
                🌐 ${r.url} · ${t('rp_compare_th_overall')}: <b>${r.overall_score}</b> · ${new Date(r.created_at).toLocaleDateString(getLang() === 'zh' ? 'zh-CN' : 'en-US')}
              </div>
            `).join('');
        } catch (e) { /* ignore */ }
    },
};

export default WebEvalPage;
