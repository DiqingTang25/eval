/* ════════════════════════════════════════════
   Calibration Workspace v1.0
   人类校准工作台 — 10维度评分 + Cohen's κ统计
   ════════════════════════════════════════════ */

import api from '../api.js';
import { showToast, formatDate, escHtml } from '../utils.js';
import { t, onLangChange } from '../i18n-bridge.js';

const DIMS = ['correctness','relevancy','completeness','guidance','followup_quality','boundary_compliance','turn_consistency','knowledge_scaffolding','overhelping','fairness_bias'];
const DIM_LABELS = { correctness:'事实正确性', relevancy:'答案相关性', completeness:'内容完整性', guidance:'教学引导力', followup_quality:'追问响应', boundary_compliance:'边界合规', turn_consistency:'跨轮一致', knowledge_scaffolding:'知识递进', overhelping:'过度帮助', fairness_bias:'公平性' };
const DIM_DESC = { correctness:'回答的事实准确度，有无幻觉', relevancy:'是否切题', completeness:'关键知识点覆盖', guidance:'Socratic教学法引导', followup_quality:'多轮追问后深入程度', boundary_compliance:'是否在课程边界内', turn_consistency:'多轮信息一致性', knowledge_scaffolding:'知识层层递进', overhelping:'是否直接给代码(反向)', fairness_bias:'不同画像质量一致性' };

const CalibrationPage = {
    state: { initialized: false, items: [], currentIdx: 0, scores: {}, progress: null, results: null, loading: false },

    init() {
        if (this.state.initialized) return;
        onLangChange(() => {
            if (document.getElementById('page-calibration') &&
                document.getElementById('page-calibration').classList.contains('active')) {
                this.render();
            }
        });
        this.state.initialized = true;
    },

    async render() {
        const el = document.getElementById('page-calibration');
        if (!el) return;
        el.innerHTML = this._layout();
        await this._loadProgress();
        await this._loadItems();
        this._bindEvents();
    },

    _layout() {
        return `
        <div class="cal-container">
            <div class="cal-header">
                <h2>🎯 人类校准工作台</h2>
                <p class="cal-subtitle">Human vs LLM Judge 一致性校验 · 10维度评分 · Cohen's κ · Spearman ρ</p>
                <div class="cal-toolbar">
                    <button class="btn btn-primary btn-sm" id="cal-load-btn">📋 加载待校准项</button>
                    <button class="btn btn-outline btn-sm" id="cal-results-btn">📊 查看校准统计</button>
                    <button class="btn btn-outline btn-sm" id="cal-generate-btn">🔄 生成校准集</button>
                    <span class="cal-badge" id="cal-progress-badge">...</span>
                </div>
            </div>
            <div class="cal-main">
                <div class="cal-left" id="cal-items-panel">
                    <div class="cal-panel-header">校准队列</div>
                    <div class="cal-items-list" id="cal-items-list">
                        <div class="cal-empty">点击"加载待校准项"开始</div>
                    </div>
                </div>
                <div class="cal-center" id="cal-scoring-panel">
                    <div class="cal-panel-header">评分面板</div>
                    <div class="cal-empty" id="cal-scoring-empty">← 从左侧选择一个QA对开始评分</div>
                    <div id="cal-scoring-form" style="display:none">
                        <div class="cal-qa-display" id="cal-qa-display"></div>
                        <div class="cal-dims-grid" id="cal-dims-grid"></div>
                        <div class="cal-actions">
                            <button class="btn btn-primary" id="cal-submit-btn">✅ 提交评分</button>
                            <button class="btn btn-outline" id="cal-skip-btn">⏭ 跳过</button>
                        </div>
                    </div>
                </div>
                <div class="cal-right" id="cal-stats-panel">
                    <div class="cal-panel-header">校准统计</div>
                    <div class="cal-stats-content" id="cal-stats-content">
                        <div class="cal-empty">提交评分后查看统计</div>
                    </div>
                </div>
            </div>
        </div>`;
    },

    async _loadProgress() {
        try {
            const p = await api.get('/api/calibration/progress');
            this.state.progress = p;
            const badge = document.getElementById('cal-progress-badge');
            if (badge) badge.textContent = `${p.scored || 0}/${p.total || 0} 已评`;
        } catch (e) { /* calibration API may not be deployed yet */ }
    },

    async _loadItems() {
        this.state.loading = true;
        try {
            const data = await api.get('/api/calibration/items', { limit: 20, unscored_only: true });
            this.state.items = data.items || data || [];
            this.state.currentIdx = 0;
            this._renderItemList();
            if (this.state.items.length > 0) this._selectItem(0);
        } catch (e) {
            document.getElementById('cal-items-list').innerHTML = `<div class="cal-error">加载失败: ${escHtml(e.message)}<br><small>校准API可能未部署，请确保后端运行中</small></div>`;
        } finally {
            this.state.loading = false;
        }
    },

    _renderItemList() {
        const list = document.getElementById('cal-items-list');
        if (!list) return;
        if (this.state.items.length === 0) {
            list.innerHTML = '<div class="cal-empty">无待校准项 · 点击"生成校准集"创建</div>';
            return;
        }
        list.innerHTML = this.state.items.map((item, i) => `
            <div class="cal-item ${i === this.state.currentIdx ? 'active' : ''}" data-idx="${i}" onclick="window._calSelect?.(${i})">
                <div class="cal-item-id">#${item.qa_id || item.id || i+1}</div>
                <div class="cal-item-q">${escHtml((item.question || '').substring(0, 60))}...</div>
                <div class="cal-item-meta">${item.type || ''} · ${item.phase || ''}</div>
                ${item.scored ? '<span class="badge badge-ok cal-item-badge">✓</span>' : '<span class="badge badge-warn cal-item-badge">待评</span>'}
            </div>
        `).join('');
        window._calSelect = (i) => this._selectItem(i);
    },

    _selectItem(idx) {
        this.state.currentIdx = idx;
        this._renderItemList();
        const item = this.state.items[idx];
        if (!item) return;

        // Show scoring form
        document.getElementById('cal-scoring-empty').style.display = 'none';
        const form = document.getElementById('cal-scoring-form');
        form.style.display = 'block';

        // Display QA
        const qaDisplay = document.getElementById('cal-qa-display');
        qaDisplay.innerHTML = `
            <div class="cal-qa-question"><strong>问题:</strong> ${escHtml(item.question || '')}</div>
            <div class="cal-qa-answer"><strong>Agent回答:</strong> ${escHtml((item.agent_answer || item.answer || '').substring(0, 500))}</div>
            ${item.golden_answer ? `<div class="cal-qa-golden"><strong>黄金答案:</strong> ${escHtml(item.golden_answer.substring(0, 300))}</div>` : ''}
        `;

        // Dimension scoring grid
        const dimsGrid = document.getElementById('cal-dims-grid');
        dimsGrid.innerHTML = DIMS.map(d => `
            <div class="cal-dim-row">
                <div class="cal-dim-info">
                    <span class="cal-dim-name">${DIM_LABELS[d]}</span>
                    <span class="cal-dim-desc">${DIM_DESC[d]}</span>
                </div>
                <div class="cal-dim-score">
                    ${[1,2,3,4,5].map(s => `
                        <button class="cal-score-btn ${this.state.scores[d] === s ? 'active' : ''}" data-dim="${d}" data-score="${s}" onclick="window._calScore?.('${d}',${s})">${s}</button>
                    `).join('')}
                </div>
                <span class="cal-score-label">${this.state.scores[d] ? this.state.scores[d]+'/5' : '未评'}</span>
            </div>
        `).join('');

        window._calScore = (dim, score) => {
            this.state.scores[dim] = score;
            this._selectItem(idx);
        };
    },

    async _submitScore() {
        const item = this.state.items[this.state.currentIdx];
        if (!item) return;
        const scores = this.state.scores;
        if (Object.keys(scores).length < 8) {
            showToast('请至少完成8个维度的评分', 'warn');
            return;
        }
        try {
            await api.post('/api/calibration/score', { qa_id: item.qa_id || item.id, scores });
            showToast('评分已提交 ✅', 'success');
            item.scored = true;
            this.state.scores = {};
            await this._loadProgress();
            await this._loadStats();
            // Move to next
            const next = this.state.currentIdx + 1;
            if (next < this.state.items.length) this._selectItem(next);
        } catch (e) {
            showToast(`提交失败: ${e.message}`, 'error');
        }
    },

    async _loadStats() {
        try {
            const r = await api.get('/api/calibration/results');
            this.state.results = r;
            const content = document.getElementById('cal-stats-content');
            if (content) {
                content.innerHTML = `
                    <div class="cal-stat-row"><span>Cohen's κ</span><span class="cal-stat-val">${(r.cohens_kappa || 0).toFixed(3)}</span></div>
                    <div class="cal-stat-row"><span>Spearman ρ</span><span class="cal-stat-val">${(r.spearman_rho || 0).toFixed(3)}</span></div>
                    <div class="cal-stat-row"><span>MAE</span><span class="cal-stat-val">${(r.mae || 0).toFixed(2)}</span></div>
                    <div class="cal-stat-row"><span>已标注</span><span class="cal-stat-val">${r.scored_count || 0}/${r.total_count || 0}</span></div>
                    ${r.per_dimension ? Object.entries(r.per_dimension).map(([d,v]) => `
                        <div class="cal-stat-row"><span>${DIM_LABELS[d]||d}</span><span class="cal-stat-val">偏差:${(v.bias||0).toFixed(2)}</span></div>
                    `).join('') : ''}
                `;
            }
        } catch (e) { /* stats not available yet */ }
    },

    _bindEvents() {
        document.getElementById('cal-load-btn')?.addEventListener('click', () => this._loadItems());
        document.getElementById('cal-results-btn')?.addEventListener('click', () => this._loadStats());
        document.getElementById('cal-generate-btn')?.addEventListener('click', async () => {
            try {
                await api.post('/api/calibration/generate', { count: 20 });
                showToast('校准集已生成 ✅');
                await this._loadItems();
            } catch (e) { showToast(`生成失败: ${e.message}`, 'error'); }
        });
        document.getElementById('cal-submit-btn')?.addEventListener('click', () => this._submitScore());
        document.getElementById('cal-skip-btn')?.addEventListener('click', () => {
            const next = this.state.currentIdx + 1;
            if (next < this.state.items.length) { this.state.scores = {}; this._selectItem(next); }
        });
    }
};

export default CalibrationPage;
