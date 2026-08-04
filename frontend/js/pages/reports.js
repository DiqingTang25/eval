/* ════════════════════════════════════════════
   Reports Page — 报告列表/详情/对比/导出
   ════════════════════════════════════════════ */

import api from '../api.js';
import { drawRadarChart, drawComparisonChart, destroyChart } from '../charts.js';
import { showToast, scoreColor, scoreText, formatDate, ringColor } from '../utils.js';

const ReportsPage = {
    state: {
        initialized: false,
        selectedId: null,
        compareMode: false,
        compareIds: [],
        page: 1,
        pageSize: 20,
    },

    init() {
        if (this.state.initialized) return;
        this.state.initialized = true;
    },

    async render() {
        this.renderLayout();
        await this.loadList();
    },

    destroy() {
        destroyChart('reportRadarChart');
        destroyChart('reportCompareChart');
    },

    renderLayout() {
        const el = document.getElementById('page-reports');
        el.innerHTML = `
          <div class="page-header" style="display:flex;justify-content:space-between;align-items:center">
            <h2>📋 报告查看</h2>
            <div style="display:flex;gap:8px">
              <button class="btn btn-outline btn-sm" id="rpCompareToggle">
                ${this.state.compareMode ? '✕ 退出对比' : '⚖️ 对比模式'}
              </button>
              <button class="btn btn-outline btn-sm" id="rpRefreshBtn">🔄 刷新</button>
            </div>
          </div>
          <div class="report-layout">
            <div class="report-list" id="rpList"><div class="qa-empty">加载中...</div></div>
            <div class="report-detail" id="rpDetail"><div class="qa-empty">← 选择一个报告查看详情</div></div>
          </div>
        `;

        // 绑定事件
        document.getElementById('rpCompareToggle').addEventListener('click', () => this.toggleCompare());
        document.getElementById('rpRefreshBtn').addEventListener('click', () => { this.state.page = 1; this.loadList(); });
    },

    // ── 列表加载 ──
    async loadList() {
        const el = document.getElementById('rpList');
        if (!el) return;
        try {
            const data = await api.get('/api/reports', { page: this.state.page, page_size: this.state.pageSize });
            this.renderList(data);
        } catch (e) {
            el.innerHTML = `<div class="qa-empty">加载失败: ${e.message}</div>`;
        }
    },

    renderList(data) {
        const el = document.getElementById('rpList');
        if (!data.items?.length) {
            el.innerHTML = '<div class="qa-empty">暂无报告</div>';
            return;
        }

        const items = data.items.map(r => {
            const cls = scoreColor(r.overall);
            const selected = this.state.selectedId === r.id ? 'selected' : '';
            const checked = this.state.compareIds.includes(r.id) ? '☑' : '☐';
            return `
              <div class="report-item ${selected}" data-report-id="${r.id}">
                <div style="display:flex;justify-content:space-between;align-items:center">
                  <div style="flex:1;cursor:pointer" data-action="select">
                    <div style="font-size:13px">📄 ${formatDate(r.timestamp)}</div>
                    <div style="font-size:12px;color:var(--text-muted);margin-top:2px">
                      ${r.agent_id || 'N/A'} · ${r.total || 0}场景
                    </div>
                  </div>
                  <div style="display:flex;align-items:center;gap:8px">
                    <span class="sm-val ${cls}" style="font-size:18px">${r.overall.toFixed(1)}</span>
                    ${this.state.compareMode ? `<span style="cursor:pointer;font-size:16px" data-action="check">${checked}</span>` : ''}
                  </div>
                </div>
              </div>`;
        }).join('');

        // 分页
        let pagination = '';
        if (data.total_pages > 1) {
            pagination = `<div class="pagination" style="margin-top:12px">
              <span class="page-info">${data.total} 条, ${data.page}/${data.total_pages} 页</span>
              ${data.page > 1 ? `<button data-rp-page="${data.page - 1}">◀</button>` : ''}
              ${data.page < data.total_pages ? `<button data-rp-page="${data.page + 1}">▶</button>` : ''}
            </div>`;
        }

        el.innerHTML = items + pagination;

        // 事件委托
        el.querySelectorAll('.report-item').forEach(item => {
            item.addEventListener('click', (e) => {
                const id = item.dataset.reportId;
                const action = e.target.closest('[data-action]')?.dataset?.action;
                if (action === 'check') {
                    this.toggleCompareId(id);
                    e.stopPropagation();
                } else {
                    this.selectReport(id);
                }
            });
        });

        el.querySelectorAll('[data-rp-page]').forEach(b => {
            b.addEventListener('click', () => {
                this.state.page = parseInt(b.dataset.rpPage);
                this.loadList();
            });
        });
    },

    // ── 选择报告 ──
    async selectReport(id) {
        if (this.state.compareMode) {
            this.toggleCompareId(id);
            return;
        }
        this.state.selectedId = id;
        // 立即显示加载状态
        const el = document.getElementById('rpDetail');
        if (el) el.innerHTML = '<div class="rpt-loading"><div class="rpt-spinner"></div><span style="color:var(--text-secondary)">加载中...</span></div>';

        try {
            // v3.6: 从DB API获取报告详情
            const detail = await api.get(`/api/reports/${id}`);

            // 如果有 html_content, 直接展示HTML
            if (detail.html_content) {
                this.renderHtmlContent(detail);
                this.loadList();
                return;
            }

            // 尝试加载文件报告获取完整数据(含 evidence)
            let fullData = null;
            if (detail.json_path) {
                try {
                    const name = detail.json_path.replace(/\\/g,'/').split('/').pop().replace('.json','');
                    const fd = await api.get('/api/reports/file/' + name);
                    if (fd) fullData = fd;
                } catch(e) { /* 降级 */ }
            }
            if (!fullData && detail.timestamp) {
                try {
                    const filesR = await api.get('/api/reports/files');
                    const items = filesR.items || [];
                    const ts = (detail.timestamp || '').replace(/[-: ]/g, '').substring(0, 11);
                    for (const item of items) {
                        if (item.name.includes(ts) && item.formats && item.formats.json) {
                            try {
                                const fd = await api.get('/api/reports/file/' + item.name);
                                if (fd) { fullData = fd; break; }
                            } catch(e) {}
                        }
                    }
                } catch(e) { /* 降级 */ }
            }
            this.renderDetail(detail, fullData);
            this.loadList();
        } catch (e) {
            if (el) el.innerHTML = '<div class="qa-empty">加载失败: ' + e.message + '</div>';
            showToast('加载报告详情失败', 'error');
        }
    },

    // v3.6: 直接渲染MySQL中的HTML内容
    renderHtmlContent(detail) {
        const el = document.getElementById('rpDetail');
        el.innerHTML = `
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
            <div>
              <h3 style="color:var(--accent-blue);margin-bottom:4px">📋 评测报告</h3>
              <div style="font-size:12px;color:var(--text-muted)">${detail.timestamp || ''} · ID: ${(detail.id||'').substring(0,8)}...</div>
            </div>
            <div style="display:flex;gap:8px">
              <button class="btn btn-outline btn-sm" onclick="window.print()">🖨 打印/PDF</button>
              <button class="btn btn-outline btn-sm" id="rpDeleteBtn">🗑 删除</button>
            </div>
          </div>
          <div class="card" style="padding:20px 24px">
            <div class="report-html-content">${detail.html_content}</div>
          </div>
          <div style="display:flex;gap:8px;margin-top:12px">
            <a class="btn btn-outline btn-sm" href="/test/api/reports/${detail.id}/export?format=json" download>📥 导出 JSON</a>
            <a class="btn btn-outline btn-sm" href="/test/api/reports/${detail.id}/export?format=csv" download>📊 导出 CSV</a>
          </div>
        `;

        document.getElementById('rpDeleteBtn')?.addEventListener('click', () => this.deleteReport(detail.id));
    },

    renderDetail(detail, fullData) {
        const el = document.getElementById('rpDetail');
        if (!detail || !detail.summary_json) {
            el.innerHTML = '<div class="qa-empty">报告数据为空</div>';
            return;
        }

        const summary = detail.summary_json;
        const avg = summary.avg_scores || {};
        const boundary = summary.boundary || {};
        const extra = (fullData && fullData.extra) || summary.extra || {};
        const evidence = (fullData && fullData.evidence) || extra.evidence || {};
        const dims = [
            { key: 'correctness', label: '正确性', icon: '📐' },
            { key: 'relevancy', label: '相关性', icon: '🎯' },
            { key: 'completeness', label: '完整性', icon: '📋' },
            { key: 'guidance', label: '引导力', icon: '🧭' },
            { key: 'followup_quality', label: '追问质量', icon: '🔄' },
            { key: 'boundary_compliance', label: '边界合规', icon: '🛡️' },
            { key: 'turn_consistency', label: '跨轮一致', icon: '🔗' },
            { key: 'knowledge_scaffolding', label: '知识递进', icon: '📈' },
            { key: 'overhelping', label: '过度帮助', icon: '⚠️' },
            { key: 'fairness_bias', label: '公平性', icon: '⚖️' },
        ];

        const ringCls = ringColor((avg.overall || 0) * 20);
        const selfHash = evidence.report_self_hash || '';
        const configFp = evidence.config_fingerprint || '';
        const chain = evidence.scenario_chain || [];
        const conf = evidence.confidence || extra.confidence || {};
        const dimsConf = conf.dimensions || {};
        const jc = evidence.judge_consensus || extra.judge_consensus || {};

        // ── 置信度表 ──
        let confTable = '';
        if (Object.keys(dimsConf).length) {
            confTable = `<div class="card" style="margin-bottom:12px;font-size:11px">
              <h4 style="color:var(--text-secondary);margin-bottom:8px">📊 置信度 & 可靠性分析</h4>
              <div style="font-size:10px;color:var(--text-muted);margin-bottom:6px">CV<10%=高可信🟢 | 10-25%=中可信🟡 | 25-50%=低可信🟠 | >50%=不可靠🔴</div>
              ${conf.overall_reliability ? `<div style="font-weight:700;margin-bottom:6px">整体: ${conf.overall_reliability}</div>` : ''}
              <table class="conf-table"><thead><tr><th>维度</th><th>均值</th><th>CV</th><th>95%CI</th><th>可靠性</th></tr></thead><tbody>
              ${dims.filter(d => dimsConf[d.key]).map(d => {
                  const c = dimsConf[d.key]; const cv = c.cv;
                  const cvStr = cv!=null&&cv!==Infinity ? (cv*100).toFixed(1)+'%' : 'N/A';
                  const ci = c.ci_95; const ciStr = ci ? '['+ci[0].toFixed(1)+','+ci[1].toFixed(1)+']' : '—';
                  return `<tr><td>${d.icon} ${d.label}</td><td style="font-weight:700">${c.mean||'-'}</td><td>${cvStr}</td><td style="font-size:10px">${ciStr}</td><td>${c.reliability||'-'}</td></tr>`;
              }).join('')}
              </tbody></table></div>`;
        }

        // ── 证据链 ──
        let evidenceBox = '';
        if (selfHash || chain.length) {
            evidenceBox = `<div class="card" style="margin-bottom:12px;font-size:11px">
              <h4 style="color:var(--text-secondary);margin-bottom:8px">🔐 证据链 · 报告完整性证明</h4>
              ${selfHash ? `<div class="evidence-box"><span style="font-size:18px">🔒</span> <strong>报告自校验哈希</strong><br><span class="hash-badge" title="${selfHash}">${selfHash.substring(0,8)}...${selfHash.substring(selfHash.length-8)}</span> <button onclick="navigator.clipboard.writeText('${selfHash}')" style="font-size:10px;padding:2px 6px;border:1px solid var(--bg-tertiary);border-radius:4px;background:var(--surface-2);color:var(--text-muted);cursor:pointer" title="复制完整哈希">📋</button><br><span style="font-size:10px;color:var(--text-muted)">SHA-256(完整报告) — 任何修改都会改变此哈希</span></div>` : ''}
              ${configFp ? `<div style="font-size:10px;color:var(--text-muted);margin:4px 0">⚙️ 配置指纹: <code>${configFp}</code></div>` : ''}
              ${chain.length ? `<div style="margin-top:6px"><strong>🔗 场景哈希链:</strong><div class="hash-chain">${chain.map((n,i) => `<div class="hash-node"><div class="hx">${n.hash}</div><div class="hl">场景${n.index}·${(n.overall||0).toFixed(1)}分</div></div>${i<chain.length-1?'<div class="hash-link">→</div>':''}`).join('')}</div></div>` : ''}
            </div>`;
        }

        // ── Judge 共识 ──
        let judgeBox = '';
        if (jc.consensus_level) {
            judgeBox = `<div class="card" style="margin-bottom:12px;font-size:11px">
              <h4 style="color:var(--text-secondary);margin-bottom:6px">⚖️ 多Judge共识</h4>
              <div>${jc.consensus_level}</div>
              <div style="font-size:10px;color:var(--text-muted)">${jc.avg_judges_per_scenario}人/场景 · 方差${(jc.avg_variance||0).toFixed(3)} · 否决${jc.veto_scenarios||0}场景</div>
            </div>`;
        }

        el.innerHTML = `
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px">
            <div>
              <h3 style="color:var(--accent-blue);margin-bottom:4px">📋 评测报告</h3>
              <div style="font-size:12px;color:var(--text-muted)">${detail.timestamp || ''}</div>
              <div style="font-size:12px;color:var(--text-muted)">Agent: ${summary.agent_id || 'N/A'} · ${summary.total || 0} 场景</div>
            </div>
            <div class="score-ring ${ringCls}" style="width:80px;height:80px">
              <div class="ring-value">${(avg.overall || 0).toFixed(1)}</div>
              <div class="ring-label">综合得分</div>
            </div>
          </div>

          <div class="score-mini-grid" style="margin-bottom:12px">
            ${dims.map(d => {
                const v = avg[d.key] || 0;
                const expText = (summary.explanations||{})[d.key] || '';
                return `<div class="score-mini" title="${expText}">
                  <div class="sm-val ${scoreColor(v)}">${v.toFixed(1)}</div>
                  <div class="sm-label">${d.icon} ${d.label}</div>
                  <div class="sm-exp">${expText.substring(0,40) || scoreText(v)}</div>
                </div>`;
            }).join('')}
          </div>

          ${evidenceBox}
          ${confTable}
          ${judgeBox}

          ${Object.keys(boundary).length ? `
          <div class="card" style="margin-bottom:12px;font-size:12px">
            <h4 style="color:var(--text-secondary);margin-bottom:6px">🛡️ 边界检测统计</h4>
            <div style="display:flex;gap:16px">
              <span>✅ 范围内: ${boundary.in_scope || 0}</span>
              <span>⚠️ 部分匹配: ${boundary.partial_match || 0}</span>
              <span>❌ 超出范围: ${boundary.out_of_scope || 0}</span>
            </div>
          </div>` : ''}

          <div class="card" style="min-height:240px;margin-bottom:12px">
            <h4 style="color:var(--text-secondary);font-size:13px;margin-bottom:8px">🎯 维度分布</h4>
            <canvas id="reportRadarChart" height="200"></canvas>
          </div>

          <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap;align-items:center">
            ${detail.json_path ? `<a class="btn btn-sm" style="background:linear-gradient(135deg,var(--accent-blue),#2563eb);color:#fff;font-weight:600;padding:8px 18px;border-radius:8px;text-decoration:none;box-shadow:0 2px 8px rgba(37,99,235,.3)" href="/test/reports/${detail.json_path.replace(/\\\\/g,'/').split('/').pop().replace('.json','')}.html" target="_blank">📄 查看完整HTML报告 (含证据链+置信度)</a>` : (fullData && fullData.timestamp ? `<a class="btn btn-sm" style="background:linear-gradient(135deg,var(--accent-blue),#2563eb);color:#fff;font-weight:600;padding:8px 18px;border-radius:8px;text-decoration:none;box-shadow:0 2px 8px rgba(37,99,235,.3)" href="/test/reports/report_${fullData.timestamp}.html" target="_blank">📄 查看完整HTML报告 (含证据链+置信度)</a>` : '')}
            <a class="btn btn-outline btn-sm" href="/test/api/reports/${detail.id}/export?format=json" download>📥 JSON</a>
            <a class="btn btn-outline btn-sm" href="/test/api/reports/${detail.id}/export?format=csv" download>📊 CSV</a>
            <button class="btn btn-danger btn-sm" id="rpDeleteBtn">🗑 删除</button>
          </div>
        `;

        // 雷达图
        setTimeout(() => drawRadarChart('reportRadarChart', avg), 100);

        // 按钮事件
        document.getElementById('rpExportJson')?.addEventListener('click', () => this.exportReport(detail.id, 'json'));
        document.getElementById('rpExportCsv')?.addEventListener('click', () => this.exportReport(detail.id, 'csv'));
        document.getElementById('rpDeleteBtn')?.addEventListener('click', () => this.deleteReport(detail.id));
    },

    // ── 对比模式 ──
    toggleCompare() {
        this.state.compareMode = !this.state.compareMode;
        this.state.compareIds = [];
        document.getElementById('rpDetail').innerHTML =
            '<div class="qa-empty">' + (this.state.compareMode ? '勾选 2-5 个报告进行对比' : '← 选择一个报告查看详情') + '</div>';
        this.loadList();
        const btn = document.getElementById('rpCompareToggle');
        if (btn) btn.textContent = this.state.compareMode ? '✕ 退出对比' : '⚖️ 对比模式';
    },

    toggleCompareId(id) {
        const idx = this.state.compareIds.indexOf(id);
        if (idx >= 0) {
            this.state.compareIds.splice(idx, 1);
        } else {
            if (this.state.compareIds.length >= 5) {
                showToast('最多对比5个报告', 'info');
                return;
            }
            this.state.compareIds.push(id);
        }
        this.loadList();

        // 自动加载对比视图
        if (this.state.compareIds.length >= 2) {
            this.loadComparison();
        }
    },

    async loadComparison() {
        if (this.state.compareIds.length < 2) return;
        try {
            const data = await api.get('/api/reports/compare', { ids: this.state.compareIds.join(',') });
            this.renderComparison(data);
        } catch (e) {
            showToast('对比加载失败: ' + e.message, 'error');
        }
    },

    renderComparison(data) {
        const el = document.getElementById('rpDetail');
        const reports = data.reports || [];
        const deltas = data.deltas || [];

        el.innerHTML = `
          <h3 style="color:var(--accent-blue);margin-bottom:12px">⚖️ 报告对比 (${reports.length}个)</h3>

          <div class="card" style="min-height:260px;margin-bottom:12px">
            <h4 style="color:var(--text-secondary);font-size:13px;margin-bottom:8px">📊 维度对比</h4>
            <canvas id="reportCompareChart" height="220"></canvas>
          </div>

          <div class="card" style="margin-bottom:12px">
            <h4 style="color:var(--text-secondary);font-size:13px;margin-bottom:8px">📋 得分对比</h4>
            <table class="data-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>综合</th>
                  <th>正确性</th>
                  <th>相关性</th>
                  <th>完整性</th>
                  <th>引导力</th>
                  <th>追问</th>
                  <th>边界</th>
                  <th>一致</th>
                  <th>递进</th>
                  <th>过帮</th>
                  <th>公平</th>
                </tr>
              </thead>
              <tbody>
                ${reports.map(r => `
                  <tr>
                    <td style="font-size:11px">${formatDate(r.timestamp)}</td>
                    <td class="${scoreColor(r.overall)}" style="font-weight:bold">${r.overall.toFixed(1)}</td>
                    ${['correctness','relevancy','completeness','guidance','followup_quality','boundary_compliance','turn_consistency','knowledge_scaffolding','overhelping','fairness_bias']
                      .map(k => `<td class="${scoreColor(r.scores?.[k] || 0)}">${(r.scores?.[k] || 0).toFixed(1)}</td>`).join('')}
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>

          ${deltas.length ? `
          <div class="card">
            <h4 style="color:var(--text-secondary);font-size:13px;margin-bottom:8px">📐 最大差异</h4>
            ${deltas.map(d => `
              <div style="display:flex;justify-content:space-between;padding:4px 0;font-size:12px;border-bottom:1px solid var(--bg-tertiary)">
                <span>${d.dimension}</span>
                <span>Δ ${d.max_delta.toFixed(2)} <span style="color:var(--text-muted);font-size:11px">[${d.values.map(v=>v.toFixed(1)).join(', ')}]</span></span>
              </div>
            `).join('')}
          </div>` : ''}
        `;

        setTimeout(() => drawComparisonChart('reportCompareChart', reports), 100);
    },

    // ── 导出 ──
    async exportReport(id, format) {
        try {
            const url = `/api/reports/${id}/export?format=${format}`;
            const a = document.createElement('a');
            a.href = url;
            a.download = `report_${id}.${format}`;
            a.click();
            showToast(`已导出 ${format.toUpperCase()}`, 'success');
        } catch (e) {
            showToast('导出失败', 'error');
        }
    },

    // ── 删除 ──
    async deleteReport(id) {
        if (!confirm('确定删除此报告？')) return;
        try {
            await api.delete(`/api/reports/${id}`);
            showToast('已删除', 'success');
            this.state.selectedId = null;
            document.getElementById('rpDetail').innerHTML = '<div class="qa-empty">← 选择一个报告查看详情</div>';
            this.loadList();
        } catch (e) {
            showToast('删除失败', 'error');
        }
    },
};

export default ReportsPage;
