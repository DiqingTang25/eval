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
            <h2>📚 知识库管理</h2>
            <div class="flex gap-2">
              <button class="btn btn-primary btn-sm" id="kbSyncBtn">🔄 同步火山引擎知识库</button>
              <button class="btn btn-outline btn-sm" id="kbRefreshBtn">🔄 刷新</button>
            </div>
          </div>
          <div id="kbStatusBar" style="margin-bottom:16px;font-size:13px"></div>
          <div class="kb-grid" id="kbGrid"><div class="qa-empty">加载中...</div></div>
          <div class="kb-doc-list" id="kbDocList" style="display:none">
            <h3 style="color:var(--accent-blue);margin-bottom:12px" id="kbDocTitle">📄 文档列表</h3>
            <div id="kbDocuments"><span class="text-muted">选择知识库查看文档</span></div>
          </div>
          <div class="card mt-4">
            <h3 style="color:var(--text-secondary);font-size:14px;margin-bottom:8px">🔍 搜索知识库</h3>
            <div class="flex gap-2">
              <input id="kbSearchInput" type="text" placeholder="输入查询..." style="flex:1">
              <button class="btn btn-primary btn-sm" id="kbSearchBtn">搜索</button>
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
            el.innerHTML = `<span class="badge ${cls}">${status.configured ? '✅ 火山引擎已配置' : '❌ 火山引擎未配置'}</span>
              <span style="color:var(--text-muted);margin-left:8px">服务ID: ${status.service_id || '(未设置)'}</span>`;

            const bases = await api.get('/api/kb/bases');
            this.renderBases(bases);
        } catch (e) {
            showToast('加载知识库状态失败', 'error');
        }
    },

    renderBases(data) {
        const grid = document.getElementById('kbGrid');
        if (!data.items?.length) {
            grid.innerHTML = '<div class="qa-empty">暂无已同步的知识库<br><span class="text-muted">点击"从Dify同步"按钮同步</span></div>';
            return;
        }
        grid.innerHTML = data.items.map(b => `
          <div class="card kb-card" data-base-id="${b.id}">
            <h4 style="color:var(--accent-blue);margin-bottom:4px">📁 ${b.name}</h4>
            <div style="font-size:12px;color:var(--text-secondary)">${b.description || ''}</div>
            <div style="font-size:12px;color:var(--text-muted);margin-top:8px">
              文档: ${b.document_count} · 状态: <span class="badge badge-${b.sync_status === 'synced' ? 'approved' : 'pending'}">${b.sync_status}</span>
            </div>
            ${b.last_synced_at ? `<div style="font-size:11px;color:var(--text-muted);margin-top:4px">上次同步: ${formatDate(b.last_synced_at)}</div>` : ''}
          </div>
        `).join('');

        // 点击知识库查看文档
        grid.querySelectorAll('.kb-card').forEach(card => {
            card.addEventListener('click', () => this.loadDocuments(card.dataset.baseId, card.querySelector('h4').textContent));
        });
    },

    async loadDocuments(baseId, baseName) {
        document.getElementById('kbDocList').style.display = 'block';
        document.getElementById('kbDocTitle').textContent = `📄 ${baseName} - 文档列表`;
        try {
            const data = await api.get(`/api/kb/bases/${baseId}/documents`);
            if (!data.items?.length) {
                document.getElementById('kbDocuments').innerHTML = '<span class="text-muted">暂无文档</span>';
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
            showToast('加载文档失败', 'error');
        }
    },

    async sync() {
        document.getElementById('kbGrid').innerHTML = '<div class="qa-empty">⏳ 正在同步火山引擎知识库...</div>';
        try {
            const result = await api.post('/api/kb/bases/sync');
            if (result.ok) {
                showToast(`已同步 ${result.synced} 个知识库`, 'success');
                await this.refresh();
            } else {
                showToast('同步失败: ' + (result.error || 'Unknown'), 'error');
                await this.refresh();
            }
        } catch (e) {
            showToast('同步请求失败: ' + e.message, 'error');
            await this.refresh();
        }
    },

    async search() {
        const q = document.getElementById('kbSearchInput').value.trim();
        if (!q) { showToast('请输入搜索内容', 'info'); return; }
        document.getElementById('kbSearchResults').innerHTML = '<div class="qa-empty">⏳ 搜索中...</div>';
        try {
            const result = await api.get(`/api/kb/search?q=${encodeURIComponent(q)}`);
            if (result.ok) {
                const records = result.results || [];
                if (!records.length) {
                    document.getElementById('kbSearchResults').innerHTML = '<span class="text-muted">未找到结果</span>';
                } else {
                    document.getElementById('kbSearchResults').innerHTML = records.map(r => `
                      <div style="padding:8px;background:var(--bg-primary);border-radius:4px;margin-bottom:4px;font-size:12px">
                        <div style="color:var(--accent-blue)">${r.dataset_name || 'Unknown'}</div>
                        <div style="color:var(--text-secondary);margin-top:4px">${(r.content || '').substring(0, 200)}</div>
                      </div>
                    `).join('');
                }
            } else {
                document.getElementById('kbSearchResults').innerHTML = `<span style="color:var(--accent-red)">搜索失败: ${result.error}</span>`;
            }
        } catch (e) {
            document.getElementById('kbSearchResults').innerHTML = `<span style="color:var(--accent-red)">搜索请求失败</span>`;
        }
    },
};

export default KBPage;
