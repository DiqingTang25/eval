/* ════════════════════════════════════════════
   i18n-bridge.js — ES 模块桥接

   页面模块 (ES modules) 通过此文件调用 i18n, 与 index.html
   内联代码共享同一份字典和语言状态 (通过全局 window.t 等函数).

   使用方法:
     import { t, onLangChange, getLang } from '../i18n-bridge.js';

   确保 i18n.js 在此模块被导入前已加载 (通过 index.html 的
   <script src="js/i18n.js"></script> 保证).
   ════════════════════════════════════════════ */

function _check() {
  if (typeof window.t !== 'function') {
    console.error('[i18n-bridge] window.t is not available — ensure i18n.js is loaded before page modules');
  }
}

export function t(key, ...args) {
  _check();
  return window.t(key, ...args);
}

export function getLang() {
  return window.getLang ? window.getLang() : 'zh';
}

export function setLang(l) {
  if (window.setLang) window.setLang(l);
}

export function onLangChange(fn) {
  if (window.onLangChange) return window.onLangChange(fn);
  console.warn('[i18n-bridge] onLangChange not available');
  return () => {};
}

export function tStatus(s) {
  return window.tStatus ? window.tStatus(s) : s;
}

export function getDimLabels() {
  return window.getDimLabels ? window.getDimLabels() : [];
}

export function getDimFullLabels() {
  return window.getDimFullLabels ? window.getDimFullLabels() : [];
}

export function getDimIcon(key) {
  return window.getDimIcon ? window.getDimIcon(key) : '';
}

export function refreshActivePage() {
  if (window.refreshActivePage) window.refreshActivePage();
}

export default { t, getLang, setLang, onLangChange, tStatus, getDimLabels, getDimFullLabels, getDimIcon, refreshActivePage };
