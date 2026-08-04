# 前端 UI 优化 + 中英双语交付说明（2026-07-09）

> 目标页面：`http://124.174.108.70:8000/`（AI Agent 评测平台 Dashboard）
>
> 本次交付两部分：
> 1. **外观精致化**（纯 CSS，深色 slate + 天蓝主题升级）——严格「只改外观」。
> 2. **中英双语切换**（i18n，用户后续明确新增需求）——新增语言切换功能，**同一时刻只显示一种语言**，全部文案可切换；**保留全部运行逻辑 / API 调用 / 数据流不变**。

---

## 1. 改了哪个文件（只有一个）

**`frontend/index.html`** —— 自包含单文件（内联 `<style>` + 内联 `<script>` + 一个 Chart.js CDN）。本次改了：内联 `<style>`（外观）、body 内静态文案加 `data-i18n` 标注、内联 `<script>`（新增 i18n 引擎 + 把注入文案改为 `t()`）。

### 重要澄清：线上页面的真实来源
- 线上端口 8000 由 `backend/main.py`（FastAPI）提供，SPA 回退把 `frontend/index.html` 作为首页返回，用 `FileResponse` **每次请求都从磁盘现读**。
- `frontend/css/*.css`、`frontend/js/*.js` 是**旧版模块化结构，当前 index.html 并未引用**。本次**无需改动**它们。
- 结论：上线只需替换云端 `/opt/agent_eval/frontend/index.html` **这一个文件**，`FileResponse` 读盘即时生效，**无需重启服务**。

文件体积：`21826 → 38363` 字节（668 行）。增量 = 外观 CSS + i18n 字典/引擎。

---

## 2. 外观优化（纯 CSS，保持原深色 slate + 天蓝主色调）

保留原配色基调的原因：JS 向 DOM 注入的片段带**硬编码颜色**（`#38bdf8/#22c55e/#94a3b8` 等），换主题会冲突。故「同色系精致化」而非「换肤」。

| 区域 | 优化前 | 优化后 |
|---|---|---|
| 背景 | 纯色 `#0f172a` | 分层径向光晕（天蓝 + 靛蓝）+ 固定视差 |
| 顶栏 header | 扁平实心 | 玻璃拟态 backdrop-blur + sticky 吸顶 + 渐变标题 + 阴影 |
| 状态「在线」 | 纯文字 emoji | 绿色胶囊 + 纯 CSS 呼吸圆点 |
| 导航 nav | 直角下划线 | sticky + 悬停高亮 + 渐变发光激活指示条 |
| 统计卡 card | 扁平 | 渐变卡面 + 顶部高光线 + 悬浮抬升 + 渐变大数字 |
| 按钮 | 纯色/透明 | 主按钮渐变+投影+悬停增亮；次按钮描边+悬停染色；按下微动效 |
| 输入 / 下拉 | 基础边框 | 统一圆角 + hover/focus 光环 |
| 表格 | 直角、粗分割线 | 圆角容器 + 大写表头 + 行悬停 + 末行去线 |
| 徽章 badge | 直角小块 | 胶囊 + 同色描边 + 垂直居中 |
| 进度条 | 6px 实心 | 8px 圆角 + 渐变 + 辉光 |
| 实时评测面板 | 基础 | 渐变头部 + 时间线式步骤行 + 渐变图标块 |
| 评分小卡 | 扁平 | 渐变卡 + 悬浮 + 分值发光（高绿/中黄/低红） |
| 语言切换按钮 | 无 | 顶栏右侧胶囊按钮（EN ⇄ 中） |
| 其它 | — | 页面淡入动画 / 定制滚动条 / `:focus-visible` 光环 / `prefers-reduced-motion` 降级 / 内容 1280px 居中 / 移动端适配 |

---

## 3. 中英双语切换（i18n）——实现方式

**设计目标**：一键切换中/英，同一时刻只显示一种语言，覆盖 6 个页面**所有**可见文案（静态 + JS 动态注入），且不碰任何业务逻辑。

**机制**：
- **切换入口**：顶栏右侧 `#langToggle` 按钮，`onclick="toggleLang()"`，按钮显示目标语言（中文界面显示「EN」，英文界面显示「中」）。
- **静态文案**：给元素加 `data-i18n="key"`（文本）、`data-i18n-ph="key"`（placeholder）。`applyI18n()` 遍历这些属性写入当前语言文本。共 **44** 个静态键。
- **动态注入文案**：JS 里所有拼接字符串改为 `t('key', ...args)` 查字典；带变量的用函数值（如分页 `共 N 条` / `N total`、场景计数、评分行等）。
- **字典**：`const I18N = { zh:{...}, en:{...} }`，**zh/en 各 86 个键，一一对齐**（已校验无缺失、无类型不匹配）。
- **状态词**：`tStatus(s)` 把 `pending/approved/rejected/success/failed/synced` 等映射为本地化标签。
- **记忆**：选择存 `localStorage['lang']`，刷新后保持；默认中文。切换时 `applyI18n()` + 重新渲染当前页（`refreshActivePage()`）让动态内容也即时变语言。同时设置 `document.title` 与 `<html lang>`。

**关键的逻辑兼容修复**：
- 原 `showPage()` 靠导航**文字** `a.textContent.includes('首页'…)` 判定高亮——翻译成英文会失效。已改为语言无关的 `a.dataset.page===name`（导航加 `data-page="home|qa|test|reports|webeval|kb"`）。**行为完全等价**，且不再依赖文案。
- 两个「清空日志」按钮原用内联 `onclick` 直接写死中文 innerHTML，改为 `clearBox(id)` 帮助函数（用 `t('log_cleared')`），行为不变。

---

## 4. 零逻辑改动 / 双语正确性（已自动校验通过）

- ✅ **JS 语法**：`node --check` 通过。
- ✅ **路由**：6 个 `showPage(...)` 全在；高亮匹配改用 `data-page`（6 个），旧 `textContent.includes` 匹配已移除。
- ✅ **API**：10 条 `/api/*` 路径（dashboard/summary、dashboard/sessions、tests/run、qa、qa/、web-eval/run、web-eval/results、kb/status、kb/bases、kb/bases/sync）**逐一未改**。
- ✅ **元素 ID**：全部保留 + 新增 `langToggle`（totalTests/avgScore/progressFill/liveEvalBody/scoreMiniGrid/trendChart/radarChart/qaTable/reportTable/weUrl/kbStatus/trLog… 无缺失）。
- ✅ **注入类名**：card / val / badge-* / eval-step / step-icon / step-* / scenario-divider / score-mini / sv / sl / sm-high|mid|low / qa-empty 全保留。
- ✅ **option value**：platform / web_test / basic / standard / comprehensive / all / pending / approved / rejected 未改。
- ✅ **i18n 覆盖**：44 个 HTML `data-i18n` 键全部能在字典解析；zh/en 各 86 键完全对齐；`dim_labels` 中英均 8 项。
- ✅ WebSocket、fetch、Chart.js 逻辑零改动。

> 建议上线后做一次浏览器冒烟：点 EN/中 来回切一次，逐页确认无残留另一种语言、无 JS 报错、路由高亮正常。

---

## 5. 交给专属 Agent 上云的操作

线上：火山云 ECS `124.174.108.70`（ECS-AOA-01，Ubuntu 22.04），systemd 服务 `agent-eval`，工作目录 `/opt/agent_eval`，SSH 用户 **`jennifer07`**（密钥对 agent-eval-key）。

> 私钥已落盘到 WSL：`~/.ssh/agent-eval-key`（权限 600，已验证可连通）。

**推荐部署（单文件替换，零停机，无需重启）：**

```bash
# 在 WSL 内执行
KEY=~/.ssh/agent-eval-key
SRV=jennifer07@124.174.108.70
LOCAL=/home/jennifer07/agent_eval/frontend/index.html

# 0) 先确认写权限/sudo（本轮因用户叫停上云未最终确认）
ssh -i "$KEY" "$SRV" 'ls -la /opt/agent_eval/frontend/; test -w /opt/agent_eval/frontend/index.html && echo WRITABLE || echo NEED_SUDO; sudo -n true 2>/dev/null && echo SUDO_NOPASSWD || echo SUDO_PW'

# 1) 云端备份当前线上文件
ssh -i "$KEY" "$SRV" 'cp /opt/agent_eval/frontend/index.html /opt/agent_eval/frontend/index.html.bak-$(date +%Y%m%d%H%M%S)'

# 2) 上传新版
scp -i "$KEY" "$LOCAL" "$SRV":/opt/agent_eval/frontend/index.html

# 3) 验证（读盘即时生效，通常无需重启）
curl -s -o /dev/null -w '%{http_code}\n' http://124.174.108.70:8000/
#   如需强制重启： ssh -i "$KEY" "$SRV" 'sudo systemctl restart agent-eval'
```

**若目录对 jennifer07 不可写**（`/opt` 常为 root 属主），中转 + sudo：

```bash
scp -i "$KEY" "$LOCAL" "$SRV":/tmp/index.html.new
ssh -i "$KEY" "$SRV" 'sudo cp /opt/agent_eval/frontend/index.html /opt/agent_eval/frontend/index.html.bak-$(date +%s) && sudo mv /tmp/index.html.new /opt/agent_eval/frontend/index.html'
```

**回滚**：把最近的 `index.html.bak-*` 覆盖回 `index.html`。

---

## 6. 本地验证 / 预览（可选）

本机 WSL 未跑该服务（线上在独立云主机）。本地预览：

```bash
cd /home/jennifer07/agent_eval && source venv/bin/activate
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8010
# 打开 http://127.0.0.1:8010/ ，点右上角 EN/中 切换；API 数据依赖 .env/DB，可能为占位
```

i18n 一致性可离线自查（示意）：把内联 `<script>` 提取为 `.js`，`node --check` 验语法；用 `new Function(src.slice(0,idx)+';return I18N;')()` 取出字典比对 `Object.keys(zh)` 与 `Object.keys(en)` 是否一致。

---

## 7. Tier 2：页头体系 + 骨架屏（2026-07-09 同一会话追加）

对比火山引擎评测平台后落地：

| 新增 | 详情 |
|---|---|
| **页头体系** | 每页 `.page-header`（eyebrow 品牌标签 + h2 标题 + p 描述），全部 data-i18n 双语；新增 brand + ph_*_title/desc 共 13 个 i18n 键 |
| **骨架屏** | `.skeleton` + shimmer 动画；qaTable（3 行）/ reportTable（3 行）/ recentReports（3 个 chips）初始加载态替换裸 "加载中…"；`loadQAData`/`loadReports`/`loadHomeData` 用 innerHTML 整体替换 tbody/#recentReports，数据到达后骨架自动消失 |

### 验证结果
- ✅ JS 语法通过；zh/en **各 99 键**对齐、零缺失、零类型不匹配
- ✅ HTML 57 个 data-i18n 键全部可在字典解析
- ✅ 6 个 page-header、6 个 data-page、9 个 skeleton
- ✅ 11 条 API 路径全在（新增 `/api/kb/search` 来自 KB 搜索控制台的外部更新，本次未改）

文件体积 `38363 → ~42500` 字节（页头 DOM + 骨架 CSS/HTML + 字典 13 新键）。

> ⚠️ 注意：KB 页面被外部更新为"搜索控制台"，内联 JS 中有**硬编码中文**（"已连接火山引擎"/"搜索失败"等），未走 t()。按你的要求不动逻辑，此行段仍显示中文，切英语后该页有混合语言。如需修复，告诉我，我补上相应的 i18n 键。

---

## 9. 两个大问题修复（同一会话追加）

### 9.1 首页两张图表真正渲染（原来是空 canvas）
- 后端本就有数据：`/api/dashboard/summary` 返回 `trend:[{ts,score}]`（近 10 次）+ `latest:{各维度均分}`；前端从未渲染。
- 新增 `renderCharts(d)`：**趋势折线**（用 `summary.trend`，倒序成时间正序）+ **维度雷达**（用 `summary.latest` 的 8 维），Chart.js 暗色主题（网格/字体色跟主题）、双语维度标签、`destroy()` 防重建报错。
- canvas 包 `.chart-box{height:200px}` 固定高度，避免 Chart.js 无限增高 bug。
- `loadHomeData` 末尾调用 `renderCharts(d)`；切语言时 `refreshActivePage()` 先 destroy 再由 loadHomeData 重绘 → 图表标签也跟着切换。
- 无数据时渲染空坐标系（不再是纯空白），不报错。

### 9.4 明/暗主题一键切换（默认浅色）
- CSS 改为**变量驱动**：`:root` 定义浅色语义 token（surface/line/text/accent/shadow/gradient…），`html[data-theme="dark"]` 覆盖为暗色一套。
- 组件规则全部改用 `var()`（133 处）+ `color-mix()`（31 处，让徽章/悬停/描边等半透明底随主题 accent 自适应），**零硬编码主题色泄漏**。
- 顶栏加 🌙/☀️ 切换按钮（`#themeToggle` → `toggleTheme()`），选择存 `localStorage['theme']`，默认浅色。
- **防闪烁**：`<head>` 内提前一行 `setAttribute('data-theme', …)`（在 CSS 加载前），刷新暗色不闪白。
- 图表 `renderCharts()` 按 `data-theme` 选网格/字体/线色，切换时 `refreshActivePage()` 重绘；live-eval 注入色改 `var(--sky/--muted/--green)` 跟随主题。
- 逻辑/API/ID 零改动，zh/en 仍各 111 键。

### 9.3 浅色主题（全量 CSS 翻版，暗→明）
- `:root` 变量全部翻为浅色系（`--bg:#f8fafc` / `--text:#1e293b` / `--line:#dce3eb` / `--shadow` 轻量化），accent 色调微调（sky → `#0ea5e9`，绿/黄/红相应加深）。
- 所有组件底色翻白（cards / table / input / select / live-eval / score-mini / skeleton）+ 玻璃态 header/nav 用白色 blur。
- 图表 `renderCharts()` 网格/字体/填充色切换为浅色主题；JS 注入内联色（`#94a3b8` → `#64748b`；`#38bdf8` → `#0ea5e9`；`#22c55e` → `#16a34a`）适配浅底可读性。
- 骨架屏动画从半透暗光 → 亮光掠过（`.skeleton::after` 用 `rgba(255,255,255,.65)`）。
- 全部逻辑/API/ID 零改动，zh/en 仍各 111 键对齐。47,282 字节。

### 9.2 KB「知识库搜索控制台」补全 i18n（原本硬编码中文）
- KB 区块此前被外部更新为搜索控制台，内联 JS/HTML 有约 15 处硬编码中文（占位符/按钮/"已连接火山引擎"/"搜索失败"/"未找到…"/"相关度"/Phase 卡片等），切英文时中英混排。
- 已全部改走字典：新增 13 个 KB i18n 键（zh/en 对齐），`loadKBStatus`/`searchKB` 用 `t()`；静态占位符/按钮/卡片加 `data-i18n`/`data-i18n-ph`。

### 验证
- ✅ JS 语法通过；zh/en **各 111 键**对齐、零缺失、零类型不匹配
- ✅ 61 个 data-i18n 键全部可解析；2 个 chart-box；6 页头/6 data-page
- ✅ 11 条 API 路径原样（图表复用已有 `/api/dashboard/summary`，未新增后端）

文件体积 `~42500 → 约 48KB`（图表逻辑 + KB i18n + 13 键）。

> 说明：`renderCharts` 只是新增读取已有 summary 字段并画图，**未改任何后端/API/数据流**；KB 修复只做文案 i18n，逻辑不变。上线后建议冒烟：首页看两图是否出现、切 EN 看图表标签与 KB 页是否全英文。

---

## 10. 仍待办（需后端 API）
- **报告详情页**（Tier 1 最大项）：点报告行进详情——概览 + 维度图 + 分数分布 + 样本级明细 + CSV 导出
- **评测创建向导**（画像×课时×轮次×维度权重）
- **裁判透明化**（各维度评语 / 规则 vs LLM-Judge 拆分）
- 可选纯外观：明/暗主题切换、空状态插画
