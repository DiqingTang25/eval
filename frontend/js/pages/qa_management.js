/* ════════════════════════════════════════════
   QA Management Page — 列表/详情/审核/生成
   ════════════════════════════════════════════ */

import api from '../api.js';
import { showToast, formatDate, truncate } from '../utils.js';

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
              <option value="pending" selected>待审核</option>
              <option value="all">全部</option>
              <option value="approved">已通过</option>
              <option value="rejected">已拒绝</option>
            </select>
            <select id="qaFilterPhase">
              <option value="all">全部阶段</option>
              <option>PHASE 01</option><option>PHASE 02</option><option>PHASE 03</option><option>PHASE 04</option><option>PHASE 05</option>
            </select>
            <select id="qaFilterType">
              <option value="all">全部题型</option>
              <option value="概念解释">概念解释</option><option value="操作步骤">操作步骤</option>
              <option value="对比分析">对比分析</option><option value="应用场景">应用场景</option>
            </select>
            <input id="qaSearch" type="text" placeholder="🔍 搜索问题/答案..." style="width:200px">
            <button class="btn btn-primary btn-sm" id="qaGenerateBtn">🔄 从Excel生成QA</button>
            <button class="btn btn-outline btn-sm" id="qaBatchApproveBtn">✅ 批量通过</button>
            <span id="qaStatsText" style="font-size:12px;color:var(--text-secondary)"></span>
          </div>
          <div class="qa-layout">
            <div class="qa-list" id="qaList"><div class="qa-empty">加载中...</div></div>
            <div class="qa-detail" id="qaDetail"><div class="qa-empty">← 选择一条QA查看详情</div></div>
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
            document.getElementById('qaList').innerHTML = '<div class="qa-empty">加载失败: ' + e.message + '</div>';
        }
    },

    renderList(data) {
        const el = document.getElementById('qaList');
        if (!data.items?.length) {
            el.innerHTML = '<div class="qa-empty">暂无QA数据</div>';
            return;
        }
        el.innerHTML = data.items.map(q => `
          <div class="qa-item ${this.state.selectedId === q.qa_id ? 'selected' : ''}" data-qaid="${q.qa_id}">
            <div class="qa-q">${truncate(q.question, 70)}</div>
            <div class="qa-meta">
              <span>${q.phase}</span> · <span>${q.type}</span>
              <span class="badge badge-${q.status}">${q.status}</span>
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
        let html = `<span class="page-info">${data.total} 条, ${data.page}/${data.total_pages} 页</span>`;
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
            document.getElementById('qaStatsText').textContent =
                `待审:${data.pending} | 通过:${data.approved} | 拒绝:${data.rejected} | 共${data.total}`;
        } catch (e) { /* ignore */ }
    },

    async selectQA(qaId) {
        this.state.selectedId = qaId;
        try {
            const qa = await api.get(`/api/qa/${qaId}`);
            this.renderDetail(qa);
            this.loadList(); // 刷新列表高亮
        } catch (e) {
            showToast('加载QA详情失败', 'error');
        }
    },

    renderDetail(qa) {
        const el = document.getElementById('qaDetail');
        const isPending = qa.status === 'pending';
        el.innerHTML = `
          <h3 style="color:var(--accent-blue);margin-bottom:10px">📝 ${qa.qa_id}</h3>
          <div style="display:flex;gap:12px;margin-bottom:8px;flex-wrap:wrap">
            <span class="badge badge-${qa.status}">${qa.status}</span>
            <span style="font-size:12px;color:var(--text-secondary)">${qa.phase} | ${qa.type} | ${qa.difficulty}</span>
          </div>
          <label>问题</label>
          <textarea id="qaEditQuestion">${qa.question || ''}</textarea>
          <label>黄金答案</label>
          <textarea id="qaEditAnswer" style="min-height:120px">${qa.golden_answer || ''}</textarea>
          <label>知识点</label>
          <div style="font-size:12px;color:var(--text-secondary)">${(qa.knowledge_points || []).join(', ')}</div>
          <label>来源</label>
          <div style="font-size:12px;color:var(--text-muted);background:var(--bg-primary);padding:8px;border-radius:4px">
            ${qa.source?.document || 'N/A'} / ${qa.source?.sheet || ''}
          </div>
          <div style="margin-top:14px;display:flex;gap:8px">
            ${isPending ? `
              <button class="btn btn-success btn-sm" id="qaApproveBtn">✅ 通过</button>
              <button class="btn btn-danger btn-sm" id="qaRejectBtn">❌ 拒绝</button>
              <button class="btn btn-warning btn-sm" id="qaSaveBtn">✏️ 保存修改</button>
            ` : '<span style="color:var(--text-secondary);font-size:13px">已审核 · ' + (qa.reviewer_notes || '') + '</span>'}
            <button class="btn btn-outline btn-sm" id="qaDeleteBtn">🗑 删除</button>
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
            showToast('已通过', 'success');
            this.selectQA(qaId);
            this.loadStats();
        } catch (e) { showToast('操作失败', 'error'); }
    },

    async reject(qaId) {
        const reason = prompt('拒绝原因（可选）:');
        try {
            await api.post(`/api/qa/${qaId}/reject`, { reason: reason || '' });
            showToast('已拒绝', 'success');
            this.selectQA(qaId);
            this.loadStats();
        } catch (e) { showToast('操作失败', 'error'); }
    },

    async saveEdit(qaId) {
        const question = document.getElementById('qaEditQuestion')?.value;
        const golden_answer = document.getElementById('qaEditAnswer')?.value;
        try {
            await api.put(`/api/qa/${qaId}`, { question, golden_answer });
            showToast('修改已保存', 'success');
            this.selectQA(qaId);
            this.loadStats();
        } catch (e) { showToast('保存失败', 'error'); }
    },

    async deleteOne(qaId) {
        if (!confirm('确定删除此QA？')) return;
        try {
            await api.delete(`/api/qa/${qaId}`);
            showToast('已删除', 'success');
            this.state.selectedId = null;
            document.getElementById('qaDetail').innerHTML = '<div class="qa-empty">← 选择一条QA查看详情</div>';
            this.loadList();
            this.loadStats();
        } catch (e) { showToast('删除失败', 'error'); }
    },

    async batchApprove() {
        if (!confirm('确定批量通过当前筛选的所有待审核QA？')) return;
        try {
            const data = await api.get('/api/qa', { status: 'pending', page_size: 100 });
            const ids = (data.items || []).map(q => q.qa_id);
            if (!ids.length) { showToast('没有待审核的QA', 'info'); return; }
            await api.post('/api/qa/batch/approve', { qa_ids: ids });
            showToast(`已批量通过 ${ids.length} 条`, 'success');
            this.loadList();
            this.loadStats();
        } catch (e) { showToast('批量操作失败', 'error'); }
    },

    async generateQA() {
        document.getElementById('qaList').innerHTML = '<div class="qa-empty">⏳ 正在从Excel生成QA...</div>';
        try {
            const data = await api.post('/api/qa/generate');
            showToast(`已生成 ${data.total} 条QA，请审核`, 'success');
            this.state.filterStatus = 'pending';
            document.getElementById('qaFilterStatus').value = 'pending';
            this.loadList();
            this.loadStats();
        } catch (e) {
            showToast('生成失败: ' + e.message, 'error');
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
