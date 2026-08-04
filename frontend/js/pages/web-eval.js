/* ════════════════════════════════════════════
   Web Eval Page — 网页评测/结果查看
   ════════════════════════════════════════════ */

import api from '../api.js';
import { showToast, formatDate, ringColor, scoreColor } from '../utils.js';

const DIM_LABELS = {
    performance: '性能',
    accessibility: '可访问性',
    best_practices: '最佳实践',
    ai_function: 'AI功能',
    ui_ux: 'UI/UX',
    content: '内容',
};

const DIM_ICONS = {
    performance: '⚡',
    accessibility: '♿',
    best_practices: '✅',
    ai_function: '🤖',
    ui_ux: '🎨',
    content: '📝',
};

const WebEvalPage = {
    state: {
        initialized: false,
        selectedId: null,
        running: false,
        page: 1,
        pageSize: 20,
    },

    init() {
        if (this.state.initialized) return;
        this.state.initialized = true;
    },

    async render() {
        this.renderLayout();
        await this.loadResults();
    },

    destroy() {},

    renderLayout() {
        const el = document.getElementById('page-web-eval');
        el.innerHTML = `
          <div class="page-header"><h2>🌐 网页评测</h2></div>

          <div class="card" style="margin-bottom:16px">
            <h3 style="color:var(--text-secondary);font-size:14px;margin-bottom:12px">🔍 评测配置</h3>
            <div class="flex flex-wrap gap-2 items-center">
              <label style="font-size:13px">URL:</label>
              <input id="weUrl" type="text" value="http://124.174.108.70"
                     style="flex:1;min-width:280px" placeholder="输入目标网页 URL">
              <button class="btn btn-primary" id="weRunBtn">▶ 开始评测</button>
            </div>
            <div id="weProgress" style="display:none;margin-top:12px">
              <div class="progress-bar"><div class="progress-fill" style="width:100%;animation:pulse 1.5s infinite"></div></div>
              <div style="font-size:11px;color:var(--accent-yellow);text-align:center;margin-top:4px">⏳ 评测进行中...</div>
            </div>
          </div>

          <div id="weLatestResult" style="display:none;margin-bottom:16px">
            <div class="card">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
                <h3 style="color:var(--accent-blue)">📊 最新评测结果</h3>
                <button class="btn btn-outline btn-sm" id="weClearLatest">✕ 收起</button>
              </div>
              <div id="weResultContent"></div>
            </div>
          </div>

          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
            <h3 style="color:var(--text-secondary);font-size:14px">📋 评测历史</h3>
            <button class="btn btn-outline btn-sm" id="weRefreshBtn">🔄 刷新</button>
          </div>
          <div id="weResultsList"><div class="qa-empty">加载中...</div></div>
        `;

        // 事件绑定
        document.getElementById('weRunBtn').addEventListener('click', () => this.runEval());
        document.getElementById('weRefreshBtn').addEventListener('click', () => this.loadResults());
        document.getElementById('weClearLatest')?.addEventListener('click', () => {
            document.getElementById('weLatestResult').style.display = 'none';
        });
    },

    // ── 运行评测 ──
    async runEval() {
        const url = document.getElementById('weUrl')?.value?.trim();
        if (!url) { showToast('请输入URL', 'error'); return; }

        this.state.running = true;
        const btn = document.getElementById('weRunBtn');
        const prog = document.getElementById('weProgress');
        if (btn) btn.disabled = true;
        if (prog) prog.style.display = 'block';

        try {
            const data = await api.post('/api/web-eval/run', { url });
            if (data.ok) {
                showToast(`评测完成 · 综合得分: ${data.overall_score?.toFixed(1) || 'N/A'}`, 'success');
                this.renderLatestResult(data.detail || data);
                await this.loadResults();
            } else {
                showToast('评测失败: ' + (data.error || '未知错误'), 'error');
            }
        } catch (e) {
            showToast('请求失败: ' + e.message, 'error');
        } finally {
            this.state.running = false;
            if (btn) btn.disabled = false;
            if (prog) prog.style.display = 'none';
        }
    },

    // ── 最新结果 ──
    renderLatestResult(data) {
        document.getElementById('weLatestResult').style.display = 'block';
        const container = document.getElementById('weResultContent');
        container.innerHTML = this.buildResultHTML(data);
    },

    buildResultHTML(data) {
        const dims = ['performance', 'accessibility', 'best_practices', 'ai_function', 'ui_ux', 'content'];
        const overall = data.overall_score ?? 0;

        const ringCls = ringColor(overall); // 0-100 scale expected
        // WebEvaluator scores are 0-100
        const score5 = overall > 5 ? (overall / 20) : overall; // normalize to 0-5

        const ringCards = dims.map(d => {
            const dimData = data[d] || {};
            const val = typeof dimData === 'object' ? (dimData.score ?? dimData.overall ?? 0) : dimData;
            const numVal = typeof val === 'number' ? val : 0;
            const cls = ringColor(numVal);
            return `
              <div class="score-ring ${cls}" style="width:110px;height:110px">
                <div class="ring-value">${numVal.toFixed(0)}</div>
                <div class="ring-label">${DIM_ICONS[d]} ${DIM_LABELS[d]}</div>
              </div>`;
        }).join('');

        return `
          <div style="text-align:center;margin-bottom:12px">
            <div class="score-ring ${ringCls}" style="width:100px;height:100px;display:inline-flex">
              <div class="ring-value">${overall.toFixed(0)}</div>
              <div class="ring-label">综合得分</div>
            </div>
            <div style="font-size:11px;color:var(--text-muted);margin-top:4px">${data.url || ''}</div>
          </div>
          <div class="ring-cards">${ringCards}</div>
          ${data.raw_result ? `
          <details style="margin-top:12px">
            <summary style="cursor:pointer;font-size:12px;color:var(--text-secondary)">📋 查看原始结果</summary>
            <pre style="background:var(--bg-primary);padding:10px;border-radius:4px;font-size:11px;max-height:300px;overflow:auto;margin-top:8px">${JSON.stringify(data.raw_result, null, 2)}</pre>
          </details>` : ''}
        `;
    },

    // ── 结果列表 ──
    async loadResults() {
        const el = document.getElementById('weResultsList');
        if (!el) return;

        try {
            const data = await api.get('/api/web-eval/results', { page: this.state.page, page_size: this.state.pageSize });
            if (!data.items?.length) {
                el.innerHTML = '<div class="qa-empty">暂无评测结果</div>';
                return;
            }

            el.innerHTML = data.items.map(r => {
                const cls = ringColor(r.overall_score ?? 0);
                return `
              <div class="report-item ${this.state.selectedId === r.id ? 'selected' : ''}" data-we-id="${r.id}">
                <div style="display:flex;justify-content:space-between;align-items:center">
                  <div style="flex:1;cursor:pointer">
                    <div style="font-size:13px">🌐 ${r.url || 'N/A'}</div>
                    <div style="font-size:11px;color:var(--text-muted);margin-top:2px">${formatDate(r.created_at)}</div>
                  </div>
                  <div style="display:flex;align-items:center;gap:8px">
                    <span class="sm-val ${scoreColor((r.overall_score || 0) / 20)}" style="font-size:18px">${(r.overall_score || 0).toFixed(0)}</span>
                    <button class="btn btn-outline btn-sm" data-we-delete="${r.id}">🗑</button>
                  </div>
                </div>
              </div>`;
            }).join('');

            // 分页
            if (data.total_pages > 1) {
                el.innerHTML += `<div class="pagination" style="margin-top:12px">
                  <span class="page-info">${data.total} 条, ${data.page}/${data.total_pages} 页</span>
                  ${data.page > 1 ? `<button data-we-page="${data.page - 1}">◀</button>` : ''}
                  ${data.page < data.total_pages ? `<button data-we-page="${data.page + 1}">▶</button>` : ''}
                </div>`;
            }

            // 事件委托
            el.querySelectorAll('.report-item').forEach(item => {
                item.addEventListener('click', (e) => {
                    if (e.target.closest('[data-we-delete]')) return;
                    this.viewResult(item.dataset.weId);
                });
            });
            el.querySelectorAll('[data-we-delete]').forEach(b => {
                b.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.deleteResult(b.dataset.weDelete);
                });
            });
            el.querySelectorAll('[data-we-page]').forEach(b => {
                b.addEventListener('click', () => {
                    this.state.page = parseInt(b.dataset.wePage);
                    this.loadResults();
                });
            });
        } catch (e) {
            el.innerHTML = `<div class="qa-empty">加载失败: ${e.message}</div>`;
        }
    },

    // ── 查看结果详情 ──
    async viewResult(id) {
        this.state.selectedId = id;
        try {
            const data = await api.get(`/api/web-eval/results/${id}`);
            if (data) {
                this.renderLatestResult(data);
                document.getElementById('weLatestResult').style.display = 'block';
                document.getElementById('weLatestResult').scrollIntoView({ behavior: 'smooth' });
            }
        } catch (e) {
            showToast('加载详情失败', 'error');
        }
        this.loadResults(); // 刷新高亮
    },

    // ── 删除结果 ──
    async deleteResult(id) {
        if (!confirm('确定删除此评测结果？')) return;
        try {
            await api.delete(`/api/web-eval/results/${id}`);
            showToast('已删除', 'success');
            if (this.state.selectedId === id) {
                this.state.selectedId = null;
                document.getElementById('weLatestResult').style.display = 'none';
            }
            this.loadResults();
        } catch (e) {
            showToast('删除失败', 'error');
        }
    },
};

export default WebEvalPage;
