/* ════════════════════════════════════════════
   Test Runner Page — 配置 + 实时日志
   ════════════════════════════════════════════ */

import api from '../api.js';
import ws from '../ws.js';
import { showToast, formatDate, formatDuration, escapeHtml } from '../utils.js';
import { t, onLangChange } from '../i18n-bridge.js';

const TestRunnerPage = {
    state: {
        initialized: false, events: [], running: false,
        timer: null, startTs: 0, errorCount: 0,
        evalState: { scenarioIndex: 0, totalScenarios: 0, turnIndex: 0, maxTurns: 0 },
    },

    init() {
        if (this.state.initialized) return;
        ws.on('eval_event', (msg) => this.handleEvent(msg));
        ws.on('connected', () => this._updateWSStatus(true));
        ws.on('disconnected', () => this._updateWSStatus(false));
        ws.on('state', (data) => {
            this.state.running = data.data?.running || false;
            this.updateButtonState();
        });
        onLangChange(() => {
            if (document.getElementById('page-test-runner') &&
                document.getElementById('page-test-runner').classList.contains('active')) {
                this.render();
            }
        });
        this.state.initialized = true;
    },

    async render() {
        this.renderLayout();
        await this._loadAgentOptions();
        this.bindEvents();
        this.loadHistory();
    },

    destroy() {},

    renderLayout() {
        document.getElementById('page-test-runner').innerHTML = `
          <div class="page-header"><h2>${t('test_title')}</h2></div>
          <div class="card" style="margin-bottom:16px">
            <h3 style="color:var(--text-secondary);font-size:14px;margin-bottom:12px">${t('test_config_label')}</h3>
            <div class="flex flex-wrap gap-2 items-center">
              <label style="font-size:13px">${t('test_agent_label')}</label>
              <select id="trAgent"></select>
              <label style="font-size:13px;margin-left:8px">${t('test_profile_label')}</label>
              <select id="trProfile">
                <option value="patrol">🔍 巡检 (~5min)</option>
                <option value="full" selected>📋 全平台 (~18min)</option>
                <option value="deep">🔬 深度 (~30min)</option>
                <option value="custom">⚙️ 自定义</option>
              </select>
              <span id="trCustomOpts" style="display:none">
                <input id="trNum" type="number" value="3" min="1" max="20" style="width:55px" title="题目数">
                <span style="font-size:12px;color:var(--muted)">题 ×</span>
                <input id="trTurns" type="number" value="3" min="1" max="10" style="width:55px" title="每轮追问数">
                <span style="font-size:12px;color:var(--muted)">轮</span>
              </span>
              <button class="btn btn-primary" id="trStartBtn">${t('test_start_btn')}</button>
              <button class="btn btn-outline" id="trStopBtn" disabled>${t('test_stop_btn')}</button>
            </div>
          </div>

          <div id="evalStatusBar" style="display:none;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin-bottom:12px;font-size:12px">
            <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:center">
              <span id="wsIndicator" style="color:var(--red)">${t('sys_ws_disconnected')}</span>
              <span>${t('live_elapsed')} <b id="evalElapsed">00:00</b></span>
              <span>${t('live_step')} <span id="evalStep">${t('live_step_ready')}</span></span>
              <span style="color:var(--red)">${t('live_errors')} <b id="evalErrors">0</b></span>
              <span>${t('live_progress')} <span id="evalProgress">0/0</span></span>
            </div>
          </div>
          <div class="progress-bar" style="margin-bottom:8px"><div class="progress-fill" id="trProgressFill" style="width:0%"></div></div>
          <div style="font-size:12px;color:var(--text-muted);margin-bottom:12px" id="trProgressLabel">${t('live_step_ready')}</div>

          <div class="live-eval">
            <div class="live-eval-header">
              <h3>${t('test_event_log')}</h3>
              <button class="btn btn-outline btn-sm" id="trClearLog">${t('btn_clear')}</button>
            </div>
            <div class="live-eval-body" id="trEventLog" style="max-height:500px">
              <div class="qa-empty">${t('test_waiting')}</div>
            </div>
          </div>

          <div class="score-mini-grid" id="trScoreCards"></div>

          <div class="card" style="margin-top:16px">
            <h3 style="color:var(--text-secondary);font-size:14px;margin-bottom:12px">${t('test_history')}</h3>
            <div id="trHistory">${t('sys_loading')}</div>
          </div>
        `;
    },

    bindEvents() {
        document.getElementById('trStartBtn').addEventListener('click', () => this.startTest());
        const trProfile = document.getElementById('trProfile');
        const trCustom = document.getElementById('trCustomOpts');
        trProfile.addEventListener('change', () => {
            trCustom.style.display = trProfile.value === 'custom' ? 'inline' : 'none';
        });
        document.getElementById('trClearLog').addEventListener('click', () => {
            document.getElementById('trEventLog').innerHTML = '<div class="qa-empty">' + t('log_cleared') + '</div>';
        });
    },

    async startTest() {
        const profile = document.getElementById('trProfile').value;

        const browserPresets = {
            patrol:  { phases: [1,2,3,4,5], mode: 'guided', include_quiz: true },
            full:    { phases: [1,2,3,4,5], mode: 'guided', include_quiz: true },
            deep:    { phases: [1,2,3,4,5], mode: 'both',    include_quiz: true },
        };

        let params, endpoint;
        if (profile === 'custom') {
            const agent = document.getElementById('trAgent').value;
            const numQ = parseInt(document.getElementById('trNum').value) || 3;
            const maxT = parseInt(document.getElementById('trTurns').value) || 3;
            params = { agent_id: agent, num_questions: numQ, max_turns: maxT, profile: 'custom' };
            endpoint = '/api/tests/run';
        } else {
            params = browserPresets[profile] || browserPresets.full;
            endpoint = '/api/tests/run-browser';
        }

        const labels = {patrol:'巡检 ~5min', full:'全平台 ~18min', deep:'深度 ~30min', custom:'LLM问答'};
        document.getElementById('trEventLog').innerHTML = '<div style="color:var(--accent-yellow);text-align:center;padding:20px">🖥️ ' + (labels[profile]||'') + ' — 启动中...</div>';
        try {
            const data = await api.post(endpoint, params);
            if (data.status !== 'started') {
                showToast(t('start_failed', ''), 'error');
            }
        } catch (e) {
            showToast(t('request_failed') + e.message, 'error');
        }
    },

    // ═══ 状态辅助方法 ═══
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
        const log = document.getElementById('trEventLog'); if (!log) return;
        const time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
        const div = document.createElement('div'); div.className = 'eval-step';
        div.innerHTML = `<div class="step-icon">${icon || '📌'}</div><div><div style="color:var(--muted);font-size:11px">${time}</div><div class="step-text ${cls || ''}">${msg}</div></div>`;
        log.appendChild(div); log.scrollTop = log.scrollHeight;
    },

    handleEvent(msg) {
        const log = document.getElementById('trEventLog');
        const statusBar = document.getElementById('evalStatusBar');
        if (!log) return;
        if (statusBar) statusBar.style.display = 'flex';

        const { event, data } = msg;
        const s = this;

        if (event === 'test_start') {
            s.state.events = []; s.state.errorCount = 0; s._startTimer(); s._updateStep(t('live_step_starting'));
            s._updateProgress(0, data.total || 0, 0, 0);
            document.getElementById('trScoreCards').innerHTML = '';
            document.getElementById('trProgressLabel').textContent = t('agent_scenarios', data.agent, data.total);
            document.getElementById('trProgressFill').style.width = '0%';
            s._addLog(t('eval_test_start', data.agent, data.total || 0), '🚀', '');
            if (data.questions) data.questions.forEach(q => s._addLog(`📋 ${q.qa_id || ''} [${q.phase || ''}] ${(q.question || '').substring(0, 80)}`, '📋', ''));
            return;
        }
        if (event === 'scenario_start') {
            const div = document.createElement('div'); div.className = 'scenario-divider';
            div.textContent = t('scenario_divider', data.index, data.total) + ' · ' + (data.qa_id || ''); log.appendChild(div);
            s._updateProgress(data.index, data.total, 0, s.state.evalState.maxTurns);
            s._updateStep(t('scenario_n', data.index, data.total));
            document.getElementById('trProgressFill').style.width = `${(data.index - 1) / data.total * 100}%`;
            document.getElementById('trProgressLabel').textContent = t('scenario_n', data.index, data.total);
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
            log.appendChild(div); s._updateStep(t('live_step_scoring'));
            const dims = ['correctness','relevancy','completeness','guidance','followup_quality','boundary_compliance','turn_consistency','knowledge_scaffolding'];
            const labels = window.getDimLabels ? window.getDimLabels() : ['正确性','相关性','完整性','引导力','追问','边界','一致性','递进性'];
            const grid = document.getElementById('trScoreCards');
            if (grid) grid.innerHTML = dims.map((d,i) => { const v = data[d] || 0; const cls = v >= 4 ? 'sm-high' : v >= 3 ? 'sm-mid' : 'sm-low'; return `<div class="score-mini"><div class="sv ${cls}">${v.toFixed(1)}</div><div class="sl">${labels[i]}</div></div>`; }).join('');
            return;
        }
        if (event === 'scenario_done') {
            s._addLog(t('eval_scenario_done', data.index || '?', (data.overall || 0).toFixed(1), data.boundary_status || 'N/A'), '✅', 'step-ai');
            document.getElementById('trProgressFill').style.width = `${((data.index || 1) / s.state.evalState.totalScenarios * 100)}%`;
            return;
        }
        if (event === 'done') {
            s._stopTimer(); s._updateStep(t('live_step_done'));
            document.getElementById('trProgressFill').style.width = '100%';
            document.getElementById('trProgressLabel').textContent = t('eval_done');
            s._addLog(t('eval_done') + (data.truncated ? t('eval_truncated', data.completed_scenarios, data.total_scenarios) : ''), '🎉', 'step-ai');
            setTimeout(() => s.loadHistory(), 2000); return;
        }
        if (event === 'error') {
            s._incErrors(); s._updateStep(t('live_step_error'));
            document.getElementById('trProgressLabel').textContent = '❌ ' + (data.message || t('eval_error_unknown'));
            const errDiv = document.createElement('div'); errDiv.className = 'eval-step';
            let html = `<div class="step-icon">❌</div><div><div class="step-text error"><b>${escapeHtml(data.message || t('eval_error_unknown'))}</b></div>`;
            if (data.traceback) html += `<details style="margin-top:4px;font-size:10px"><summary style="color:var(--red);cursor:pointer">${t('eval_error_traceback_title')}</summary><pre style="background:var(--surface-2);padding:8px;border-radius:4px;overflow-x:auto;max-height:200px;font-size:10px;color:var(--red);white-space:pre-wrap">${escapeHtml(data.traceback)}</pre></details>`;
            html += `</div>`; errDiv.innerHTML = html; log.appendChild(errDiv);
            return;
        }
        if (event === 'cancelled') {
            s._stopTimer(); s._updateStep(t('live_step_cancelled'));
            s._addLog(t('eval_cancelled', data.reason || ''), '⏹', ''); return;
        }

        log.scrollTop = log.scrollHeight;
    },

    async _loadAgentOptions() {
        try {
            const agents = await api.get('/api/agents');
            const keys = Object.keys(agents || {}).filter(k => k === 'platform');
            const sel = document.getElementById('trAgent');
            if (sel) {
                sel.innerHTML = keys.map(k => `<option value="${k}">${agents[k]?.name || k}</option>`).join('')
                    || '<option value="platform">实训教学平台</option>';
                const defOpt = sel.querySelector('option[value="platform"]');
                if (defOpt) defOpt.selected = true;
            }
        } catch (e) {
            console.warn('Failed to load agent list:', e);
            const sel = document.getElementById('trAgent');
            if (sel) sel.innerHTML = '<option value="platform" selected>' + t('agent_option_platform') + '</option>';
        }
    },

    async loadHistory() {
        const el = document.getElementById('trHistory');
        if (!el) return;
        try {
            const data = await api.get('/api/tests/sessions', { page_size: 10 });
            if (!data.items?.length) {
                el.innerHTML = '<span class="text-muted">' + t('test_no_history') + '</span>';
                return;
            }
            el.innerHTML = data.items.map(s => `
              <div style="padding:8px 12px;border:1px solid var(--bg-tertiary);border-radius:6px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center">
                <div>
                  <span style="font-size:13px">📄 ${formatDate(s.created_at)}</span>
                  <span class="badge badge-info" style="margin-left:8px">${s.agent_id}</span>
                  <span class="badge ${s.status === 'success' ? 'badge-approved' : s.status === 'error' ? 'badge-rejected' : 'badge-pending'}">${s.status}</span>
                  <span style="font-size:12px;color:var(--text-muted);margin-left:8px">${s.total_scenarios}${t('scenario_label')}</span>
                </div>
              </div>
            `).join('');
        } catch (e) {
            el.innerHTML = '<span class="text-muted">' + t('sys_error') + '</span>';
        }
    },

    updateButtonState() {
        const btn = document.getElementById('trStartBtn');
        if (btn) btn.disabled = this.state.running;
    },
};

export default TestRunnerPage;
