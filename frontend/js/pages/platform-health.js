/* ════════════════════════════════════════════
   Platform Health + Real-time Eval Monitor v3.0
   全数据驱动, 零硬编码
   ════════════════════════════════════════════ */

import api from '../api.js';
import ws from '../ws.js';
import { t, onLangChange } from '../i18n-bridge.js';

const P = {
    state: { inited: false, running: false, pollTimer: null, totalScenarios: 0 },

    init() {
        if (this.state.inited) return;
        ws.on('eval_event', (m) => this._onWsEval(m));
        ws.on('connected', () => this._wsStatus(true));
        ws.on('disconnected', () => this._wsStatus(false));
        onLangChange(() => {
            if (document.getElementById('page-platform-health') &&
                document.getElementById('page-platform-health').classList.contains('active')) {
                this.render();
            }
        });
        this.state.inited = true;
    },

    async render() {
        var el = document.getElementById('page-platform-health');
        if (!el) return;
        el.innerHTML = this._layout();
        this._loadHealth();
        this._poll();
        this.state.pollTimer = setInterval(() => this._poll(), 5000);
    },

    // ── HTML 布局 ──
    _layout() {
        return (
        '<div class="page-header">' +
          '<h2>' + t('health_title') + '</h2>' +
          '<p class="page-desc" id="ph-eval-status">' + t('health_desc') + '</p>' +
        '</div>' +
        // 评测状态卡片
        '<div class="stat-grid" style="margin-bottom:16px">' +
          '<div class="card"><h3>' + t('health_ws_card') + '</h3><div class="val" id="ph-ws" style="font-size:14px;color:#dc2626">' + t('health_ws_disconnected') + '</div></div>' +
          '<div class="card"><h3>' + t('health_eval_status') + '</h3><div class="val" id="ph-state" style="font-size:14px">' + t('health_eval_idle') + '</div></div>' +
          '<div class="card"><h3>' + t('health_scenarios_done') + '</h3><div class="val" id="ph-scenarios">-</div></div>' +
          '<div class="card"><h3>' + t('health_elapsed') + '</h3><div class="val" id="ph-time">-</div></div>' +
        '</div>' +
        '<div class="progress-bar" style="margin-bottom:16px"><div class="progress-fill" id="ph-bar" style="width:0%"></div></div>' +
        // 平台健康度卡片
        '<div class="card" style="margin-bottom:16px">' +
          '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">' +
            '<h3 style="font-size:14px;color:var(--sky)">🔌 ' + t('health_title').replace('📡 ', '被测平台') + '</h3>' +
            '<div style="display:flex;gap:8px;align-items:center">' +
              '<span id="phHealthAge" style="font-size:11px;color:var(--dim)"></span>' +
              '<button class="btn btn-outline btn-sm" id="phRefreshBtn">' + t('health_refresh_btn') + '</button>' +
            '</div>' +
          '</div>' +
          '<div id="phHealthSummary" style="margin-bottom:12px;font-size:13px">' + t('sys_loading') + '</div>' +
          '<div id="phP0Warning" style="display:none;margin-bottom:12px"></div>' +
          '<table id="phFeatureTable" style="display:none">' +
            '<thead><tr><th>' + t('health_feature_name') + '</th><th>' + t('health_feature_api') + '</th><th>' + t('health_feature_status') + '</th><th>' + t('health_feature_latency') + '</th><th>' + t('health_feature_detail') + '</th></tr></thead>' +
            '<tbody id="phFeatureBody"></tbody>' +
          '</table>' +
        '</div>' +
        // 指标趋势图
        '<div class="card" style="margin-bottom:16px">' +
          '<h3 style="font-size:14px;color:var(--sky);margin-bottom:8px">📈 技术指标趋势 (24h)</h3>' +
          '<canvas id="phTrendChart" style="width:100%;height:200px"></canvas>' +
        '</div>' +
        // 事件日志
        '<div class="card">' +
          '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">' +
            '<h3 style="font-size:14px;color:var(--muted)">' + t('health_log_title') + '</h3>' +
            '<button class="btn btn-outline btn-sm" id="phClearLogBtn">' + t('btn_clear') + '</button>' +
          '</div>' +
          '<div id="ph-log" style="max-height:350px;overflow-y:auto;font-size:11px;font-family:monospace;background:var(--surface-2);border-radius:8px;padding:10px;line-height:1.6">' +
            '<div style="color:var(--dim)">' + t('health_log_loaded') + '</div>' +
          '</div>' +
        '</div>');
    },

    // ── 健康度加载 & 渲染 ──
    async _loadHealth() {
        // 绑定刷新按钮
        var btn = document.getElementById('phRefreshBtn');
        if (btn) {
            btn.addEventListener('click', () => this._refreshFull());
        }
        // 绑定清空按钮
        var clearBtn = document.getElementById('phClearLogBtn');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                var logEl = document.getElementById('ph-log');
                if (logEl) logEl.innerHTML = '<div style="color:var(--dim)">日志已清空</div>';
            });
        }
        // 加载数据
        await this._loadFromApi();
    },

    async _loadFromApi() {
        try {
            var d = await api.get('/api/dashboard/interaction', {quick: 'true'});
            this._renderHealth(d);
        } catch (e) {
            var el = document.getElementById('phHealthSummary');
            if (el) el.innerHTML = '<span style="color:var(--red)">平台交互数据加载失败</span>';
        }
        this._loadTrend();
    },

    async _loadTrend() {
        try {
            var d = await api.get('/api/dashboard/metrics-trend', {hours: 24});
            this._renderTrend(d.trend || []);
        } catch (e) {
            // 静默失败 - trend是辅助功能
        }
    },

    _renderTrend(points) {
        var canvas = document.getElementById('phTrendChart');
        if (!canvas) return;
        var ctx = canvas.getContext('2d');
        if (this._trendChart) this._trendChart.destroy();

        if (!points || points.length < 2) {
            ctx.font = '13px sans-serif';
            ctx.fillStyle = 'var(--dim)';
            ctx.textAlign = 'center';
            ctx.fillText('趋势数据不足 (需要至少2个采样点)', canvas.width / 2, 100);
            return;
        }

        var labels = points.map(function (p) {
            var d = new Date(p.ts * 1000);
            return d.getHours() + ':' + String(d.getMinutes()).padStart(2, '0');
        });
        var health = points.map(function (p) { return Math.round(p.health_score * 100); });
        var errors = points.map(function (p) { return p.error_count || 0; });

        this._trendChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: '健康度 %',
                        data: health,
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59,130,246,0.1)',
                        fill: true,
                        tension: 0.3,
                        yAxisID: 'y',
                    },
                    {
                        label: '异常功能数',
                        data: errors,
                        borderColor: '#ef4444',
                        borderDash: [4, 4],
                        pointRadius: 3,
                        tension: 0.3,
                        yAxisID: 'y1',
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { intersect: false, mode: 'index' },
                scales: {
                    y: {
                        type: 'linear',
                        position: 'left',
                        min: 0, max: 100,
                        ticks: { callback: function (v) { return v + '%'; } }
                    },
                    y1: {
                        type: 'linear',
                        position: 'right',
                        min: 0,
                        grid: { drawOnChartArea: false }
                    }
                },
                plugins: {
                    legend: { labels: { boxWidth: 12, font: { size: 10 } } }
                }
            }
        });
    },

    _formatAge(sec) {
        if (sec == null) return '';
        if (sec < 60) return t('health_data_age_seconds').replace('{0}', sec);
        if (sec < 3600) return t('health_data_age_minutes').replace('{0}', Math.round(sec / 60));
        return t('health_data_age_hours').replace('{0}', Math.round(sec / 3600));
    },

    _statusBadge(s) {
        if (s === 'working') return '<span class="badge badge-green">' + t('health_working') + '</span>';
        if (s === 'degraded') return '<span class="badge badge-yellow">' + t('health_degraded') + '</span>';
        if (s === 'broken') return '<span class="badge badge-red">' + t('health_broken') + '</span>';
        return '<span class="badge">' + (s || '?') + '</span>';
    },

    _renderHealth(d) {
        var summaryEl = document.getElementById('phHealthSummary');
        var warningEl = document.getElementById('phP0Warning');
        var tableEl = document.getElementById('phFeatureTable');
        var tbody = document.getElementById('phFeatureBody');
        var ageEl = document.getElementById('phHealthAge');

        if (!d || !d.summary) {
            if (summaryEl) summaryEl.innerHTML = '<span style="color:var(--red)">无法获取平台健康度数据 — 请检查被测平台是否在线</span>';
            return;
        }

        var s = d.summary;
        var pct = Math.round((s.health_score || 0) * 100);
        var color = pct >= 80 ? 'var(--green)' : pct >= 50 ? 'var(--yellow)' : 'var(--red)';

        // 摘要行
        if (summaryEl) {
            summaryEl.innerHTML =
                t('health_summary') + ': <b style="font-size:18px;color:' + color + '">' + pct + '%</b> &nbsp;|&nbsp; ' +
                '✅ <b>' + (s.working || 0) + '</b> ' + t('health_working') + ' &nbsp;|&nbsp; ' +
                '⚠️ <b>' + (s.degraded || 0) + '</b> ' + t('health_degraded') + ' &nbsp;|&nbsp; ' +
                '❌ <b>' + (s.broken || 0) + '</b> ' + t('health_broken') + ' &nbsp;|&nbsp; ' +
                t('health_total') + ' <b>' + (s.total || 0) + '</b> ' + t('health_items');
        }

        // 缓存年龄
        if (ageEl) {
            if (d.cached) {
                ageEl.textContent = '数据: ' + this._formatAge(d.cache_age_seconds);
                ageEl.style.color = d.stale ? 'var(--yellow)' : 'var(--dim)';
            } else if (d.probe_mode) {
                ageEl.textContent = '实时探活 (' + this._formatAge(d.cache_age_seconds || 0) + ')';
                ageEl.style.color = 'var(--dim)';
            }
        }

        // P0 阻断告警
        if (warningEl) {
            var blocked = s.p0_blocked_features || [];
            if (blocked.length > 0) {
                warningEl.style.display = 'block';
                warningEl.innerHTML =
                    '<div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;padding:10px 14px;font-size:12px;color:#92400e">' +
                    '🚨 <b>P0 阻断:</b> 以下核心功能不可用 — ' +
                    blocked.map(function (f) { return '<code>' + f + '</code>'; }).join(', ') +
                    ' &nbsp; <small>(' + (s.p0_blocked || 0) + '/' + (s.total || 0) + ' P0 功能受阻)</small>' +
                    '</div>';
            } else {
                warningEl.style.display = 'none';
            }
        }

        // 功能表格
        var features = d.features || {};
        var keys = Object.keys(features);
        if (keys.length > 0 && tbody) {
            tableEl.style.display = '';
            keys.sort(function (a, b) {
                var order = { broken: 0, degraded: 1, working: 2 };
                return (order[features[a].status] || 3) - (order[features[b].status] || 3);
            });
            tbody.innerHTML = keys.map(function (k) {
                var f = features[k];
                var lat = f.latency_ms != null
                    ? (f.latency_ms > 1000 ? (f.latency_ms / 1000).toFixed(1) + 's' : Math.round(f.latency_ms) + 'ms')
                    : '-';
                var detail = (f.detail || '').substring(0, 100);
                return '<tr>' +
                    '<td><b>' + (f.name || k) + '</b> <small style="color:var(--dim)">' + (f.priority || '') + '</small></td>' +
                    '<td style="font-family:monospace;font-size:11px">' + (f.api || '') + '</td>' +
                    '<td>' + P._statusBadge(f.status) + '</td>' +
                    '<td style="font-size:11px">' + lat + '</td>' +
                    '<td style="font-size:11px;color:var(--muted)">' + detail + '</td>' +
                    '</tr>';
            }).join('');
        }
    },

    // ── 手动全量刷新 ──
    _refreshing: false,
    async _refreshFull() {
        if (this._refreshing) return;
        this._refreshing = true;
        var btn = document.getElementById('phRefreshBtn');
        if (btn) { btn.disabled = true; btn.textContent = '⏳ 检测中 (2-3分钟)...'; }
        var summaryEl = document.getElementById('phHealthSummary');
        if (summaryEl) summaryEl.innerHTML = '⏳ 正在运行全量平台健康检测 (2-3分钟)...';

        try {
            var d = await api.post('/api/dashboard/interaction/refresh');
            this._renderHealth(d);
        } catch (e) {
            if (summaryEl) summaryEl.innerHTML = '<span style="color:var(--red)">检测失败: ' + (e.message || '网络错误') + '</span>';
        } finally {
            this._refreshing = false;
            if (btn) { btn.disabled = false; btn.textContent = '🔄 刷新检测'; }
        }
    },

    // ── 评测状态轮询 ──
    async _poll() {
        try {
            var s = await api.get('/api/tests/status');
            var h = await api.get('/api/tests/health');
            var stEl = document.getElementById('ph-state');
            var scEl = document.getElementById('ph-scenarios');
            var tmEl = document.getElementById('ph-time');
            var bar = document.getElementById('ph-bar');
            if (s.running || h.running) {
                if (stEl) stEl.innerHTML = '<b style="color:var(--green)">▶ 运行中</b>';
                if (scEl) scEl.textContent = (h.scenarios_completed || 0) + '/' + (h.scenarios_total || 0);
                if (tmEl) tmEl.textContent = Math.round((h.elapsed_seconds || 0) / 60) + '分';
                if (bar && h.scenarios_total) bar.style.width = ((h.scenarios_completed || 0) / h.scenarios_total * 100) + '%';
            } else {
                if (stEl) stEl.textContent = '空闲';
                if (scEl) scEl.textContent = '-';
                if (tmEl) tmEl.textContent = '-';
                if (bar) bar.style.width = '0%';
            }
        } catch (e) { /* ignore poll errors */ }
    },

    // ── WebSocket 事件 ──
    _wsStatus(ok) {
        var el = document.getElementById('ph-ws');
        if (el) { el.innerHTML = ok ? '🟢 已连接' : '🔌 断开'; el.style.color = ok ? 'var(--green)' : 'var(--red)'; }
    },

    _log(msg, color) {
        var el = document.getElementById('ph-log');
        if (!el) return;
        var t = new Date().toLocaleTimeString('zh-CN', { hour12: false });
        var d = document.createElement('div');
        d.style.cssText = 'padding:1px 0;color:' + (color || 'var(--text)');
        d.textContent = t + ' ' + msg;
        el.appendChild(d);
        el.scrollTop = el.scrollHeight;
    },

    _onWsEval(msg) {
        var e = msg.event, d = msg.data;
        var st = document.getElementById('ph-eval-status');
        var bar = document.getElementById('ph-bar');

        if (e === 'test_start') {
            this.state.running = true;
            this.state.totalScenarios = d.total || 0;
            if (st) st.innerHTML = '🚀 <b>测评启动</b> — ' + (d.agent || '?') + ' | ' + (d.total || 0) + ' 场景';
            this._log('🚀 启动 | Agent=' + (d.agent || '?') + ' | ' + (d.total || 0) + '场景', 'var(--sky)');
        }
        if (e === 'scenario_start') {
            if (st) st.innerHTML = '📋 <b>场景 ' + d.index + '/' + this.state.totalScenarios + '</b>';
            if (bar && this.state.totalScenarios) bar.style.width = ((d.index - 1) / this.state.totalScenarios * 100) + '%';
            this._log('📋 场景 ' + d.index + '/' + this.state.totalScenarios, 'var(--sky)');
        }
        if (e === 'send') {
            this._log('📤 T' + d.turn + ': ' + (d.question || '').substring(0, 80), 'var(--muted)');
        }
        if (e === 'response') {
            this._log('📥 T' + d.turn + ' [' + (d.status || '?') + '] ' + ((d.duration || 0).toFixed(1)) + 's', 'var(--green)');
        }
        if (e === 'score_done') {
            this._log('✅ 评分 overall=' + (d.overall || 0) + ' | boundary=' + (d.boundary_compliance || 0), 'var(--sky)');
        }
        if (e === 'scenario_done') {
            if (bar && this.state.totalScenarios) bar.style.width = (d.index / this.state.totalScenarios * 100) + '%';
            this._log('✅ 场景' + d.index + '完成 | overall=' + ((d.overall || 0).toFixed(1)), 'var(--sky)');
            this._poll();
        }
        if (e === 'done') {
            this.state.running = false;
            if (bar) bar.style.width = '100%';
            if (st) st.innerHTML = '🎉 <b>全部完成!</b>';
            this._log('🎉 全部完成!', 'var(--green)');
            this._poll();
        }
        if (e === 'error') {
            this._log('❌ ' + (d.message || 'error'), 'var(--red)');
        }
    },
};

export default P;
