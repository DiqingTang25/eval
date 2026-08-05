/* ════════════════════════════════════════════
   Knowledge Base Page — Dify 集成管理
   ════════════════════════════════════════════ */

import api from '../api.js';
import { showToast, formatDate } from '../utils.js';
import { t, onLangChange } from '../i18n-bridge.js';

const KBPage = {
    state: { initialized: false },

    init() {
        this.state.initialized = true;
        onLangChange(() => {
            if (document.getElementById('page-kb') &&
                document.getElementById('page-kb').classList.contains('active')) {
                this.render();
            }
        });
    },
    async render() { this.renderLayout(); await this.refresh(); },
    destroy() {},

    renderLayout() {
        document.getElementById('page-kb').innerHTML = `
          <div class="page-header">
            <h2>📚 ${t('kb_bases_title')}</h2>
            <div class="flex gap-2">
              <button class="btn btn-primary btn-sm" id="kbSyncBtn">${t('kb_sync_btn')}</button>
              <button class="btn btn-outline btn-sm" id="kbRefreshBtn">${t('btn_refresh')}</button>
            </div>
          </div>
          <div id="kbStatusBar" style="margin-bottom:16px;font-size:13px"></div>
          <div class="kb-grid" id="kbGrid"><div class="qa-empty">${t('sys_loading')}</div></div>
          <div class="kb-doc-list" id="kbDocList" style="display:none">
            <h3 style="color:var(--accent-blue);margin-bottom:12px" id="kbDocTitle">${t('kb_doc_title')}</h3>
            <div id="kbDocuments"><span class="text-muted">${t('kb_doc_select_hint')}</span></div>
          </div>
          <div class="card mt-4">
            <h3 style="color:var(--text-secondary);font-size:14px;margin-bottom:8px">${t('kb_search_title')}</h3>
            <div class="flex gap-2">
              <input id="kbSearchInput" type="text" placeholder="${t('kb_search_input_ph')}" style="flex:1">
              <button class="btn btn-primary btn-sm" id="kbSearchBtn">${t('kb_search_btn')}</button>
            </div>
            <div id="kbSearchResults" style="margin-top:12px"></div>
          </div>
        `;
        this.bindEvents();
    },

    bindEvents() {
        document.getElementById('kbSyncBtn').addEventListener('click', () => this.sync());
        document.getElementById('kbRefreshBtn').addEventListener('click', () => this.refresh());
        document.getElementById('kbSearchBtn').addEventListener('click', () => this.search());
    },

    async refresh() {
        try {
            const status = await api.get('/api/kb/status');
            const el = document.getElementById('kbStatusBar');
            const cls = status.configured ? 'badge-approved' : 'badge-rejected';
            el.innerHTML = `<span class="badge ${cls}">${status.configured ? t('kb_configured') : t('kb_not_configured')}</span>
              <span style="color:var(--text-muted);margin-left:8px">${t('kb_service_id')}: ${status.service_id || t('kb_no_service_id')}</span>`;

            const bases = await api.get('/api/kb/bases');
            this.renderBases(bases);
        } catch (e) {
            showToast(t('kb_status_load_fail'), 'error');
        }
    },

    renderBases(data) {
        const grid = document.getElementById('kbGrid');
        if (!data.items?.length) {
            grid.innerHTML = `<div class="qa-empty">${t('kb_no_bases')}<br><span class="text-muted">${t('kb_sync_hint')}</span></div>`;
            return;
        }
        grid.innerHTML = data.items.map(b => `
          <div class="card kb-card" data-base-id="${b.id}">
            <h4 style="color:var(--accent-blue);margin-bottom:4px">📁 ${b.name}</h4>
            <div style="font-size:12px;color:var(--text-secondary)">${b.description || ''}</div>
            <div style="font-size:12px;color:var(--text-muted);margin-top:8px">
              ${t('kb_doc_count')}: ${b.document_count} · ${t('kb_sync_status')}:<span class="badge badge-${b.sync_status === 'synced' ? 'approved' : 'pending'}">${b.sync_status}</span>
            </div>
            ${b.last_synced_at ? `<div style="font-size:11px;color:var(--text-muted);margin-top:4px">${t('kb_last_sync')}: ${formatDate(b.last_synced_at)}</div>` : ''}
          </div>
        `).join('');

        grid.querySelectorAll('.kb-card').forEach(card => {
            card.addEventListener('click', () => this.loadDocuments(card.dataset.baseId, card.querySelector('h4').textContent));
        });
    },

    async loadDocuments(baseId, baseName) {
        document.getElementById('kbDocList').style.display = 'block';
        document.getElementById('kbDocTitle').textContent = `📄 ${baseName} - ${t('kb_doc_title').replace('📄 ', '')}`;
        try {
            const data = await api.get(`/api/kb/bases/${baseId}/documents`);
            if (!data.items?.length) {
                document.getElementById('kbDocuments').innerHTML = `<span class="text-muted">${t('kb_doc_no_data')}</span>`;
                return;
            }
            document.getElementById('kbDocuments').innerHTML = data.items.map(d => `
              <div style="padding:8px 12px;border:1px solid var(--bg-tertiary);border-radius:6px;margin-bottom:4px;display:flex;justify-content:space-between;align-items:center">
                <div>
                  <span style="font-size:13px">📄 ${d.name}</span>
                  <span class="badge badge-info" style="margin-left:8px">${d.status}</span>
                </div>
                <div style="font-size:11px;color:var(--text-muted)">
                  ${d.chunk_count} chunks · ${d.tokens} tokens
                </div>
              </div>
            `).join('');
        } catch (e) {
            showToast(t('kb_doc_load_fail_msg'), 'error');
        }
    },

    async sync() {
        document.getElementById('kbGrid').innerHTML = `<div class="qa-empty">${t('kb_syncing')}</div>`;
        try {
            const result = await api.post('/api/kb/bases/sync');
            if (result.ok) {
                showToast(t('kb_sync_success', result.synced), 'success');
                await this.refresh();
            } else {
                showToast(t('kb_sync_failed') + ': ' + (result.error || 'Unknown'), 'error');
                await this.refresh();
            }
        } catch (e) {
            showToast(t('kb_sync_req_fail_msg') + ': ' + e.message, 'error');
            await this.refresh();
        }
    },

    async search() {
        const q = document.getElementById('kbSearchInput').value.trim();
        if (!q) { showToast(t('kb_no_query'), 'info'); return; }
        document.getElementById('kbSearchResults').innerHTML = `<div class="qa-empty">${t('kb_searching')}</div>`;
        try {
            const result = await api.get(`/api/kb/search?q=${encodeURIComponent(q)}`);
            if (result.ok) {
                const records = result.results || [];
                if (!records.length) {
                    document.getElementById('kbSearchResults').innerHTML = `<span class="text-muted">${t('kb_no_results_text')}</span>`;
                } else {
                    document.getElementById('kbSearchResults').innerHTML = records.map(r => `
                      <div style="padding:8px;background:var(--bg-primary);border-radius:4px;margin-bottom:4px;font-size:12px">
                        <div style="color:var(--accent-blue)">${r.dataset_name || 'Unknown'}</div>
                        <div style="color:var(--text-secondary);margin-top:4px">${(r.content || '').substring(0, 200)}</div>
                      </div>
                    `).join('');
                }
            } else {
                document.getElementById('kbSearchResults').innerHTML = `<span style="color:var(--accent-red)">${t('kb_search_fail')}: ${result.error}</span>`;
            }
        } catch (e) {
            document.getElementById('kbSearchResults').innerHTML = `<span style="color:var(--accent-red)">${t('kb_search_req_fail_msg')}</span>`;
        }
    },
};

export default KBPage;
