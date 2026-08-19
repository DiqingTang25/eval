import { Icons } from "@/components/icons";
import { HomeIcon, NotebookIcon, FileText } from "lucide-react";
import { ReactLight } from "@/components/ui/svgs/reactLight";
import { NextjsIconDark } from "@/components/ui/svgs/nextjsIconDark";
import { Typescript } from "@/components/ui/svgs/typescript";
import { Nodejs } from "@/components/ui/svgs/nodejs";
import { Python } from "@/components/ui/svgs/python";
import { Docker } from "@/components/ui/svgs/docker";
import { Postgresql } from "@/components/ui/svgs/postgresql";
import type { ComponentType, ReactNode } from "react";

export const GITHUB_REPO = "https://github.com/DiqingTang25/eval";
export const LIVE_SYSTEM = "http://124.174.108.70/test/";
export const PRD_URL = "/prd.html";

export interface Social {
  name: string;
  url: string;
  icon: ComponentType<{ className?: string }>;
  navbar: boolean;
}

export interface WorkItem {
  company: string;
  href: string;
  badges: string[];
  location: string;
  title: string;
  logoUrl: string;
  start: string;
  end: string;
  description: string;
}

export interface EducationItem {
  school: string;
  href: string;
  degree: string;
  logoUrl: string;
  start: string;
  end: string;
}

export interface ProjectItem {
  title: string;
  href: string;
  dates: string;
  active: boolean;
  description: string;
  technologies: string[];
  links: { type: string; href: string; icon: ReactNode }[];
  image: string;
  video: string;
}

export interface AchievementItem {
  title: string;
  dates: string;
  location: string;
  description: string;
  image: string;
  win?: string;
  links: { title: string; icon: ReactNode; href: string }[];
}

export interface ResumeData {
  name: string;
  initials: string;
  url: string;
  location: string;
  locationLink: string;
  description: string;
  summary: string;
  avatarUrl: string;
  hero: {
    badge: string;
    title: string;
    subtitle: string;
    stats: { value: string; label: string }[];
  };
  skills: { name: string; icon?: ComponentType<{ className?: string }> }[];
  navbar: { href: string; icon: ComponentType<{ className?: string }>; label: string }[];
  contact: {
    email: string;
    tel: string;
    social: Record<string, Social>;
  };
  work: WorkItem[];
  education: EducationItem[];
  projects: ProjectItem[];
  achievements: AchievementItem[];
}

const sharedNavbar = [
  { href: "/", icon: HomeIcon },
  { href: "/blog", icon: NotebookIcon },
  { href: PRD_URL, icon: FileText },
];

const githubLinkIcon = <Icons.github className="size-3" />;
const globeLinkIcon = <Icons.globe className="size-3" />;
const docLinkIcon = <FileText className="size-3" />;

const sharedContactSocial: Record<string, Social> = {
  GitHub: {
    name: "GitHub",
    url: GITHUB_REPO,
    icon: Icons.github,
    navbar: true,
  },
  LiveSystem: {
    name: "在线系统 / Live System",
    url: LIVE_SYSTEM,
    icon: Icons.globe,
    navbar: true,
  },
  PRD: {
    name: "产品需求文档 / PRD",
    url: PRD_URL,
    icon: FileText,
    navbar: true,
  },
  email: {
    name: "发送邮件 / Send Email",
    url: "mailto:DiqingTang25@users.noreply.github.com",
    icon: Icons.email,
    navbar: false,
  },
};

export const RESUME: Record<"zh" | "en", ResumeData> = {
  zh: {
    name: "AI Agent 全自动化测评系统",
    initials: "AE",
    url: "https://github.com/DiqingTang25/eval",
    location: "西交利物浦大学 · AI+X 实训教学平台",
    locationLink: "https://www.xjtlu.edu.cn",
    description:
      "面向 AI 教学助手的全自动化测评平台：Playwright 操控被测 Agent → LLM 生成多画像测试问题 → 多轮追问 → 三层级联评分（规则 + 算法 + 多 Judge 投票）→ 边界合规检测 → 证据链 SHA-256 封存 → 可视化报告。三个月 7.3 万行代码、42 次提交，交付生产环境。",
    summary:
      "AI 教学助手承担着西交利物浦大学 AI+X 实训平台的答疑工作，但其回答质量此前缺乏系统性保障。本项目在三个月内从 0 构建了完整的自动化测评体系：\n\n" +
      "- **数据采集层**：五层平台探索器（认证检测 → 流量捕获 → 结构推断 → API 分类 → Schema 生成）+ Playwright 浏览器操控被测 Agent\n" +
      "- **智能分析层**：10 维度评分体系（对齐 CLEAR / TEACH-AI / EduAgentBench 等学术框架），L1 规则 30% + L2 算法 10% + L3 三 Judge 投票 60%，95% 置信区间 + 变异系数校准\n" +
      "- **应用层**：10 页双语 SPA 面板、WebSocket 实时推送、对话式卡点干预、自演化引擎、零门槛向导\n\n" +
      "开发采用**双 Claude Code Agent 协同工作流**——Agent A 负责前端与测评引擎，Agent B 负责平台探索器，通过同步文档规范接口并行推进。成果已部署至云服务器（systemd + Nginx），覆盖 22 门课程、110 个教学步骤、33 个 API 端点。",
    avatarUrl: "/logo.svg",
    hero: {
      badge: "v3.6 · 生产环境运行中",
      title: "AI Agent 全自动化测评系统",
      subtitle:
        "浏览器操控被测 Agent → LLM 生成多画像问题 → 多轮追问 → 10 维度三层级联评分 → 证据链封存 → 可视化报告",
      stats: [
        { value: "3 个月", label: "开发周期" },
        { value: "73K+", label: "行代码" },
        { value: "42", label: "Commits" },
        { value: "688", label: "双语 i18n 键" },
        { value: "88%", label: "平台健康度" },
        { value: "22+110", label: "课程 / 教学步骤" },
      ],
    },
    skills: [
      { name: "Python", icon: Python },
      { name: "FastAPI" },
      { name: "Playwright" },
      { name: "Next.js", icon: NextjsIconDark },
      { name: "React", icon: ReactLight },
      { name: "TypeScript", icon: Typescript },
      { name: "TailwindCSS" },
      { name: "Chart.js" },
      { name: "Node.js", icon: Nodejs },
      { name: "Docker", icon: Docker },
      { name: "MySQL" },
      { name: "Redis" },
      { name: "PostgreSQL", icon: Postgresql },
      { name: "LLM Judge · DeepSeek/GLM/Doubao" },
      { name: "Nginx" },
      { name: "GitHub Actions" },
      { name: "systemd" },
    ],
    navbar: [
      { ...sharedNavbar[0], label: "首页" },
      { ...sharedNavbar[1], label: "博客" },
      { ...sharedNavbar[2], label: "PRD" },
    ],
    contact: {
      email: "DiqingTang25@users.noreply.github.com",
      tel: "",
      social: sharedContactSocial,
    },
    work: [
      {
        company: "基础系统与数据采集层",
        href: GITHUB_REPO,
        badges: ["Phase 0"],
        location: "2026.06",
        title: "v3.0 · 从 0 起步",
        logoUrl: "",
        start: "2026.06",
        end: "2026.06",
        description:
          "FastAPI 后端骨架 + Playwright 浏览器操控被测 Agent + 黄金 QA 库分层抽样 + L1 规则引擎（结构完整性 / 事实锚点 / SLA 性能 / 安全合规）",
      },
      {
        company: "评分体系 v3.4 → v3.5",
        href: GITHUB_REPO,
        badges: ["8维 → 10维", "校准"],
        location: "2026.07 上旬",
        title: "可信度与稳定性",
        logoUrl: "",
        start: "2026.07",
        end: "2026.07",
        description:
          "新增过度帮助检测与公平性审计两个维度；置信度校准（95% CI + 变异系数 + A/B/C 可靠性分级）；Watchdog 三层超时保护；Prompt SHA-256 版本管理；A/B 对比框架（维度级 delta + Cohen's d）",
      },
      {
        company: "白皮书 v3.6 与平台交互测评",
        href: GITHUB_REPO,
        badges: ["逆向分析"],
        location: "2026.07.16",
        title: "24.7 万字符 SPA 逆向",
        logoUrl: "",
        start: "2026.07",
        end: "2026.07",
        description:
          "逆向分析平台前端 JS 后发现双 API 前缀架构（/api vs /phase3-api）与独立 JWT 密钥；13 项交互功能全量测试（健康度 88%）；Quiz 测评体系（5 Phase × 45 题，结构完整率 100%）",
      },
      {
        company: "平台探索与前端重构",
        href: GITHUB_REPO,
        badges: ["五层探索器", "双 AI 协同"],
        location: "2026.07.29 – 08.05",
        title: "探索器 L0-L4 + 双语 SPA",
        logoUrl: "",
        start: "2026.07",
        end: "2026.08",
        description:
          "五层探索器自动生成平台 Schema 驱动测评；10 页 SPA 重构 + 591 键双语 i18n + WebSocket 实时推送；建立双 Claude Code Agent 分工与同步文档协作工作流",
      },
      {
        company: "全平台实测报告",
        href: GITHUB_REPO,
        badges: ["真实数据"],
        location: "2026.08.12",
        title: "22 课程 · 110 步骤 · 33 API",
        logoUrl: "",
        start: "2026.08",
        end: "2026.08",
        description:
          "全量采集 22 门课程内容与 17 门课 Agent 对话 DOM，8 门课 LLM Judge 正式评分；发现 AI 类课程 Agent 空响应与 UI 文本泄漏等关键质量问题，综合得分 4.8/10",
      },
      {
        company: "五阶段迭代：自演化 + 零门槛",
        href: GITHUB_REPO,
        badges: ["最终形态"],
        location: "2026.08.19",
        title: "v3.6 · 交付生产",
        logoUrl: "",
        start: "2026.08",
        end: "至今",
        description:
          "对话式探索器 v2（计划确认卡 / 凭证脱敏）；报错 → LLM 六要素求助卡干预；自演化引擎（经验记忆 + 快路径 + 运行指标）；首访四步向导 + 688 键 i18n；L0 登录假成功修复（探索 0 → 28 phases，置信度 0.77）",
      },
    ],
    education: [
      {
        school: "西交利物浦大学",
        href: "https://www.xjtlu.edu.cn",
        degree: "AI+X 实训教学平台 · AI 助教质量保障项目",
        logoUrl: "",
        start: "2026.06",
        end: "2026.08",
      },
      {
        school: "Open Source · GitHub",
        href: GITHUB_REPO,
        degree: "github.com/DiqingTang25/eval · 42 commits · CI 五级流水线",
        logoUrl: "",
        start: "2026.08",
        end: "至今",
      },
      {
        school: "生产部署",
        href: LIVE_SYSTEM,
        degree: "systemd + Nginx · 云端运行中 · /test/",
        logoUrl: "",
        start: "2026.08",
        end: "至今",
      },
    ],
    projects: [
      {
        title: "五层平台探索器",
        href: GITHUB_REPO + "/tree/main/src/platform_probe",
        dates: "2026.07 – 2026.08",
        active: true,
        description:
          "认证检测 → 流量拦截 + BFS 遍历 → 教学结构推断 → API 分类 → Schema 生成。逆向发现双 API 前缀架构，凭证全程脱敏，修复后单平台探索 **0 → 28 phases，置信度 0.77**。",
        technologies: ["Python", "Playwright", "LLM", "FastAPI"],
        links: [
          { type: "Source", href: GITHUB_REPO + "/tree/main/src/platform_probe", icon: githubLinkIcon },
          { type: "架构文档", href: GITHUB_REPO + "/blob/main/docs/ARCHITECTURE_PX.md", icon: docLinkIcon },
        ],
        image: "",
        video: "",
      },
      {
        title: "三层级联评分引擎",
        href: GITHUB_REPO + "/tree/main/src",
        dates: "2026.06 – 2026.08",
        active: true,
        description:
          "L1 规则 30%（一票否决 + 高分跳过）+ L2 算法 10%（Embedding 相似度 + 关键词覆盖）+ L3 三 Judge 投票 60%（跨模型族、方差量化、人工复核标记）。**10 维度** + 95% CI / CV 置信度校准。",
        technologies: ["Python", "DeepSeek", "GLM-5.2", "Doubao"],
        links: [
          { type: "Source", href: GITHUB_REPO + "/blob/main/src/evaluator.py", icon: githubLinkIcon },
          { type: "白皮书", href: GITHUB_REPO + "/blob/main/docs/whitepaper_v3.6.md", icon: docLinkIcon },
        ],
        image: "",
        video: "",
      },
      {
        title: "对话式卡点干预",
        href: GITHUB_REPO + "/blob/main/backend/services/error_interpreter.py",
        dates: "2026.08",
        active: true,
        description:
          "评测卡点 → LLM 生成六要素求助卡（无 key 时降级 8 类模板）；风险分级超时（low 120s / mid 300s / high 600s）；QuestionBridge 问答接线；强制求助与防骚扰（同类最多问 2 次）。",
        technologies: ["Python", "LLM", "WebSocket"],
        links: [
          { type: "Source", href: GITHUB_REPO + "/blob/main/backend/services/error_interpreter.py", icon: githubLinkIcon },
        ],
        image: "",
        video: "",
      },
      {
        title: "自演化引擎",
        href: GITHUB_REPO + "/blob/main/src/experience_store.py",
        dates: "2026.08",
        active: true,
        description:
          "平台画像库（URL 指纹归档，换平台不丢历史）+ 失败反思 JSONL 经验记忆 + 成功路径固化（先重放后 AI）+ 退出类型四分类，成功率 / 求助率看板——**用得越多，测得越准**。",
        technologies: ["Python", "JSONL", "FastAPI"],
        links: [
          { type: "Source", href: GITHUB_REPO + "/blob/main/src/experience_store.py", icon: githubLinkIcon },
          { type: "指标 API", href: GITHUB_REPO + "/blob/main/src/run_metrics.py", icon: docLinkIcon },
        ],
        image: "",
        video: "",
      },
      {
        title: "双语评测面板 SPA",
        href: GITHUB_REPO + "/tree/main/frontend",
        dates: "2026.07 – 2026.08",
        active: true,
        description:
          "10 个页面（Dashboard / Explorer / Test Runner / Reports / Calibration / Platform Health / Web Eval / QA / KB / Report Viewer），**688 键中英双语**、WebSocket 实时日志、Chart.js 可视化。",
        technologies: ["Vanilla JS", "Chart.js", "i18n", "WebSocket"],
        links: [
          { type: "Source", href: GITHUB_REPO + "/tree/main/frontend", icon: githubLinkIcon },
          { type: "在线系统", href: LIVE_SYSTEM, icon: globeLinkIcon },
        ],
        image: "",
        video: "",
      },
      {
        title: "零门槛向导与 CI/CD",
        href: GITHUB_REPO + "/tree/main/deploy",
        dates: "2026.08",
        active: true,
        description:
          "首访四步向导 + `env_check.sh` 部署体检（DB 默认 SQLite）；GitHub Actions 五级流水线（语法 → 单测 → 内容校验 → 冒烟 → 全量）；systemd + Nginx 生产部署，rsync 一键同步。",
        technologies: ["GitHub Actions", "Docker", "systemd", "Nginx"],
        links: [
          { type: "Deploy", href: GITHUB_REPO + "/tree/main/deploy", icon: githubLinkIcon },
          { type: "用户手册", href: GITHUB_REPO + "/blob/main/docs/用户手册.md", icon: docLinkIcon },
        ],
        image: "",
        video: "",
      },
    ],
    achievements: [
      {
        title: "全平台评测报告",
        dates: "2026.08.12",
        location: "22 门课程 · 110 步骤 · 33 API",
        description:
          "8 门代表课程 LLM Judge 正式评分：硬件模块 8.2 优秀 / 具身交互 4.6 中等 / AI 类 1.5 严重（空响应、UI 文本泄漏）。关键发现直接反馈给平台团队，综合得分 4.8/10。",
        image: "/logo.svg",
        links: [
          {
            title: "报告",
            icon: <Icons.github className="h-4 w-4" />,
            href: GITHUB_REPO + "/blob/main/reports/final_evaluation_report_20260812.md",
          },
        ],
      },
      {
        title: "探索成功率修复",
        dates: "2026.08.19",
        location: "L0 登录假成功 → 反例检测",
        description:
          "登录模态框关闭被误判为登录成功，导致后续测评以未登录态白跑（0 phases）。加入反例检测（页面仍可见登录按钮 = 未登录）+ 强制求助升级后，同一平台探索 0 → 28 phases，置信度 0.77，认证状态 30B → 1260B。",
        image: "/logo.svg",
        win: "0 → 28 phases",
        links: [
          {
            title: "Commit",
            icon: <Icons.github className="h-4 w-4" />,
            href: GITHUB_REPO + "/commit/5f7b5f6",
          },
        ],
      },
      {
        title: "平台交互健康度 88%",
        dates: "2026.07.16",
        location: "13 项交互功能全量测试",
        description:
          "Quiz 启动/提交、Agent 对话、步骤进度、学生画像（6 维雷达图）、知识搜索等 13 项功能逐一真实端点验证：11 working / 1 degraded / 1 broken。Quiz 45 题结构完整率 100%。",
        image: "/logo.svg",
        win: "11/13 working",
        links: [
          {
            title: "白皮书 §5",
            icon: <Icons.github className="h-4 w-4" />,
            href: GITHUB_REPO + "/blob/main/docs/whitepaper_v3.6.md",
          },
        ],
      },
      {
        title: "评测标准白皮书 v3.6",
        dates: "2026.07.16",
        location: "产业级交付标准",
        description:
          "对齐 CLEAR / TEACH-AI / EduAgentBench / PEBBLE 等学术评测框架；10 维 Agent 测评 + 7 维 Web 测评 + 13 项平台交互测评；可复现 / 可解释 / 可审计 / 可校准 / 可对比五大可信性标准。",
        image: "/logo.svg",
        links: [
          {
            title: "白皮书",
            icon: <Icons.github className="h-4 w-4" />,
            href: GITHUB_REPO + "/blob/main/docs/whitepaper_v3.6.md",
          },
        ],
      },
    ],
  },

  en: {
    name: "AI Agent Evaluation Platform",
    initials: "AE",
    url: "https://github.com/DiqingTang25/eval",
    location: "XJTLU · AI+X Training Platform",
    locationLink: "https://www.xjtlu.edu.cn",
    description:
      "A fully-automated evaluation platform for AI teaching assistants: browser-controlled agent interaction → LLM-generated persona tests → multi-turn probing → 3-tier cascaded scoring (rules + algorithms + multi-judge voting) → boundary compliance → SHA-256 evidence chains → visual reports. 73K+ lines of code and 42 commits, shipped to production in 3 months.",
    summary:
      "The AI teaching assistant (HiAgent) handles Q&A for XJTLU's AI+X training platform, but its answer quality previously had no systematic guarantee. This project built a complete automated evaluation system from zero in three months:\n\n" +
      "- **Data collection layer**: a five-layer platform explorer (auth detection → traffic capture → structure inference → API classification → schema generation) plus Playwright-driven browser control of the agent under test\n" +
      "- **Intelligent analysis layer**: a 10-dimension scoring system (aligned with CLEAR / TEACH-AI / EduAgentBench), L1 rules 30% + L2 algorithms 10% + L3 three-judge voting 60%, calibrated with 95% confidence intervals and coefficient of variation\n" +
      "- **Application layer**: a 10-page bilingual SPA dashboard, WebSocket real-time streaming, conversational stuck-point intervention, a self-evolving engine, and a zero-barrier onboarding wizard\n\n" +
      "Development used a **dual Claude Code agent workflow** — Agent A owned the frontend and evaluation engine, Agent B owned the platform explorer, coordinating through sync documents. The system runs in production (systemd + Nginx), covering 22 courses, 110 teaching steps and 33 API endpoints.",
    avatarUrl: "/logo.svg",
    hero: {
      badge: "v3.6 · Live in production",
      title: "AI Agent Evaluation Platform",
      subtitle:
        "Browser-controlled agent testing → persona-driven questions → multi-turn probing → 10-dimension cascaded scoring → evidence sealing → visual reports",
      stats: [
        { value: "3 mo", label: "Build time" },
        { value: "73K+", label: "Lines of code" },
        { value: "42", label: "Commits" },
        { value: "688", label: "i18n keys" },
        { value: "88%", label: "Platform health" },
        { value: "22+110", label: "Courses / steps" },
      ],
    },
    skills: [
      { name: "Python", icon: Python },
      { name: "FastAPI" },
      { name: "Playwright" },
      { name: "Next.js", icon: NextjsIconDark },
      { name: "React", icon: ReactLight },
      { name: "TypeScript", icon: Typescript },
      { name: "TailwindCSS" },
      { name: "Chart.js" },
      { name: "Node.js", icon: Nodejs },
      { name: "Docker", icon: Docker },
      { name: "MySQL" },
      { name: "Redis" },
      { name: "PostgreSQL", icon: Postgresql },
      { name: "LLM Judge · DeepSeek/GLM/Doubao" },
      { name: "Nginx" },
      { name: "GitHub Actions" },
      { name: "systemd" },
    ],
    navbar: [
      { ...sharedNavbar[0], label: "Home" },
      { ...sharedNavbar[1], label: "Blog" },
      { ...sharedNavbar[2], label: "PRD" },
    ],
    contact: {
      email: "DiqingTang25@users.noreply.github.com",
      tel: "",
      social: sharedContactSocial,
    },
    work: [
      {
        company: "Foundation & Data Collection",
        href: GITHUB_REPO,
        badges: ["Phase 0"],
        location: "2026.06",
        title: "v3.0 · From zero",
        logoUrl: "",
        start: "2026.06",
        end: "2026.06",
        description:
          "FastAPI backend + Playwright browser control of the agent under test + golden QA bank stratified sampling + L1 rule engine (structure / fact anchors / SLA / safety)",
      },
      {
        company: "Scoring System v3.4 → v3.5",
        href: GITHUB_REPO,
        badges: ["8→10 dims", "Calibration"],
        location: "Early Jul 2026",
        title: "Trust & stability",
        logoUrl: "",
        start: "2026.07",
        end: "2026.07",
        description:
          "Added over-helping detection and fairness audit dimensions; confidence calibration (95% CI + CV + A/B/C reliability grades); Watchdog 3-tier timeout protection; prompt SHA-256 versioning; A/B comparison framework (per-dimension delta + Cohen's d)",
      },
      {
        company: "Whitepaper v3.6 & Platform Interaction Eval",
        href: GITHUB_REPO,
        badges: ["Reverse engineering"],
        location: "2026.07.16",
        title: "247K-char SPA reverse analysis",
        logoUrl: "",
        start: "2026.07",
        end: "2026.07",
        description:
          "Reverse-engineered the platform frontend JS and discovered a dual API-prefix architecture (/api vs /phase3-api) with independent JWT keys; full testing of 13 interaction features (health 88%); Quiz evaluation system (5 phases × 45 questions, 100% structural integrity)",
      },
      {
        company: "Platform Exploration & Frontend Rebuild",
        href: GITHUB_REPO,
        badges: ["5-layer explorer", "Dual-AI"],
        location: "2026.07.29 – 08.05",
        title: "Explorer L0-L4 + bilingual SPA",
        logoUrl: "",
        start: "2026.07",
        end: "2026.08",
        description:
          "Five-layer explorer auto-generates platform schemas that drive evaluation; 10-page SPA rebuild + 591-key bilingual i18n + WebSocket real-time streaming; established a dual Claude Code agent workflow with sync documents",
      },
      {
        company: "Full-Platform Evaluation Report",
        href: GITHUB_REPO,
        badges: ["Real data"],
        location: "2026.08.12",
        title: "22 courses · 110 steps · 33 APIs",
        logoUrl: "",
        start: "2026.08",
        end: "2026.08",
        description:
          "Collected full content of 22 courses and agent-conversation DOM of 17 courses; formal LLM-judge scoring of 8 courses; surfaced critical quality issues such as empty responses and UI-text leakage in AI-module agents; overall 4.8/10",
      },
      {
        company: "Five-Stage Iteration: Self-Evolving + Zero-Barrier",
        href: GITHUB_REPO,
        badges: ["Final form"],
        location: "2026.08.19",
        title: "v3.6 · Shipped",
        logoUrl: "",
        start: "2026.08",
        end: "Present",
        description:
          "Conversational explorer v2 (plan confirmation cards / credential redaction); error → LLM six-element help cards; self-evolving engine (experience memory + fast paths + run metrics); first-visit 4-step wizard + 688-key i18n; L0 false-login fix (exploration 0 → 28 phases, confidence 0.77)",
      },
    ],
    education: [
      {
        school: "Xi'an Jiaotong-Liverpool University",
        href: "https://www.xjtlu.edu.cn",
        degree: "AI+X Training Platform · AI Tutor Quality Assurance Project",
        logoUrl: "",
        start: "2026.06",
        end: "2026.08",
      },
      {
        school: "Open Source · GitHub",
        href: GITHUB_REPO,
        degree: "github.com/DiqingTang25/eval · 42 commits · 5-stage CI pipeline",
        logoUrl: "",
        start: "2026.08",
        end: "Present",
      },
      {
        school: "Production Deployment",
        href: LIVE_SYSTEM,
        degree: "systemd + Nginx · Live in the cloud · /test/",
        logoUrl: "",
        start: "2026.08",
        end: "Present",
      },
    ],
    projects: [
      {
        title: "Five-Layer Platform Explorer",
        href: GITHUB_REPO + "/tree/main/src/platform_probe",
        dates: "2026.07 – 2026.08",
        active: true,
        description:
          "Auth detection → traffic interception + BFS → structure inference → API classification → schema generation. Reverse-engineered the dual API-prefix architecture; full credential redaction; **0 → 28 phases, confidence 0.77** after the login fix.",
        technologies: ["Python", "Playwright", "LLM", "FastAPI"],
        links: [
          { type: "Source", href: GITHUB_REPO + "/tree/main/src/platform_probe", icon: githubLinkIcon },
          { type: "Architecture", href: GITHUB_REPO + "/blob/main/docs/ARCHITECTURE_PX.md", icon: docLinkIcon },
        ],
        image: "",
        video: "",
      },
      {
        title: "3-Tier Cascaded Scoring Engine",
        href: GITHUB_REPO + "/tree/main/src",
        dates: "2026.06 – 2026.08",
        active: true,
        description:
          "L1 rules 30% (veto + high-score skip) + L2 algorithms 10% (embedding similarity + keyword coverage) + L3 three-judge voting 60% (cross-model-family, variance-quantified, manual-review flags). **10 dimensions** + 95% CI / CV calibration.",
        technologies: ["Python", "DeepSeek", "GLM-5.2", "Doubao"],
        links: [
          { type: "Source", href: GITHUB_REPO + "/blob/main/src/evaluator.py", icon: githubLinkIcon },
          { type: "Whitepaper", href: GITHUB_REPO + "/blob/main/docs/whitepaper_v3.6.md", icon: docLinkIcon },
        ],
        image: "",
        video: "",
      },
      {
        title: "Conversational Stuck-Point Intervention",
        href: GITHUB_REPO + "/blob/main/backend/services/error_interpreter.py",
        dates: "2026.08",
        active: true,
        description:
          "Eval stuck-points → LLM-generated six-element help cards (8 template fallbacks without a key); risk-tiered timeouts (low 120s / mid 300s / high 600s); QuestionBridge Q&A wiring; forced help requests with anti-harassment limits (max 2 per category).",
        technologies: ["Python", "LLM", "WebSocket"],
        links: [
          { type: "Source", href: GITHUB_REPO + "/blob/main/backend/services/error_interpreter.py", icon: githubLinkIcon },
        ],
        image: "",
        video: "",
      },
      {
        title: "Self-Evolving Engine",
        href: GITHUB_REPO + "/blob/main/src/experience_store.py",
        dates: "2026.08",
        active: true,
        description:
          "Platform profile library (URL fingerprinting, history survives platform switches) + JSONL failure reflection memory + successful-path caching (replay before AI) + 4-way exit-type classification with success/help-rate dashboards — **the more it runs, the better it evaluates**.",
        technologies: ["Python", "JSONL", "FastAPI"],
        links: [
          { type: "Source", href: GITHUB_REPO + "/blob/main/src/experience_store.py", icon: githubLinkIcon },
          { type: "Metrics API", href: GITHUB_REPO + "/blob/main/src/run_metrics.py", icon: docLinkIcon },
        ],
        image: "",
        video: "",
      },
      {
        title: "Bilingual Evaluation Dashboard SPA",
        href: GITHUB_REPO + "/tree/main/frontend",
        dates: "2026.07 – 2026.08",
        active: true,
        description:
          "10 pages (Dashboard / Explorer / Test Runner / Reports / Calibration / Platform Health / Web Eval / QA / KB / Report Viewer), **688-key zh/en i18n**, WebSocket real-time logs, Chart.js visualizations.",
        technologies: ["Vanilla JS", "Chart.js", "i18n", "WebSocket"],
        links: [
          { type: "Source", href: GITHUB_REPO + "/tree/main/frontend", icon: githubLinkIcon },
          { type: "Live", href: LIVE_SYSTEM, icon: globeLinkIcon },
        ],
        image: "",
        video: "",
      },
      {
        title: "Zero-Barrier Onboarding & CI/CD",
        href: GITHUB_REPO + "/tree/main/deploy",
        dates: "2026.08",
        active: true,
        description:
          "First-visit 4-step wizard + `env_check.sh` deployment health check (SQLite by default); GitHub Actions 5-stage pipeline (syntax → unit → content validation → smoke → full); systemd + Nginx production deployment with one-command rsync sync.",
        technologies: ["GitHub Actions", "Docker", "systemd", "Nginx"],
        links: [
          { type: "Deploy", href: GITHUB_REPO + "/tree/main/deploy", icon: githubLinkIcon },
          { type: "Manual", href: GITHUB_REPO + "/blob/main/docs/用户手册.md", icon: docLinkIcon },
        ],
        image: "",
        video: "",
      },
    ],
    achievements: [
      {
        title: "Full-Platform Evaluation Report",
        dates: "2026.08.12",
        location: "22 courses · 110 steps · 33 APIs",
        description:
          "Formal LLM-judge scoring on 8 representative courses: hardware module 8.2 excellent / embodied projects 4.6 fair / AI module 1.5 severe (empty responses, UI-text leakage). Findings were fed back to the platform team; overall 4.8/10.",
        image: "/logo.svg",
        links: [
          {
            title: "Report",
            icon: <Icons.github className="h-4 w-4" />,
            href: GITHUB_REPO + "/blob/main/reports/final_evaluation_report_20260812.md",
          },
        ],
      },
      {
        title: "Exploration Success-Rate Fix",
        dates: "2026.08.19",
        location: "L0 false-login → counter-example detection",
        description:
          "Login-modal dismissal was misjudged as successful login, causing downstream evaluation to run logged-out (0 phases). Counter-example detection (login button still visible = not logged in) + forced help escalation took the same platform from 0 → 28 phases, confidence 0.77, auth state 30B → 1260B.",
        image: "/logo.svg",
        win: "0 → 28 phases",
        links: [
          {
            title: "Commit",
            icon: <Icons.github className="h-4 w-4" />,
            href: GITHUB_REPO + "/commit/5f7b5f6",
          },
        ],
      },
      {
        title: "Platform Interaction Health 88%",
        dates: "2026.07.16",
        location: "13 interaction features fully tested",
        description:
          "Quiz start/submit, agent chat, step progress, student profile (6-dimension radar), knowledge search and more — every feature verified against real endpoints: 11 working / 1 degraded / 1 broken. Quiz integrity 100% across 45 questions.",
        image: "/logo.svg",
        win: "11/13 working",
        links: [
          {
            title: "Whitepaper §5",
            icon: <Icons.github className="h-4 w-4" />,
            href: GITHUB_REPO + "/blob/main/docs/whitepaper_v3.6.md",
          },
        ],
      },
      {
        title: "Evaluation Whitepaper v3.6",
        dates: "2026.07.16",
        location: "Industry-grade delivery standard",
        description:
          "Aligned with CLEAR / TEACH-AI / EduAgentBench / PEBBLE academic frameworks; 10-dimension agent eval + 7-dimension web eval + 13-feature interaction eval; reproducible / explainable / auditable / calibratable / comparable.",
        image: "/logo.svg",
        links: [
          {
            title: "Whitepaper",
            icon: <Icons.github className="h-4 w-4" />,
            href: GITHUB_REPO + "/blob/main/docs/whitepaper_v3.6.md",
          },
        ],
      },
    ],
  },
};

// 静态站点信息（供服务端 metadata / OG 图片 / 博客页使用，不含语言相关文案）
export const SITE = {
  name: "AI Agent 全自动化测评系统",
  enName: "AI Agent Evaluation Platform",
  url: "https://github.com/DiqingTang25/eval",
  description: RESUME.zh.description,
  avatarUrl: "/logo.svg",
};

// 兼容旧引用（博客页与 OG 图片仅使用静态字段）
export const DATA = SITE;
