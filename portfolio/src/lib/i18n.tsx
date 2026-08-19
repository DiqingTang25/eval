"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { RESUME, type ResumeData } from "@/data/resume";

export type Lang = "zh" | "en";

const UI_STRINGS: Record<Lang, Record<string, string>> = {
  zh: {
    "nav.home": "首页",
    "nav.blog": "博客",
    "nav.prd": "产品需求文档 PRD",
    "nav.github": "GitHub 仓库",
    "nav.live": "在线系统",
    "nav.theme": "主题",
    "nav.lang": "切换语言",

    "section.about": "关于项目",
    "section.work": "项目里程碑",
    "section.education": "项目信息",
    "section.skills": "技术栈",
    "section.projects": "核心模块",
    "section.projects.subtitle":
      "三个月内从 0 到生产环境的完整系统。以下是六大核心模块，全部代码开源于 GitHub。",
    "section.achievements": "评测成果",
    "section.achievements.subtitle":
      "平台真实评测数据与关键工程成果——所有数据均可溯源，证据链 SHA-256 封存。",
    "section.contact": "联系与链接",
    "contact.title": "一起聊一聊",
    "contact.description":
      "项目完全开源在 GitHub，欢迎 Star / Issue / Pull Request；完整的产品需求文档见 PRD；系统正在云端运行。",
  },
  en: {
    "nav.home": "Home",
    "nav.blog": "Blog",
    "nav.prd": "Product Requirements Doc",
    "nav.github": "GitHub Repository",
    "nav.live": "Live System",
    "nav.theme": "Theme",
    "nav.lang": "Switch Language",

    "section.about": "About",
    "section.work": "Milestones",
    "section.education": "Project Info",
    "section.skills": "Tech Stack",
    "section.projects": "Core Modules",
    "section.projects.subtitle":
      "A complete system built from zero to production in 3 months. Six core modules, fully open-sourced on GitHub.",
    "section.achievements": "Results",
    "section.achievements.subtitle":
      "Real evaluation data and key engineering wins — every number is traceable, with SHA-256 sealed evidence chains.",
    "section.contact": "Contact & Links",
    "contact.title": "Get in Touch",
    "contact.description":
      "The project is fully open-source on GitHub — stars, issues and PRs are welcome. The complete PRD is available, and the system is running live in production.",
  },
};

interface I18nContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  toggleLang: () => void;
  t: (key: string) => string;
  data: ResumeData;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  // SSR 与首帧固定渲染 zh，挂载后再应用 localStorage 中保存的语言，避免水合不一致。
  const [lang, setLangState] = useState<Lang>("zh");

  useEffect(() => {
    const saved = localStorage.getItem("lang");
    if (saved === "zh" || saved === "en") {
      setLangState(saved);
    }
  }, []);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    localStorage.setItem("lang", next);
    document.documentElement.lang = next === "zh" ? "zh-CN" : "en";
  }, []);

  const toggleLang = useCallback(() => {
    setLangState((prev) => {
      const next: Lang = prev === "zh" ? "en" : "zh";
      localStorage.setItem("lang", next);
      document.documentElement.lang = next === "zh" ? "zh-CN" : "en";
      return next;
    });
  }, []);

  const value = useMemo<I18nContextValue>(
    () => ({
      lang,
      setLang,
      toggleLang,
      t: (key: string) => UI_STRINGS[lang][key] ?? key,
      data: RESUME[lang],
    }),
    [lang, setLang, toggleLang]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    throw new Error("useI18n must be used within a LanguageProvider");
  }
  return ctx;
}
