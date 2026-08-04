/* ════════════════════════════════════════════
   Report Viewer Page — 历史报告 / 详情 / 对比
   ════════════════════════════════════════════ */

import api from '../api.js';
import { showToast, formatDate, scoreColor } from '../utils.js';
import { drawComparisonChart, destroyChart } from '../charts.js';

const ReportPage = {
    state: { initialized: false, selectedId: null, selectedIds: [] },

    init() { this.state.initialized = true; },
    async render() {
        this.renderLayout();
        await this.loadList();
    },
    destroy() { destroyChart('compareChart'); },

    renderLayout() {
        document.getElementById('page-reports').innerHTML = `
          <div class="page-header">
            <h2>📋 报告查看</h2>
            <div class="flex gap-2">
              <button class="btn btn-outline btn-sm" id="rpCompareBtn" disabled>📊 对比选中报告</button>
              <button class="btn btn-outline btn-sm" id="rpRefreshBtn">🔄 刷新</button>
            </div>
          </div>
          <div class="report-layout">
            <div class="report-list" id="rpList"><div class="qa-empty">加载中...</div></div>
            <div class="report-detail" id="rpDetail"><div class="qa-empty">← 选择一份报告查看详情</div></div>
          </div>
          <div id="rpCompareArea" style="display:none;margin-top:16px">
            <div class="card"><h3 style="color:var(--accent-blue);margin-bottom:12px">📊 报告对比</h3><canvas id="compareChart" height="200"></canvas></div>
            <div id="rpCompareTable" style="margin-top:12px"></div>
          </div>
        `;
        this.bindEvents();
    },

    bindEvents() {
        document.getElementById('rpRefreshBtn').addEventListener('click', () => this.loadList());
        document.getElementById('rpCompareBtn').addEventListener('click', () => this.compare());
    },

    async loadList() {
        try {
            const data = await api.get('/api/reports', { page_size: 30 });
            const el = document.getElementById('rpList');
            if (!data.items?.length) { el.innerHTML = '<div class="qa-empty">暂无报告</div>'; return; }
            el.innerHTML = data.items.map(r => `
              <div class="report-item ${this.state.selectedId === r.id ? 'selected' : ''}" data-id="${r.id}">
                <div style="display:flex;align-items:center;gap:8px">
                  <input type="checkbox" class="rp-check" data-id="${r.id}" ${this.state.selectedIds.includes(r.id) ? 'checked' : ''}>
                  <div style="flex:1;cursor:pointer" class="rp-info" data-id="${r.id}">
                    <div style="font-size:13px">📄 ${formatDate(r.timestamp)}</div>
                    <div style="font-size:12px;color:var(--text-secondary)">综合: <b style="color:${r.overall >= 4 ? 'var(--accent-green)' : r.overall >= 3 ? 'var(--accent-yellow)' : 'var(--accent-red)'}">${r.overall?.toFixed(1) || '?'}</b> · ${r.total || 0}场景 · ${r.agent_id || ''}</div>
                  </div>
                </div>
              </div>
            `).join('');

            // 事件委托
            el.querySelectorAll('.rp-info').forEach(div => {
                div.addEventListener('click', () => this.selectReport(div.dataset.id));
            });
            el.querySelectorAll('.rp-check').forEach(cb => {
                cb.addEventListener('change', (e) => {
                    e.stopPropagation();
                    this.toggleSelection(cb.dataset.id, cb.checked);
                });
            });
        } catch (e) { showToast('加载失败', 'error'); }
    },

    async selectReport(id) {
        this.state.selectedId = id;
        try {
            const r = await api.get(`/api/reports/${id}`);
            this.renderDetail(r);
            this.loadList(); // 刷新高亮
        } catch (e) { showToast('加载报告详情失败', 'error'); }
    },

    renderDetail(r) {
        const el = document.getElementById('rpDetail');
        const s = r.summary_json || {};
        const avg = s.avg_scores || {};
        const boundary = s.boundary || {};
        const dims = [
            { k: 'correctness', l: '正确性' }, { k: 'relevancy', l: '相关性' },
            { k: 'completeness', l: '完整性' }, { k: 'guidance', l: '引导力' },
            { k: 'followup_quality', l: '追问质量' }, { k: 'boundary_compliance', l: '边界合规' },
            { k: 'turn_consistency', l: '跨轮一致' }, { k: 'knowledge_scaffolding', l: '知识递进' },
            { k: 'overhelping', l: '过度帮助' }, { k: 'fairness_bias', l: '公平性' },
        ];

        let html = `<h3 style="color:var(--accent-blue);margin-bottom:8px">📊 ${r.timestamp} · 综合 ${avg.overall?.toFixed(2) || '?'}/5.00</h3>`;

        html += `<table class="data-table" style="margin-top:12px"><tr><th>维度</th><th>得分</th></tr>`;
        dims.forEach(d => {
            const v = avg[d.k] || 0;
            const cls = v >= 4 ? 'var(--accent-green)' : v >= 3 ? 'var(--accent-yellow)' : 'var(--accent-red)';
            html += `<tr><td>${d.l}</td><td style="color:${cls};font-weight:bold">${v.toFixed(2)}</td></tr>`;
        });
        html += `</table>`;

        if (Object.keys(boundary).length) {
            html += `<div style="margin-top:12px;padding:10px;background:var(--bg-primary);border-radius:6px;font-size:13px">
              <b>🛡️ 边界统计</b>: 在范围 ${boundary.in_scope || 0} · 部分匹配 ${boundary.partial_match || 0} · 超出 ${boundary.out_of_scope || 0}</div>`;
        }

        html += `<div class="mt-4 flex gap-2">
          <a class="btn btn-outline btn-sm" href="/api/reports/${r.id}/export?format=json" download>📥 JSON</a>
          <a class="btn btn-outline btn-sm" href="/api/reports/${r.id}/export?format=csv" download>📥 CSV</a>
        </div>`;

        el.innerHTML = html;
    },

    toggleSelection(id, checked) {
        if (checked) {
            if (!this.state.selectedIds.includes(id)) this.state.selectedIds.push(id);
        } else {
            this.state.selectedIds = this.state.selectedIds.filter(i => i !== id);
        }
        const btn = document.getElementById('rpCompareBtn');
        if (btn) btn.disabled = this.state.selectedIds.length < 2;
    },

    async compare() {
        if (this.state.selectedIds.length < 2) { showToast('请选择至少2个报告', 'info'); return; }
        const area = document.getElementById('rpCompareArea');
        area.style.display = 'block';
        try {
            const ids = this.state.selectedIds.join(',');
            const data = await api.get(`/api/reports/compare?ids=${ids}`);
            this.renderComparison(data);
            area.scrollIntoView({ behavior: 'smooth' });
        } catch (e) { showToast('对比失败: ' + e.message, 'error'); }
    },

    renderComparison(data) {
        if (data.reports?.length) {
            drawComparisonChart('compareChart', data.reports);
        }
        if (data.deltas?.length) {
            const table = document.getElementById('rpCompareTable');
            table.innerHTML = `<table class="data-table" style="margin-top:12px">
              <tr><th>维度</th>${data.reports.map(r => `<th>${r.timestamp?.slice(9, 19) || ''}</th>`).join('')}<th>差异</th></tr>
              ${data.deltas.map(d => `<tr>
                <td>${d.dimension}</td>
                ${d.values.map(v => `<td style="font-weight:bold;color:${v >= 4 ? 'var(--accent-green)' : v >= 3 ? 'var(--accent-yellow)' : 'var(--accent-red)'}">${v.toFixed(2)}</td>`).join('')}
                <td style="color:${d.max_delta > 1 ? 'var(--accent-red)' : 'var(--text-secondary)'}">${d.max_delta.toFixed(2)}</td>
              </tr>`).join('')}
            </table>`;
        }
    },
};

export default ReportPage;
