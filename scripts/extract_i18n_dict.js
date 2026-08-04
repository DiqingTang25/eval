/**
 * extract_i18n_dict.js — 从 i18n.js 提取字典到 JSON 文件
 *
 * 功能:
 * 1. 创建模拟浏览器环境
 * 2. 加载 i18n.js
 * 3. 将 I18N_DICT 中的函数值转换为模板字符串 ({0}, {1}...)
 * 4. 输出 frontend/locales/zh.json 和 en.json
 *
 * 用法: node scripts/extract_i18n_dict.js
 */

const fs = require('fs');
const path = require('path');

// ── 创建模拟浏览器环境 ──
global.window = global;
global.document = {
  querySelectorAll: () => [],
  title: '',
  documentElement: { lang: '' }
};
global.localStorage = {
  _data: {},
  getItem(k) { return this._data[k] || null; },
  setItem(k, v) { this._data[k] = v; }
};
global.console = console;

// ── 加载 i18n.js ──
const i18nPath = path.join(__dirname, '..', 'frontend', 'js', 'i18n.js');
const i18nSrc = fs.readFileSync(i18nPath, 'utf-8');

// 用 Function 构造器执行 (避免 eval 的模块作用域问题)
const fn = new Function(i18nSrc);
fn();

// ── 获取字典 ──
const dict = global.I18N_DICT;
if (!dict || !dict.zh || !dict.en) {
  console.error('ERROR: Failed to extract I18N_DICT from i18n.js');
  process.exit(1);
}

/**
 * 将函数源码转换为模板字符串
 * 支持的函数模式:
 *   function(x) { return x + '分'; }              → "{0}分"
 *   function(n, e) { return n + ' · ' + e; }     → "{0} · {1}"
 *   function(i, tt) { return '场景 ' + i; }       → "场景 {0}"
 *
 * 策略: 调用 toString(), 用正则找到 return 语句,
 * 将参数引用替换为 {N} 占位符
 */
function functionToTemplate(fn) {
  const src = fn.toString();

  // 提取参数名
  const paramMatch = src.match(/^function\s*\(([^)]*)\)/);
  if (!paramMatch) return fn; // 无法解析, 保留原函数

  const params = paramMatch[1].split(',').map(s => s.trim()).filter(Boolean);
  if (params.length === 0) return fn;

  // 提取 return 语句
  const returnMatch = src.match(/return\s+(.+?);?\s*\}/s);
  if (!returnMatch) return fn;

  let expr = returnMatch[1].trim();

  // 按参数名长度降序排序, 避免短名称先替换长名称的问题
  const sorted = [...params].sort((a, b) => b.length - a.length);

  // 为每个参数分配一个唯一占位符, 避免冲突
  const placeholders = {};
  sorted.forEach((p, i) => {
    placeholders[p] = `__PARAM_${i}__`;
  });

  // 先替换参数名为占位符
  for (const [pname, ph] of Object.entries(placeholders)) {
    // 只替换标识符 (前后非字母数字), 避免替换字符串内容
    const regex = new RegExp('\\b' + pname.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b', 'g');
    expr = expr.replace(regex, ph);
  }

  // 现在将占位符替换为 {N} 格式
  for (const [pname, ph] of Object.entries(placeholders)) {
    const idx = sorted.indexOf(pname);
    expr = expr.replace(new RegExp(ph, 'g'), `{${idx}}`);
  }

  // 去除字符串拼接符号: 'str' + expr → 合并
  // 简化: 用 eval 计算表达式, 传入模拟参数
  try {
    const testArgs = params.map((_, i) => `__ARG_${i}__`);
    const testFn = new Function(...params, `return ${returnMatch[1]};`);
    const result = testFn(...testArgs);
    if (typeof result === 'string') {
      // 将测试参数替换回 {N}
      let template = result;
      params.forEach((_, i) => {
        template = template.replace(new RegExp(`__ARG_${i}__`, 'g'), `{${i}}`);
      });
      return template;
    }
  } catch (e) {
    // eval 失败, 降级到正则方法
  }

  // 降级: 直接用替换后的表达式
  return expr;
}

/**
 * 递归转换字典中的所有函数值
 */
function convertDict(obj) {
  const result = {};
  for (const [key, value] of Object.entries(obj)) {
    if (typeof value === 'function') {
      result[key] = functionToTemplate(value);
    } else if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      result[key] = convertDict(value);
    } else {
      result[key] = value;
    }
  }
  return result;
}

// ── 转换并输出 ──
const zhDict = convertDict(dict.zh);
const enDict = convertDict(dict.en);

const localesDir = path.join(__dirname, '..', 'frontend', 'locales');
if (!fs.existsSync(localesDir)) {
  fs.mkdirSync(localesDir, { recursive: true });
}

fs.writeFileSync(
  path.join(localesDir, 'zh.json'),
  JSON.stringify(zhDict, null, 2),
  'utf-8'
);
fs.writeFileSync(
  path.join(localesDir, 'en.json'),
  JSON.stringify(enDict, null, 2),
  'utf-8'
);

// ── 统计 ──
const zhKeys = Object.keys(zhDict).length;
const enKeys = Object.keys(enDict).length;
const zhFuncs = Object.values(zhDict).filter(v => typeof v === 'string' && v.includes('{')).length;
const enFuncs = Object.values(enDict).filter(v => typeof v === 'string' && v.includes('{')).length;

console.log(`✅ Extracted i18n dictionary:`);
console.log(`   zh.json: ${zhKeys} keys (${zhFuncs} template strings)`);
console.log(`   en.json: ${enKeys} keys (${enFuncs} template strings)`);
console.log(`   Output: ${localesDir}/`);
