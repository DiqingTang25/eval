# 🎨 Portfolio — AI Agent 全自动化测评系统作品集

基于 [Magic UI Portfolio](https://github.com/magicuidesign/portfolio) 模板（Next.js 16 · React 19 · Tailwind CSS 4 · Motion）定制的项目作品集网站，内置**中英双语切换**、明暗主题切换与**完整 PRD 文档页**（`/prd.html`）。

- **在线预览**：本地 `npm run dev` → http://localhost:3000
- **PRD 文档**：`public/prd.html`（作品集内链接 `/prd.html`）
- **关联仓库**：https://github.com/DiqingTang25/eval

## 页面结构

| 区块 | 内容 |
|------|------|
| Hero | 项目名 + 关键数据看板（3 个月 / 73K 行 / 42 commits / 688 i18n） |
| About | 项目背景 + 双 Claude Code Agent 协同开发方式 |
| Milestones | 6 月 → 8 月六个月里程碑（可折叠时间线） |
| Core Modules | 六大核心模块卡片（探索器 / 评分引擎 / 干预 / 自演化 / 面板 / CI-CD） |
| Results | 四项关键评测成果（真实数据 + 证据链接） |
| Blog | 3 篇深度技术解析（三层级联 / 探索器 / 自演化） |
| Contact | GitHub / PRD / 在线系统入口 |

## 本地开发

```bash
cd portfolio
npm install        # 首次
npm run dev        # 开发服务器 → http://localhost:3000
npm run build      # 生产构建
npm run start      # 本地运行生产构建
```

## 🚀 部署到 Vercel（推荐）

> 前提：仓库已推送到 GitHub（portfolio/ 目录随主仓库一起）。

1. 打开 https://vercel.com/new 并登录（可用 GitHub 账号直接登录）
2. **Import Git Repository** → 选择 `DiqingTang25/eval`
3. 在导入配置页找到 **Root Directory** 字段，填 `portfolio`（关键步骤！）
4. Framework Preset 会自动识别为 **Next.js**，其余保持默认
5. 点击 **Deploy**，约 1-2 分钟完成
6. 部署完成后可获得 `https://<项目名>.vercel.app` 域名，可在 Settings → Domains 绑定自定义域名

> 说明：Vercel 默认 Build Command `npm run build`，无需任何环境变量。`public/prd.html` 会随站点一起发布到 `/prd.html`。

### 备选：本地构建 + Vercel CLI

```bash
npm i -g vercel
vercel login
cd portfolio
vercel --prod
```

## ✏️ 自定义内容

所有文案集中在两个文件，修改无需动组件代码：

- **`src/data/resume.tsx`** — 全部双语内容（Hero / 里程碑 / 模块 / 成果 / 技术栈 / 链接）。`zh` 与 `en` 两个对象一一对应，改完两个都改。
- **`src/lib/i18n.tsx`** — 界面固定文案（导航 tooltip、章节标题等）的双语字典。

其他可改项：

- **Logo**：`public/logo.svg`（同时用于头像与 OG 图）
- **博客**：`content/*.mdx`（frontmatter 需含 `title` / `publishedAt` / `summary`）
- **PRD**：`public/prd.html`（独立 HTML，可直接编辑）
- **个人信息**：`src/data/resume.tsx` 中的 `location`、`contact.email` 等字段

## 技术栈

Next.js 16 · React 19 · Tailwind CSS 4 · Magic UI 组件（BlurFade / Dock / FlickeringGrid / Timeline）· content-collections · motion

---

基于 [magicuidesign/portfolio](https://github.com/magicuidesign/portfolio)（MIT License）二次开发。
