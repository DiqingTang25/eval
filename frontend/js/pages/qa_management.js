/* ════════════════════════════════════════════
   QA Management Page — 列表/详情/审核/生成
   ════════════════════════════════════════════ */

import api from '../api.js';
import { showToast, formatDate, truncate } from '../utils.js';
import { t, onLangChange, tStatus } from '../i18n-bridge.js';

const QAPage = {
    state: {
        initialized: false,
        selectedId: null,
        filterStatus: 'pending',
        filterPhase: 'all',
        filterType: 'all',
        filterDifficulty: 'all',
        search: '',
        page: 1,
        pageSize: 20,
    },

    init() {
        if (this.state.initialized) {
            this.bindDetailEvents();
            return;
        }
        this.state.initialized = true;
        // 语言切换时重新渲染 (仅当本页面处于激活状态)
        onLangChange(() => {
            if (document.getElementById('page-qa') &&
                document.getElementById('page-qa').classList.contains('active')) {
                this.render();
            }
        });
    },

    async render() {
        this.renderLayout();
        await this.loadList();
        await this.loadStats();
        this.bindDetailEvents();
    },

    destroy() {},

    renderLayout() {
        const el = document.getElementById('page-qa');
        el.innerHTML = `
          <div class="filter-bar">
            <select id="qaFilterStatus">
              <option value="pending" selected>${t('qa_filter_pending')}</option>
              <option value="all">${t('qa_filter_all')}</option>
              <option value="approved">${t('qa_filter_approved')}</option>
              <option value="rejected">${t('qa_filter_rejected')}</option>
            </select>
            <select id="qaFilterPhase">
              <option value="all">${t('qa_filter_all_phase')}</option>
              <option>PHASE 01</option><option>PHASE 02</option><option>PHASE 03</option><option>PHASE 04</option><option>PHASE 05</option>
            </select>
            <select id="qaFilterType">
              <option value="all">${t('qa_filter_all_type')}</option>
              <option value="概念解释">${t('qa_type_concept')}</option><option value="操作步骤">${t('qa_type_procedure')}</option>
              <option value="对比分析">${t('qa_type_comparison')}</option><option value="应用场景">${t('qa_type_scenario')}</option>
            </select>
            <input id="qaSearch" type="text" placeholder="${t('qa_search_ph')}" style="width:200px">
            <button class="btn btn-primary btn-sm" id="qaGenerateBtn">${t('qa_generate_btn')}</button>
            <button class="btn btn-outline btn-sm" id="qaBatchApproveBtn">${t('qa_batch_approve_btn')}</button>
            <span id="qaStatsText" style="font-size:12px;color:var(--text-secondary)"></span>
          </div>
          <div class="qa-layout">
            <div class="qa-list" id="qaList"><div class="qa-empty">${t('sys_loading')}</div></div>
            <div class="qa-detail" id="qaDetail"><div class="qa-empty">${t('qa_select_hint')}</div></div>
          </div>
          <div class="pagination" id="qaPagination"></div>
        `;
    },

    bindDetailEvents() {
        // 使用事件委托
        document.getElementById('page-qa').onclick = (e) => {
            if (e.target.id === 'qaGenerateBtn') this.generateQA();
            if (e.target.id === 'qaBatchApproveBtn') this.batchApprove();
            if (e.target.classList.contains('qa-item')) this.selectQA(e.target.dataset.qaid);
        };
        document.getElementById('page-qa').onchange = (e) => {
            if (['qaFilterStatus', 'qaFilterPhase', 'qaFilterType'].includes(e.target.id)) {
                this.state.filterStatus = document.getElementById('qaFilterStatus')?.value || 'pending';
                this.state.filterPhase = document.getElementById('qaFilterPhase')?.value || 'all';
                this.state.filterType = document.getElementById('qaFilterType')?.value || 'all';
                this.state.page = 1;
                this.loadList();
            }
        };
        document.getElementById('qaSearch')?.addEventListener('input', (e) => {
            this.state.search = e.target.value;
            this.state.page = 1;
            this.debouncedLoad();
        });
    },

    async loadList() {
        const { filterStatus, filterPhase, filterType, search, page, pageSize } = this.state;
        try {
            const data = await api.get('/api/qa', {
                status: filterStatus, phase: filterPhase, type: filterType,
                search, page, page_size: pageSize,
            });
            this.renderList(data);
            this.renderPagination(data);
        } catch (e) {
            document.getElementById('qaList').innerHTML = '<div class="qa-empty">' + t('load_failed').replace('{0}', e.message) + '</div>';
        }
    },

    renderList(data) {
        const el = document.getElementById('qaList');
        if (!data.items?.length) {
            el.innerHTML = '<div class="qa-empty">' + t('qa_no_data') + '</div>';
            return;
        }
        el.innerHTML = data.items.map(q => `
          <div class="qa-item ${this.state.selectedId === q.qa_id ? 'selected' : ''}" data-qaid="${q.qa_id}">
            <div class="qa-q">${truncate(q.question, 70)}</div>
            <div class="qa-meta">
              <span>${q.phase}</span> · <span>${q.type}</span>
              <span class="badge badge-${q.status}">${tStatus(q.status)}</span>
            </div>
          </div>
        `).join('');
    },

    renderPagination(data) {
        const el = document.getElementById('qaPagination');
        if (!el || data.total_pages <= 1) {
            if (el) el.innerHTML = '';
            return;
        }
        let html = `<span class="page-info">${t('qa_page_of', data.total, data.page, data.total_pages).replace('{0}', data.total).replace('{1}', data.page).replace('{2}', data.total_pages)}</span>`;
        if (data.page > 1) html = `<button data-page="${data.page - 1}">◀</button>` + html;
        if (data.page < data.total_pages) html += `<button data-page="${data.page + 1}">▶</button>`;
        el.innerHTML = html;
        el.querySelectorAll('button').forEach(b => {
            b.addEventListener('click', () => {
                this.state.page = parseInt(b.dataset.page);
                this.loadList();
            });
        });
    },

    async loadStats() {
        try {
            const data = await api.get('/api/qa/stats');
            document.getElementById('qaStatsText').textContent = t('qa_stats_fmt')
                .replace('{0}', data.pending).replace('{1}', data.approved)
                .replace('{2}', data.rejected).replace('{3}', data.total);
        } catch (e) { /* ignore */ }
    },

    async selectQA(qaId) {
        this.state.selectedId = qaId;
        try {
            const qa = await api.get(`/api/qa/${qaId}`);
            this.renderDetail(qa);
            this.loadList(); // 刷新列表高亮
        } catch (e) {
            showToast(t('qa_load_detail_failed'), 'error');
        }
    },

    renderDetail(qa) {
        const el = document.getElementById('qaDetail');
        const isPending = qa.status === 'pending';
        el.innerHTML = `
          <h3 style="color:var(--accent-blue);margin-bottom:10px">${t('qa_detail_title_prefix')}${qa.qa_id}</h3>
          <div style="display:flex;gap:12px;margin-bottom:8px;flex-wrap:wrap">
            <span class="badge badge-${qa.status}">${tStatus(qa.status)}</span>
            <span style="font-size:12px;color:var(--text-secondary)">${qa.phase} | ${qa.type} | ${qa.difficulty}</span>
          </div>
          <label>${t('qa_question_label')}</label>
          <textarea id="qaEditQuestion">${qa.question || ''}</textarea>
          <label>${t('qa_answer_label')}</label>
          <textarea id="qaEditAnswer" style="min-height:120px">${qa.golden_answer || ''}</textarea>
          <label>${t('qa_knowledge_points')}</label>
          <div style="font-size:12px;color:var(--text-secondary)">${(qa.knowledge_points || []).join(', ')}</div>
          <label>${t('qa_source_label')}</label>
          <div style="font-size:12px;color:var(--text-muted);background:var(--bg-primary);padding:8px;border-radius:4px">
            ${qa.source?.document || 'N/A'} / ${qa.source?.sheet || ''}
          </div>
          <div style="margin-top:14px;display:flex;gap:8px">
            ${isPending ? `
              <button class="btn btn-success btn-sm" id="qaApproveBtn">${t('qa_approve_btn')}</button>
              <button class="btn btn-danger btn-sm" id="qaRejectBtn">${t('qa_reject_btn')}</button>
              <button class="btn btn-warning btn-sm" id="qaSaveBtn">${t('qa_save_btn')}</button>
            ` : '<span style="color:var(--text-secondary);font-size:13px">' + t('qa_already_reviewed_prefix') + (qa.reviewer_notes || '') + '</span>'}
            <button class="btn btn-outline btn-sm" id="qaDeleteBtn">${t('qa_delete_btn')}</button>
          </div>
        `;

        // 绑定按钮事件
        document.getElementById('qaApproveBtn')?.addEventListener('click', () => this.approve(qa.qa_id));
        document.getElementById('qaRejectBtn')?.addEventListener('click', () => this.reject(qa.qa_id));
        document.getElementById('qaSaveBtn')?.addEventListener('click', () => this.saveEdit(qa.qa_id));
        document.getElementById('qaDeleteBtn')?.addEventListener('click', () => this.deleteOne(qa.qa_id));
    },

    async approve(qaId) {
        try {
            await api.post(`/api/qa/${qaId}/approve`);
            showToast(t('qa_approved'), 'success');
            this.selectQA(qaId);
            this.loadStats();
        } catch (e) { showToast(t('operation_failed'), 'error'); }
    },

    async reject(qaId) {
        const reason = prompt(t('qa_reject_reason_prompt'));
        try {
            await api.post(`/api/qa/${qaId}/reject`, { reason: reason || '' });
            showToast(t('qa_rejected'), 'success');
            this.selectQA(qaId);
            this.loadStats();
        } catch (e) { showToast(t('operation_failed'), 'error'); }
    },

    async saveEdit(qaId) {
        const question = document.getElementById('qaEditQuestion')?.value;
        const golden_answer = document.getElementById('qaEditAnswer')?.value;
        try {
            await api.put(`/api/qa/${qaId}`, { question, golden_answer });
            showToast(t('qa_saved'), 'success');
            this.selectQA(qaId);
            this.loadStats();
        } catch (e) { showToast(t('qa_save_failed'), 'error'); }
    },

    async deleteOne(qaId) {
        if (!confirm(t('qa_confirm_delete'))) return;
        try {
            await api.delete(`/api/qa/${qaId}`);
            showToast(t('qa_deleted'), 'success');
            this.state.selectedId = null;
            document.getElementById('qaDetail').innerHTML = '<div class="qa-empty">' + t('qa_select_hint') + '</div>';
            this.loadList();
            this.loadStats();
        } catch (e) { showToast(t('qa_delete_failed'), 'error'); }
    },

    async batchApprove() {
        if (!confirm(t('qa_batch_confirm'))) return;
        try {
            const data = await api.get('/api/qa', { status: 'pending', page_size: 100 });
            const ids = (data.items || []).map(q => q.qa_id);
            if (!ids.length) { showToast(t('qa_batch_none'), 'info'); return; }
            await api.post('/api/qa/batch/approve', { qa_ids: ids });
            showToast(t('qa_batch_success').replace('{0}', ids.length), 'success');
            this.loadList();
            this.loadStats();
        } catch (e) { showToast(t('qa_batch_failed'), 'error'); }
    },

    async generateQA() {
        document.getElementById('qaList').innerHTML = '<div class="qa-empty">' + t('qa_generating') + '</div>';
        try {
            const data = await api.post('/api/qa/generate');
            showToast(t('qa_generate_success').replace('{0}', data.total), 'success');
            this.state.filterStatus = 'pending';
            document.getElementById('qaFilterStatus').value = 'pending';
            this.loadList();
            this.loadStats();
        } catch (e) {
            showToast(t('qa_generate_failed').replace('{0}', e.message), 'error');
            this.loadList();
        }
    },
};

// debounced search
let searchTimer;
QAPage.debouncedLoad = function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => QAPage.loadList(), 400);
};

export default QAPage;
