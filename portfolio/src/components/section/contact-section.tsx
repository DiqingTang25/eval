"use client";

import Link from "next/link";
import { FlickeringGrid } from "@/components/magicui/flickering-grid";
import { GITHUB_REPO, LIVE_SYSTEM, PRD_URL } from "@/data/resume";
import { useI18n } from "@/lib/i18n";

export default function ContactSection() {
  const { t } = useI18n();

  return (
    <div className="border rounded-xl p-10 relative">
      <div className="absolute -top-4 border bg-primary z-10 rounded-xl px-4 py-1 left-1/2 -translate-x-1/2">
        <span className="text-background text-sm font-medium">
          {t("section.contact")}
        </span>
      </div>
      <div className="absolute inset-0 top-0 left-0 right-0 h-1/2 rounded-xl overflow-hidden">
        <FlickeringGrid
          className="h-full w-full"
          squareSize={2}
          gridGap={2}
          style={{
            maskImage: "linear-gradient(to bottom, black, transparent)",
            WebkitMaskImage: "linear-gradient(to bottom, black, transparent)",
          }}
        />
      </div>
      <div className="relative flex flex-col items-center gap-4 text-center">
        <h2 className="text-3xl font-bold tracking-tighter sm:text-5xl">
          {t("contact.title")}
        </h2>
        <p className="mx-auto max-w-lg text-muted-foreground text-balance">
          {t("contact.description")}
        </p>
        <div className="flex flex-wrap justify-center gap-2">
          <Link
            href={GITHUB_REPO}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md border border-input bg-background px-4 py-2 text-sm font-medium shadow-sm hover:bg-accent hover:text-accent-foreground transition-colors"
          >
            GitHub · DiqingTang25/eval
          </Link>
          <Link
            href={PRD_URL}
            className="inline-flex items-center gap-1.5 rounded-md border border-input bg-background px-4 py-2 text-sm font-medium shadow-sm hover:bg-accent hover:text-accent-foreground transition-colors"
          >
            PRD · 产品需求文档
          </Link>
          <Link
            href={LIVE_SYSTEM}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md border border-input bg-background px-4 py-2 text-sm font-medium shadow-sm hover:bg-accent hover:text-accent-foreground transition-colors"
          >
            在线系统
          </Link>
        </div>
      </div>
    </div>
  );
}
