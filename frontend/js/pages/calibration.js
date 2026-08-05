/* ════════════════════════════════════════════
   Calibration Workspace v1.0
   人类校准工作台 — 10维度评分 + Cohen's κ统计
   ════════════════════════════════════════════ */

import api from '../api.js';
import { showToast, formatDate, escHtml } from '../utils.js';
import { t, onLangChange } from '../i18n-bridge.js';

const DIMS = ['correctness','relevancy','completeness','guidance','followup_quality','boundary_compliance','turn_consistency','knowledge_scaffolding','overhelping','fairness_bias'];

// v3.6: DIM_LABELS / DIM_DESC 改为从 i18n 字典动态获取
function getDimLabel(d) { return t('dim_' + d); }
function getDimDesc(d) { return t('dim_' + d + '_desc'); }

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
                <h2>${t('cal_title')}</h2>
                <p class="cal-subtitle">${t('cal_subtitle')}</p>
                <div class="cal-toolbar">
                    <button class="btn btn-primary btn-sm" id="cal-load-btn">${t('cal_load_btn')}</button>
                    <button class="btn btn-outline btn-sm" id="cal-results-btn">${t('cal_results_btn')}</button>
                    <button class="btn btn-outline btn-sm" id="cal-generate-btn">${t('cal_generate_btn')}</button>
                    <span class="cal-badge" id="cal-progress-badge">...</span>
                </div>
            </div>
            <div class="cal-main">
                <div class="cal-left" id="cal-items-panel">
                    <div class="cal-panel-header">${t('cal_queue_title')}</div>
                    <div class="cal-items-list" id="cal-items-list">
                        <div class="cal-empty">${t('cal_queue_empty')}</div>
                    </div>
                </div>
                <div class="cal-center" id="cal-scoring-panel">
                    <div class="cal-panel-header">${t('cal_scoring_title')}</div>
                    <div class="cal-empty" id="cal-scoring-empty">${t('cal_scoring_empty')}</div>
                    <div id="cal-scoring-form" style="display:none">
                        <div class="cal-qa-display" id="cal-qa-display"></div>
                        <div class="cal-dims-grid" id="cal-dims-grid"></div>
                        <div class="cal-actions">
                            <button class="btn btn-primary" id="cal-submit-btn">${t('cal_submit_btn')}</button>
                            <button class="btn btn-outline" id="cal-skip-btn">${t('cal_skip_btn')}</button>
                        </div>
                    </div>
                </div>
                <div class="cal-right" id="cal-stats-panel">
                    <div class="cal-panel-header">${t('cal_stats_title')}</div>
                    <div class="cal-stats-content" id="cal-stats-content">
                        <div class="cal-empty">${t('cal_stats_empty')}</div>
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
            if (badge) badge.textContent = t('cal_progress_fmt', p.scored || 0, p.total || 0);
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
            document.getElementById('cal-items-list').innerHTML = `<div class="cal-error">${t('cal_load_fail')}: ${escHtml(e.message)}<br><small>${t('cal_api_unavailable')}</small></div>`;
        } finally {
            this.state.loading = false;
        }
    },

    _renderItemList() {
        const list = document.getElementById('cal-items-list');
        if (!list) return;
        if (this.state.items.length === 0) {
            list.innerHTML = `<div class="cal-empty">${t('cal_queue_no_items')}</div>`;
            return;
        }
        list.innerHTML = this.state.items.map((item, i) => `
            <div class="cal-item ${i === this.state.currentIdx ? 'active' : ''}" data-idx="${i}" onclick="window._calSelect?.(${i})">
                <div class="cal-item-id">#${item.qa_id || item.id || i+1}</div>
                <div class="cal-item-q">${escHtml((item.question || '').substring(0, 60))}...</div>
                <div class="cal-item-meta">${item.type || ''} · ${item.phase || ''}</div>
                ${item.scored ? `<span class="badge badge-ok cal-item-badge">${t('cal_item_scored')}</span>` : `<span class="badge badge-warn cal-item-badge">${t('cal_item_pending')}</span>`}
            </div>
        `).join('');
        window._calSelect = (i) => this._selectItem(i);
    },

    _selectItem(idx) {
        this.state.currentIdx = idx;
        this._renderItemList();
        const item = this.state.items[idx];
        if (!item) return;

        document.getElementById('cal-scoring-empty').style.display = 'none';
        const form = document.getElementById('cal-scoring-form');
        form.style.display = 'block';

        const qaDisplay = document.getElementById('cal-qa-display');
        qaDisplay.innerHTML = `
            <div class="cal-qa-question"><strong>${t('cal_question_label')}</strong> ${escHtml(item.question || '')}</div>
            <div class="cal-qa-answer"><strong>${t('cal_answer_label')}</strong> ${escHtml((item.agent_answer || item.answer || '').substring(0, 500))}</div>
            ${item.golden_answer ? `<div class="cal-qa-golden"><strong>${t('cal_golden_label')}</strong> ${escHtml(item.golden_answer.substring(0, 300))}</div>` : ''}
        `;

        const dimsGrid = document.getElementById('cal-dims-grid');
        dimsGrid.innerHTML = DIMS.map(d => `
            <div class="cal-dim-row">
                <div class="cal-dim-info">
                    <span class="cal-dim-name">${getDimLabel(d)}</span>
                    <span class="cal-dim-desc">${getDimDesc(d)}</span>
                </div>
                <div class="cal-dim-score">
                    ${[1,2,3,4,5].map(s => `
                        <button class="cal-score-btn ${this.state.scores[d] === s ? 'active' : ''}" data-dim="${d}" data-score="${s}" onclick="window._calScore?.('${d}',${s})">${s}</button>
                    `).join('')}
                </div>
                <span class="cal-score-label">${this.state.scores[d] ? t('cal_score_label_fmt', this.state.scores[d]) : t('cal_score_label')}</span>
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
            showToast(t('cal_complete_hint'), 'warn');
            return;
        }
        try {
            await api.post('/api/calibration/score', { qa_id: item.qa_id || item.id, scores });
            showToast(t('cal_submit_success'), 'success');
            item.scored = true;
            this.state.scores = {};
            await this._loadProgress();
            await this._loadStats();
            const next = this.state.currentIdx + 1;
            if (next < this.state.items.length) this._selectItem(next);
        } catch (e) {
            showToast(t('cal_submit_failed') + ': ' + e.message, 'error');
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
                    <div class="cal-stat-row"><span>${t('cal_scored_count')}</span><span class="cal-stat-val">${r.scored_count || 0}/${r.total_count || 0}</span></div>
                    ${r.per_dimension ? Object.entries(r.per_dimension).map(([d,v]) => `
                        <div class="cal-stat-row"><span>${getDimLabel(d)}</span><span class="cal-stat-val">${t('cal_dim_bias')}:${(v.bias||0).toFixed(2)}</span></div>
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
                showToast(t('cal_generate_success'), 'success');
                await this._loadItems();
            } catch (e) { showToast(t('cal_generate_failed') + ': ' + e.message, 'error'); }
        });
        document.getElementById('cal-submit-btn')?.addEventListener('click', () => this._submitScore());
        document.getElementById('cal-skip-btn')?.addEventListener('click', () => {
            const next = this.state.currentIdx + 1;
            if (next < this.state.items.length) { this.state.scores = {}; this._selectItem(next); }
        });
    }
};

export default CalibrationPage;
