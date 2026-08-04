/* Dashboard Page */
import api from '../api.js';
import ws from '../ws.js';
import { showToast } from '../utils.js';
import { t, onLangChange } from '../i18n-bridge.js';

export default {
    state: {
        initialized: false,
        timer: null, startTs: 0, errorCount: 0,
        evalState: { scenarioIndex: 0, totalScenarios: 0, turnIndex: 0, maxTurns: 0 },
    },

    init() {
        if (this.state.initialized) return;
        ws.on('connected', () => this._updateWSStatus(true));
        ws.on('disconnected', () => this._updateWSStatus(false));
        // Re-render on language switch (if this page is active)
        onLangChange(() => {
            if (document.getElementById('page-dashboard') &&
                document.getElementById('page-dashboard').classList.contains('active')) {
                this.render();
            }
        });
        this.state.initialized = true;
    },

    async render() {
        const el = document.getElementById('page-dashboard');
        if (!el) return;

        // 先渲染骨架
        el.innerHTML = `
          <div class="stat-grid">
            <div class="card"><div class="card-header">${t('card_total_tests')}</div><div class="card-value" id="totalTests">-</div></div>
            <div class="card"><div class="card-header">${t('card_avg_score')}</div><div class="card-value" id="avgScore">-</div></div>
            <div class="card"><div class="card-header">${t('card_qa_approved')}</div><div class="card-value" id="qaApproved">-</div></div>
            <div class="card"><div class="card-header">${t('card_sys_status')}</div><div class="card-value" id="sysStatus" style="font-size:16px">${t('sys_online')}</div></div>
          </div>

          <div class="controls" style="display:flex;flex-wrap:wrap;gap:10px;align-items:center">
            <select id="agentSelect"></select>
            <select id="evalProfile" style="width:auto">
              <option value="patrol">🔍 巡检 (~5min) — 每Phase抽1Day+Agent+Quiz</option>
              <option value="full" selected>📋 全平台 (~18min) — 22Days全遍历+Agent+Quiz验证</option>
              <option value="deep">🔬 深度 (~30min) — 全遍历+双模式(帮帮我+我自己来)+逐Step验证</option>
              <option value="custom">⚙️ 自定义参数</option>
            </select>
            <span id="customOpts" style="display:none;gap:6px;align-items:center">
              <input id="numQuestions" type="number" value="3" min="1" max="20" style="width:55px" title="LLM问答题目数">
              <span style="font-size:12px;color:var(--muted)">题 ×</span>
              <input id="maxTurns" type="number" value="3" min="1" max="10" style="width:55px" title="每轮追问数">
              <span style="font-size:12px;color:var(--muted)">轮 (LLM模式)</span>
            </span>
            <button class="btn btn-primary" id="startTestBtn">${t('btn_start_eval')}</button>
            <button class="btn btn-outline" id="refreshBtn">${t('btn_refresh')}</button>
          </div>
          <div style="font-size:11px;color:var(--dim);margin-top:4px" id="evalModeHint">
            全平台模式: Playwright浏览器真实遍历 22个Day + Phase 5 Agent + Quiz自动验证
          </div>

          <div id="evalStatusBar" style="display:none;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin-bottom:12px;font-size:12px">
            <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:center">
              <span id="wsIndicator" style="color:var(--red)">${t('sys_ws_disconnected')}</span>
              <span>${t('live_elapsed')} <b id="evalElapsed">00:00</b></span>
              <span>${t('live_step')} <span id="evalStep">${t('live_step_ready')}</span></span>
              <span style="color:var(--red)">${t('live_errors')} <b id="evalErrors">0</b> ${t('live_errors')}</span>
              <span>${t('live_progress')} <span id="evalProgress">0/0 · 0/0</span></span>
            </div>
          </div>

          <div class="progress-bar" style="margin-bottom:8px"><div class="progress-fill" id="progressFill" style="width:0%"></div></div>
          <div style="font-size:11px;color:#64748b;margin-bottom:12px" id="progressLabel">${t('home_ready')}</div>

          <div class="live-eval" id="liveEvalPanel" style="display:none">
            <div class="live-eval-header"><h3>${t('live_title')}</h3><button class="btn btn-outline btn-sm" id="clearLogBtn">${t('btn_clear')}</button></div>
            <div class="live-eval-body" id="liveEvalBody"><div class="qa-empty">${t('live_hint')}</div></div>
          </div>

          <div class="score-mini-grid" id="scoreMiniGrid"></div>

          <div class="card" style="margin-bottom:12px" id="platformHealthCard">
            <h3 style="color:#38bdf8;margin-bottom:8px">🔌 ${t('health_title').replace('📡 ', '')}</h3>
            <div style="display:flex;gap:12px;flex-wrap:wrap;font-size:12px" id="platformHealthStats">
              <span style="color:var(--muted)">${t('sys_loading')}</span>
            </div>
            <div style="margin-top:6px;font-size:11px;color:var(--dim)" id="platformHealthQuiz"></div>
          </div>

          <div class="two-col" style="margin-bottom:16px">
            <div class="card"><h3 style="font-size:13px;color:#94a3b8">${t('chart_trend')}</h3><canvas id="trendChart" height="160"></canvas></div>
            <div class="card"><h3 style="font-size:13px;color:#94a3b8">${t('chart_radar')}</h3><canvas id="radarChart" height="160"></canvas></div>
          </div>

          <div class="card"><h3 style="color:#38bdf8;margin-bottom:8px">${t('recent_reports')}</h3><div id="reportList">${t('sys_loading')}</div></div>
        `;

        // 动态加载 Agent 列表
        await this._loadAgentOptions();

        // 绑定事件
        document.getElementById('startTestBtn').addEventListener('click', () => this.startTest());
        document.getElementById('refreshBtn').addEventListener('click', () => this.loadData());
        document.getElementById('clearLogBtn').addEventListener('click', () => {
            document.getElementById('liveEvalBody').innerHTML = '<div class="qa-empty">' + t('log_cleared') + '</div>';
        });
        // Profile → 自定义参数联动
        const profileSel = document.getElementById('evalProfile');
        const customOpts = document.getElementById('customOpts');
        profileSel.addEventListener('change', () => {
            customOpts.style.display = profileSel.value === 'custom' ? 'flex' : 'none';
        });

        // WebSocket 事件
        ws.on('eval_event', (msg) => this.handleEvalEvent(msg));

        // 加载数据
        await this.loadData();
    },

    async loadData() {
        try {
            const data = await api.get('/api/dashboard/summary');
            document.getElementById('totalTests').textContent = data.total_tests || 0;
            document.getElementById('avgScore').textContent = (data.avg_overall || 0).toFixed(2);
            document.getElementById('qaApproved').textContent = data.qa_approved || 0;

            // 平台交互健康度 (来自最新报告)
            if (data.interaction) {
                this.renderPlatformHealth(data.interaction);
            } else {
                this.renderPlatformHealthDefault();
            }
        } catch (e) {
            document.getElementById('sysStatus').textContent = t('sys_offline');
            document.getElementById('sysStatus').style.color = '#dc2626';
            this.renderPlatformHealthDefault();
        }

        try {
            const reports = await api.get('/api/dashboard/sessions', { page_size: 5 });
            const el = document.getElementById('reportList');
            if (reports.items && reports.items.length > 0) {
                el.innerHTML = reports.items.map(r =>
                    `<span class="badge badge-info" style="margin:2px">${r.agent_id} · ${r.status}</span>`
                ).join(' ');
            } else {
                el.innerHTML = '<span class="text-muted">' + t('reports_no_data_hint') + '</span>';
            }
        } catch (e) {
            document.getElementById('reportList').textContent = t('sys_error');
        }
    },

    renderPlatformHealth(interaction) {
        const s = interaction.summary || {};
        const stats = document.getElementById('platformHealthStats');
        const quiz = document.getElementById('platformHealthQuiz');
        if (!stats) return;

        const pct = (s.health_score || 0) * 100;
        const color = pct >= 80 ? '#16a34a' : pct >= 50 ? '#d97706' : '#dc2626';
        stats.innerHTML = [
            `<span>${t('health_summary')}: <b style="color:${color}">${pct.toFixed(0)}%</b></span>`,
            `<span style="color:#16a34a">✅ ${s.working || 0} ${t('health_working')}</span>`,
            `<span style="color:#d97706">⚠️ ${s.degraded || 0} ${t('health_degraded')}</span>`,
            `<span style="color:#dc2626">❌ ${s.broken || 0} ${t('health_broken')}</span>`,
        ].join(' &nbsp;|&nbsp; ');

        // Quiz coverage
        const phaseQuiz = interaction.phase_quiz_summary || {};
        const quizOk = Object.values(phaseQuiz).filter(v => v.status === 'working').length;
        if (quiz) {
            quiz.innerHTML = '📝 Quiz: ' + quizOk + '/5 Phase &nbsp;|&nbsp; 45 ' + t('qa_question_label') + ' &nbsp;|&nbsp; API: /phase3-api/quiz/*';
        }
    },

    renderPlatformHealthDefault() {
        // 从真实API加载, 不做硬编码
        const stats = document.getElementById('platformHealthStats');
        const quiz = document.getElementById('platformHealthQuiz');
        if (stats) stats.innerHTML = '<span style="color:var(--muted)">' + t('health_loading') + '</span>';
        if (quiz) quiz.innerHTML = '';
        api.get('/api/dashboard/interaction?quick=true').then(d => {
            if (d && d.summary) this.renderPlatformHealth(d);
            else if (stats) stats.innerHTML = '<span style="color:var(--red)">' + t('health_no_data') + '</span>';
        }).catch(() => {
            if (stats) stats.innerHTML = '<span style="color:var(--red)">' + t('health_unavailable') + '</span>';
        });
    },

    // ═══ 辅助方法 ═══
    _updateWSStatus(connected) {
        const el = document.getElementById('wsIndicator');
        if (el) { el.innerHTML = connected ? t('sys_ws_connected') : t('sys_ws_disconnected'); el.style.color = connected ? 'var(--green)' : 'var(--red)'; }
    },
    _startTimer() {
        this.state.startTs = Date.now(); if (this.state.timer) clearInterval(this.state.timer);
        this.state.timer = setInterval(() => {
            const sec = Math.floor((Date.now() - this.state.startTs) / 1000);
            const m = Math.floor(sec / 60), s = sec % 60;
            const el = document.getElementById('evalElapsed'); if (el) el.textContent = String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0');
        }, 1000);
    },
    _stopTimer() { if (this.state.timer) { clearInterval(this.state.timer); this.state.timer = null; } },
    _updateStep(step) { const el = document.getElementById('evalStep'); if (el) el.textContent = step; },
    _updateProgress(scIdx, scTotal, turnIdx, turnTotal) {
        Object.assign(this.state.evalState, { scenarioIndex: scIdx, totalScenarios: scTotal, turnIndex: turnIdx, maxTurns: turnTotal });
        const el = document.getElementById('evalProgress'); if (el) el.textContent = t('eval_progress_fmt', scIdx, scTotal, turnIdx, turnTotal);
    },
    _incErrors() { this.state.errorCount++; const el = document.getElementById('evalErrors'); if (el) el.textContent = this.state.errorCount; },
    _addLog(msg, icon, cls) {
        const body = document.getElementById('liveEvalBody'); if (!body) return;
        const time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
        const div = document.createElement('div'); div.className = 'eval-step';
        div.innerHTML = `<div class="step-icon">${icon || '📌'}</div><div><div style="color:var(--muted);font-size:11px">${time}</div><div class="step-text ${cls || ''}">${msg}</div></div>`;
        body.appendChild(div); body.scrollTop = body.scrollHeight;
    },

    handleEvalEvent(msg) {
        const panel = document.getElementById('liveEvalPanel');
        const body = document.getElementById('liveEvalBody');
        const statusBar = document.getElementById('evalStatusBar');
        if (!panel || !body) return;
        panel.style.display = 'block';
        if (statusBar) statusBar.style.display = 'flex';

        const { event, data } = msg;
        const s = this;

        if (event === 'test_start') {
            s.state.errorCount = 0; s._startTimer(); s._updateStep(t('live_step_starting'));
            s._updateProgress(0, data.total || 0, 0, 0);
            body.innerHTML = '';
            s._addLog(t('eval_test_start', data.agent, data.total || 0), '🚀', '');
            document.getElementById('progressLabel').textContent = `Agent: ${data.agent} | ${data.total} ${t('scenario_label')}`;
            document.getElementById('progressFill').style.width = '0%';
            document.getElementById('startTestBtn').disabled = true;
            return;
        }
        if (event === 'scenario_start') {
            const div = document.createElement('div'); div.className = 'scenario-divider';
            div.textContent = t('scenario_divider', data.index, data.total); body.appendChild(div);
            s._updateProgress(data.index, data.total, 0, s.state.evalState.maxTurns);
            s._updateStep(t('live_step_scenario_start') + ' ' + data.index);
            document.getElementById('progressFill').style.width = `${(data.index-1)/data.total*100}%`;
            return;
        }
        if (event === 'agent_start') { s._addLog(t('eval_agent_connecting', data.agent || ''), '🔗', ''); s._updateStep(t('live_step_agent_connecting')); return; }
        if (event === 'agent_ready') { s._addLog(t('eval_agent_ready', data.agent || ''), '✅', 'step-ai'); s._updateStep(t('live_step_agent_ready')); return; }
        if (event === 'prologue') { s._addLog(t('eval_prologue', (data.text || '').substring(0, 200)), '💬', ''); return; }
        if (event === 'send') {
            s._addLog(t('eval_send', data.turn, (data.question || '').substring(0, 150)), '📤', '');
            s._updateProgress(s.state.evalState.scenarioIndex, s.state.evalState.totalScenarios, data.turn, data.max_turns || s.state.evalState.maxTurns);
            s._updateStep(t('live_step_sending') + ' (' + t('turn_label').replace('{0}', data.turn) + ')'); return;
        }
        if (event === 'response') {
            s._addLog(t('eval_response', data.turn, data.status, data.duration, (data.text || '').substring(0, 500)), '📥', 'step-ai');
            s._updateStep(t('live_step_receiving') + ' (' + t('turn_label').replace('{0}', data.turn) + ')'); return;
        }
        if (event === 'generating_followup') { s._addLog(t('eval_generating_followup'), '🤔', ''); s._updateStep(t('live_step_followup')); return; }
        if (event === 'followup') { s._addLog(t('eval_followup', (data.question || '').substring(0, 150)), '🔄', ''); s._updateStep(t('live_step_send_followup')); return; }
        if (event === 'followup_end') { s._addLog(t('eval_followup_end'), '✅', 'step-ai'); return; }
        if (event === 'conversation_end') { s._addLog(t('eval_conversation_end', data.reason || ''), '🏁', ''); return; }
        if (event === 'turns_done') { s._addLog(t('eval_conversation_done', data.total_turns || 0), '✅', 'step-ai'); s._updateStep(t('live_step_conversation_done')); return; }
        if (event === 'boundary_start') { s._addLog(t('eval_boundary_start'), '🛡️', ''); s._updateStep(t('live_step_boundary')); return; }
        if (event === 'boundary_done') {
            s._addLog(t('eval_boundary_done', data.status || 'N/A', (data.hit_rate || 0).toFixed(1) + '%', data.recommendation || ''), '🛡️', data.status === 'in_scope' ? 'step-ai' : 'step-err');
            return;
        }
        if (event === 'scoring') { s._addLog(t('eval_scoring'), '📊', ''); s._updateStep(t('live_step_scoring')); return; }
        if (event === 'score_done') {
            const div = document.createElement('div'); div.className = 'eval-step';
            div.innerHTML = `<div class="step-icon">📊</div><div class="step-content"><div class="step-label">${t('eval_score_done')}</div><div class="step-text ai">${t('eval_score_done_line', data)}</div>${data.flags?.length ? `<div class="step-text error">⚠️ ${data.flags.join('; ')}</div>` : ''}</div>`;
            body.appendChild(div); s.showScoreCards(data); s._updateStep(t('live_step_scoring')); return;
        }
        if (event === 'scenario_done') {
            s._addLog(t('eval_scenario_done', data.index || '?', (data.overall || 0).toFixed(1), data.boundary_status || 'N/A'), '✅', 'step-ai');
            document.getElementById('progressFill').style.width = `${((data.index || 1) / s.state.evalState.totalScenarios * 100)}%`;
            return;
        }
        if (event === 'done') {
            s._stopTimer(); s._updateStep(t('live_step_done'));
            document.getElementById('progressFill').style.width = '100%';
            document.getElementById('progressLabel').textContent = t('eval_done');
            document.getElementById('startTestBtn').disabled = false;
            s._addLog(t('eval_done') + (data.truncated ? t('eval_truncated', data.completed_scenarios, data.total_scenarios) : ''), '🎉', 'step-ai');
            setTimeout(() => s.loadData(), 2000); return;
        }
        if (event === 'error') {
            s._incErrors(); s._updateStep(t('live_step_error'));
            document.getElementById('startTestBtn').disabled = false;
            const errDiv = document.createElement('div'); errDiv.className = 'eval-step';
            let html = `<div class="step-icon error">❌</div><div class="step-content"><div class="step-text error"><b>${data.message || t('eval_error_unknown')}</b></div>`;
            if (data.traceback) html += `<details style="margin-top:4px;font-size:10px"><summary style="color:var(--red);cursor:pointer">${t('eval_error_traceback_title')}</summary><pre style="background:var(--surface-2);padding:8px;border-radius:4px;overflow-x:auto;max-height:200px;font-size:10px;color:var(--red);white-space:pre-wrap">${data.traceback}</pre></details>`;
            html += `</div>`; errDiv.innerHTML = html; body.appendChild(errDiv); return;
        }
        if (event === 'cancelled') {
            s._stopTimer(); s._updateStep(t('live_step_cancelled')); document.getElementById('startTestBtn').disabled = false;
            s._addLog(t('eval_cancelled', data.reason || ''), '⏹', ''); return;
        }
        body.scrollTop = body.scrollHeight;
    },

    showScoreCards(scores) {
        const dims = ['correctness','relevancy','completeness','guidance','followup_quality','boundary_compliance','turn_consistency','knowledge_scaffolding'];
        const labels = window.getDimLabels ? window.getDimLabels() : ['正确性','相关性','完整性','引导力','追问','边界','一致性','递进性'];
        const grid = document.getElementById('scoreMiniGrid');
        if (!grid) return;
        grid.innerHTML = dims.map((d,i) => {
            const v = scores[d] || 0;
            const cls = v >= 4 ? 'sm-high' : v >= 3 ? 'sm-mid' : 'sm-low';
            return `<div class="score-mini"><div class="sm-val ${cls}">${v.toFixed(1)}</div><div class="sm-label">${labels[i]}</div></div>`;
        }).join('');
    },

    async _loadAgentOptions() {
        try {
            const agents = await api.get('/api/agents');
            const keys = Object.keys(agents || {}).filter(k => k === 'platform');
            const sel = document.getElementById('agentSelect');
            if (sel) {
                sel.innerHTML = keys.map(k => `<option value="${k}">${agents[k]?.name || k}</option>`).join('')
                    || '<option value="platform">实训教学平台</option>';
                const defOpt = sel.querySelector('option[value="platform"]');
                if (defOpt) defOpt.selected = true;
            }
        } catch (e) {
            console.warn('Failed to load agent list:', e);
            const sel = document.getElementById('agentSelect');
            if (sel) sel.innerHTML = '<option value="platform" selected>' + t('agent_option_platform') + '</option>';
        }
    },

    async startTest() {
        const profile = document.getElementById('evalProfile').value;
        const panel = document.getElementById('liveEvalPanel');
        const body = document.getElementById('liveEvalBody');
        const statusBar = document.getElementById('evalStatusBar');
        const hint = document.getElementById('evalModeHint');

        // 浏览器遍历预设 (全平台真实操作)
        const browserPresets = {
            patrol:  { phases: [1,2,3,4,5], mode: 'guided', include_quiz: true, phase_filter: 'sample' },
            full:    { phases: [1,2,3,4,5], mode: 'guided', include_quiz: true },
            deep:    { phases: [1,2,3,4,5], mode: 'both',    include_quiz: true },
        };

        panel.style.display = 'block';
        if (statusBar) statusBar.style.display = 'flex';
        document.getElementById('scoreMiniGrid').innerHTML = '';
        document.getElementById('progressFill').style.width = '0%';

        let data;
        try {
            if (profile === 'custom') {
                // LLM问答模式 (自定义)
                const agent = document.getElementById('agentSelect').value;
                const numQ = parseInt(document.getElementById('numQuestions').value) || 3;
                const maxT = parseInt(document.getElementById('maxTurns').value) || 3;
                body.innerHTML = '<div class="qa-empty">' + t('test_starting') + ' (LLM: ' + numQ + '题×' + maxT + '轮)</div>';
                if (hint) hint.textContent = 'LLM问答模式: 从黄金QA库抽样, 多轮对话评分';
                data = await api.post('/api/tests/run', {
                    agent_id: agent, num_questions: numQ, max_turns: maxT, profile: 'custom',
                });
            } else {
                // 浏览器全平台遍历
                const cfg = browserPresets[profile] || browserPresets.full;
                const labels = {patrol:'巡检 (~5min)', full:'全平台 (~18min)', deep:'深度 (~30min)'};
                body.innerHTML = '<div class="qa-empty">🖥️ ' + (labels[profile]||'') + ' — Playwright浏览器真实遍历...</div>';
                if (hint) hint.textContent = '浏览器模式: Phase ' + cfg.phases.join(',') + ' | ' + cfg.mode + ' | Quiz验证:' + (cfg.include_quiz?'✅':'❌');
                data = await api.post('/api/tests/run-browser', cfg);
            }

            if (data.status !== 'started') {
                showToast(t('start_failed') + JSON.stringify(data), 'error');
                document.getElementById('startTestBtn').disabled = false;
            }
        } catch (e) {
            showToast(t('request_failed') + e.message, 'error');
            document.getElementById('startTestBtn').disabled = false;
        }
    },
};
