/* App — SPA 路由 / 状态管理 */
import { ws } from './ws.js';

const pages = {};
let currentPage = 'dashboard';

// 简单路由
async function navigateTo(pageName) {
    // 隐藏所有页面
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav a').forEach(a => a.classList.remove('active'));

    // 激活目标
    const pageEl = document.getElementById(`page-${pageName}`);
    if (pageEl) pageEl.classList.add('active');
    const navEl = document.querySelector(`.nav a[data-page="${pageName}"]`);
    if (navEl) navEl.classList.add('active');

    // 加载页面模块
    if (!pages[pageName]) {
        try {
            const mod = await import(`./pages/${pageName}.js`);
            pages[pageName] = mod.default || mod;
        } catch (e) {
            console.warn(`Failed to load ${pageName}:`, e);
            if (pageEl) pageEl.innerHTML = `<div class="qa-empty">页面加载失败: ${pageName}</div>`;
            return;
        }
    }

    // 渲染
    currentPage = pageName;
    const page = pages[pageName];
    if (page.init) page.init();
    if (page.render) await page.render();
}

// 导航点击
document.querySelectorAll('.nav a').forEach(link => {
    link.addEventListener('click', () => {
        const page = link.dataset.page;
        if (page) navigateTo(page);
    });
});

// 页面加载完成
window.addEventListener('DOMContentLoaded', async () => {
    window.__appLoaded = true;  // 通知内联JS跳过重复初始化
    ws.connect();
    await navigateTo('dashboard');
});

// 暴露全局
window.navigateTo = navigateTo;
