/* ════════════════════════════════════════════
   Reports Page — 报告列表/详情/对比/导出
   ════════════════════════════════════════════ */

import api from '../api.js';
import { drawRadarChart, drawComparisonChart, destroyChart } from '../charts.js';
import { showToast, scoreColor, scoreText, formatDate, ringColor } from '../utils.js';
import { t, onLangChange } from '../i18n-bridge.js';

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
        // Re-render on language switch (if this page is active)
        onLangChange(() => {
            if (document.getElementById('page-reports') &&
                document.getElementById('page-reports').classList.contains('active')) {
                this.render();
            }
        });
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
            <h2>${t('reports_title')}</h2>
            <div style="display:flex;gap:8px">
              <button class="btn btn-outline btn-sm" id="rpCompareToggle">
                ${this.state.compareMode ? t('reports_exit_compare') : t('reports_compare_mode')}
              </button>
              <button class="btn btn-outline btn-sm" id="rpRefreshBtn">${t('btn_refresh')}</button>
            </div>
          </div>
          <div class="report-layout">
            <div class="report-list" id="rpList"><div class="qa-empty">${t('loading')}</div></div>
            <div class="report-detail" id="rpDetail"><div class="qa-empty">${t('reports_select_hint')}</div></div>
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
            el.innerHTML = `<div class="qa-empty">${t('load_failed').replace('{0}', e.message)}</div>`;
        }
    },

    renderList(data) {
        const el = document.getElementById('rpList');
        if (!data.items?.length) {
            el.innerHTML = `<div class="qa-empty">${t('reports_no_data')}</div>`;
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
                      ${r.agent_id || 'N/A'} · ${t('scenarios_count').replace('{0}', r.total || 0)}
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
              <span class="page-info">${t('page_of').replace('{0}', data.total).replace('{1}', data.page).replace('{2}', data.total_pages)}</span>
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
        if (el) el.innerHTML = `<div class="rpt-loading"><div class="rpt-spinner"></div><span style="color:var(--text-secondary)">${t('loading')}</span></div>`;

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
            if (el) el.innerHTML = `<div class="qa-empty">${t('load_failed').replace('{0}', e.message)}</div>`;
            showToast(t('rp_load_failed'), 'error');
        }
    },

    // v3.6: 直接渲染MySQL中的HTML内容
    renderHtmlContent(detail) {
        const el = document.getElementById('rpDetail');
        el.innerHTML = `
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
            <div>
              <h3 style="color:var(--accent-blue);margin-bottom:4px">📋 ${t('reports_title')}</h3>
              <div style="font-size:12px;color:var(--text-muted)">${detail.timestamp || ''} · ${t('rp_report_id_label')} ${(detail.id||'').substring(0,8)}...</div>
            </div>
            <div style="display:flex;gap:8px">
              <button class="btn btn-outline btn-sm" onclick="window.print()">${t('rp_btn_print')}</button>
              <button class="btn btn-outline btn-sm" id="rpDeleteBtn">${t('rp_btn_delete')}</button>
            </div>
          </div>
          <div class="card" style="padding:20px 24px">
            <div class="report-html-content">${detail.html_content}</div>
          </div>
          <div style="display:flex;gap:8px;margin-top:12px">
            <a class="btn btn-outline btn-sm" href="/test/api/reports/${detail.id}/export?format=json" download>${t('rp_btn_export_json')}</a>
            <a class="btn btn-outline btn-sm" href="/test/api/reports/${detail.id}/export?format=csv" download>${t('rp_btn_export_csv')}</a>
          </div>
        `;

        document.getElementById('rpDeleteBtn')?.addEventListener('click', () => this.deleteReport(detail.id));
    },

    renderDetail(detail, fullData) {
        const el = document.getElementById('rpDetail');
        if (!detail || !detail.summary_json) {
            el.innerHTML = `<div class="qa-empty">${t('reports_detail_empty')}</div>`;
            return;
        }

        const summary = detail.summary_json;
        const avg = summary.avg_scores || {};
        const boundary = summary.boundary || {};
        const extra = (fullData && fullData.extra) || summary.extra || {};
        const evidence = (fullData && fullData.evidence) || extra.evidence || {};
        const dims = [
            { key: 'correctness', icon: '📐' },
            { key: 'relevancy', icon: '🎯' },
            { key: 'completeness', icon: '📋' },
            { key: 'guidance', icon: '🧭' },
            { key: 'followup_quality', icon: '🔄' },
            { key: 'boundary_compliance', icon: '🛡️' },
            { key: 'turn_consistency', icon: '🔗' },
            { key: 'knowledge_scaffolding', icon: '📈' },
            { key: 'overhelping', icon: '⚠️' },
            { key: 'fairness_bias', icon: '⚖️' },
        ].map(d => ({ ...d, label: t('dim_short_' + d.key) }));

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
              <h4 style="color:var(--text-secondary);margin-bottom:8px">${t('rp_section_confidence')}</h4>
              <div style="font-size:10px;color:var(--text-muted);margin-bottom:6px">${t('rp_cv_legend')}</div>
              ${conf.overall_reliability ? `<div style="font-weight:700;margin-bottom:6px">${t('rp_conf_overall').replace('{0}', conf.overall_reliability)}</div>` : ''}
              <table class="conf-table"><thead><tr><th>${t('rp_conf_th_dim')}</th><th>${t('rp_conf_th_mean')}</th><th>${t('rp_conf_th_cv')}</th><th>${t('rp_conf_th_ci')}</th><th>${t('rp_conf_th_reliability')}</th></tr></thead><tbody>
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
              <h4 style="color:var(--text-secondary);margin-bottom:8px">${t('rp_section_evidence')}</h4>
              ${selfHash ? `<div class="evidence-box"><span style="font-size:18px">🔒</span> <strong>${t('rp_self_hash')}</strong><br><span class="hash-badge" title="${selfHash}">${selfHash.substring(0,8)}...${selfHash.substring(selfHash.length-8)}</span> <button onclick="navigator.clipboard.writeText('${selfHash}')" style="font-size:10px;padding:2px 6px;border:1px solid var(--bg-tertiary);border-radius:4px;background:var(--surface-2);color:var(--text-muted);cursor:pointer" title="${t('rp_copy_hash_title')}">${t('rp_btn_copy_hash')}</button><br><span style="font-size:10px;color:var(--text-muted)">${t('rp_sha256_hint')}</span></div>` : ''}
              ${configFp ? `<div style="font-size:10px;color:var(--text-muted);margin:4px 0">${t('rp_config_fp_label')} <code>${configFp}</code></div>` : ''}
              ${chain.length ? `<div style="margin-top:6px"><strong>${t('rp_hash_chain_title')}</strong><div class="hash-chain">${chain.map((n,i) => `<div class="hash-node"><div class="hx">${n.hash}</div><div class="hl">${t('rp_hash_node').replace('{0}', n.index).replace('{1}', (n.overall||0).toFixed(1))}</div></div>${i<chain.length-1?'<div class="hash-link">→</div>':''}`).join('')}</div></div>` : ''}
            </div>`;
        }

        // ── Judge 共识 ──
        let judgeBox = '';
        if (jc.consensus_level) {
            judgeBox = `<div class="card" style="margin-bottom:12px;font-size:11px">
              <h4 style="color:var(--text-secondary);margin-bottom:6px">${t('rp_section_judge')}</h4>
              <div>${jc.consensus_level}</div>
              <div style="font-size:10px;color:var(--text-muted)">${t('rp_judge_stats').replace('{0}', jc.avg_judges_per_scenario).replace('{1}', (jc.avg_variance||0).toFixed(3)).replace('{2}', jc.veto_scenarios||0)}</div>
            </div>`;
        }

        el.innerHTML = `
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px">
            <div>
              <h3 style="color:var(--accent-blue);margin-bottom:4px">📋 ${t('reports_title')}</h3>
              <div style="font-size:12px;color:var(--text-muted)">${detail.timestamp || ''}</div>
              <div style="font-size:12px;color:var(--text-muted)">${t('agent_scenarios').replace('{0}', summary.agent_id || 'N/A').replace('{1}', summary.total || 0)}</div>
            </div>
            <div class="score-ring ${ringCls}" style="width:80px;height:80px">
              <div class="ring-value">${(avg.overall || 0).toFixed(1)}</div>
              <div class="ring-label">${t('chart_overall_label')}</div>
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
            <h4 style="color:var(--text-secondary);margin-bottom:6px">${t('rp_section_boundary')}</h4>
            <div style="display:flex;gap:16px">
              <span>${t('rp_in_scope').replace('{0}', boundary.in_scope || 0)}</span>
              <span>${t('rp_partial_match').replace('{0}', boundary.partial_match || 0)}</span>
              <span>${t('rp_out_of_scope').replace('{0}', boundary.out_of_scope || 0)}</span>
            </div>
          </div>` : ''}

          <div class="card" style="min-height:240px;margin-bottom:12px">
            <h4 style="color:var(--text-secondary);font-size:13px;margin-bottom:8px">${t('rp_section_radar')}</h4>
            <canvas id="reportRadarChart" height="200"></canvas>
          </div>

          <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap;align-items:center">
            ${detail.json_path ? `<a class="btn btn-sm" style="background:linear-gradient(135deg,var(--accent-blue),#2563eb);color:#fff;font-weight:600;padding:8px 18px;border-radius:8px;text-decoration:none;box-shadow:0 2px 8px rgba(37,99,235,.3)" href="/test/reports/${detail.json_path.replace(/\\\\/g,'/').split('/').pop().replace('.json','')}.html" target="_blank">${t('rp_btn_full_html')}</a>` : (fullData && fullData.timestamp ? `<a class="btn btn-sm" style="background:linear-gradient(135deg,var(--accent-blue),#2563eb);color:#fff;font-weight:600;padding:8px 18px;border-radius:8px;text-decoration:none;box-shadow:0 2px 8px rgba(37,99,235,.3)" href="/test/reports/report_${fullData.timestamp}.html" target="_blank">${t('rp_btn_full_html')}</a>` : '')}
            <a class="btn btn-outline btn-sm" href="/test/api/reports/${detail.id}/export?format=json" download>${t('rp_btn_export_json')}</a>
            <a class="btn btn-outline btn-sm" href="/test/api/reports/${detail.id}/export?format=csv" download>${t('rp_btn_export_csv')}</a>
            <button class="btn btn-danger btn-sm" id="rpDeleteBtn">${t('rp_btn_delete')}</button>
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
            '<div class="qa-empty">' + (this.state.compareMode ? t('reports_compare_hint') : t('reports_select_hint')) + '</div>';
        this.loadList();
        const btn = document.getElementById('rpCompareToggle');
        if (btn) btn.textContent = this.state.compareMode ? t('reports_exit_compare') : t('reports_compare_mode');
    },

    toggleCompareId(id) {
        const idx = this.state.compareIds.indexOf(id);
        if (idx >= 0) {
            this.state.compareIds.splice(idx, 1);
        } else {
            if (this.state.compareIds.length >= 5) {
                showToast(t('reports_max_compare'), 'info');
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
            showToast(t('rp_compare_load_failed').replace('{0}', e.message), 'error');
        }
    },

    renderComparison(data) {
        const el = document.getElementById('rpDetail');
        const reports = data.reports || [];
        const deltas = data.deltas || [];

        el.innerHTML = `
          <h3 style="color:var(--accent-blue);margin-bottom:12px">${t('rp_compare_title').replace('{0}', reports.length)}</h3>

          <div class="card" style="min-height:260px;margin-bottom:12px">
            <h4 style="color:var(--text-secondary);font-size:13px;margin-bottom:8px">${t('rp_section_comparison')}</h4>
            <canvas id="reportCompareChart" height="220"></canvas>
          </div>

          <div class="card" style="margin-bottom:12px">
            <h4 style="color:var(--text-secondary);font-size:13px;margin-bottom:8px">${t('rp_section_score_compare')}</h4>
            <table class="data-table">
              <thead>
                <tr>
                  <th>${t('rp_compare_th_time')}</th>
                  <th>${t('rp_compare_th_overall')}</th>
                  <th>${t('dim_short_correctness')}</th>
                  <th>${t('dim_short_relevancy')}</th>
                  <th>${t('dim_short_completeness')}</th>
                  <th>${t('dim_short_guidance')}</th>
                  <th>${t('dim_short_followup_quality')}</th>
                  <th>${t('dim_short_boundary_compliance')}</th>
                  <th>${t('dim_short_turn_consistency')}</th>
                  <th>${t('dim_short_knowledge_scaffolding')}</th>
                  <th>${t('dim_short_overhelping')}</th>
                  <th>${t('dim_short_fairness_bias')}</th>
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
            <h4 style="color:var(--text-secondary);font-size:13px;margin-bottom:8px">${t('rp_section_max_delta')}</h4>
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
            showToast(`${t('rp_exported')} ${format.toUpperCase()}`, 'success');
        } catch (e) {
            showToast(t('rp_export_failed'), 'error');
        }
    },

    // ── 删除 ──
    async deleteReport(id) {
        if (!confirm(t('rp_confirm_delete'))) return;
        try {
            await api.delete(`/api/reports/${id}`);
            showToast(t('rp_deleted'), 'success');
            this.state.selectedId = null;
            document.getElementById('rpDetail').innerHTML = `<div class="qa-empty">${t('reports_select_hint')}</div>`;
            this.loadList();
        } catch (e) {
            showToast(t('rp_delete_failed'), 'error');
        }
    },
};

export default ReportsPage;
