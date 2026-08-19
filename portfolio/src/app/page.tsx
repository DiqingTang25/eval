/* eslint-disable @next/next/no-img-element */
"use client";

import BlurFade from "@/components/magicui/blur-fade";
import BlurFadeText from "@/components/magicui/blur-fade-text";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { GITHUB_REPO, LIVE_SYSTEM, PRD_URL } from "@/data/resume";
import { useI18n } from "@/lib/i18n";
import { Icons } from "@/components/icons";
import { ArrowUpRight, FileText, GlobeIcon } from "lucide-react";
import Link from "next/link";
import Markdown from "react-markdown";
import ContactSection from "@/components/section/contact-section";
import HackathonsSection from "@/components/section/hackathons-section";
import ProjectsSection from "@/components/section/projects-section";
import WorkSection from "@/components/section/work-section";

const BLUR_FADE_DELAY = 0.04;

export default function Page() {
  const { t, data } = useI18n();

  return (
    <main className="min-h-dvh flex flex-col gap-14 relative">
      <section id="hero">
        <div className="mx-auto w-full max-w-2xl space-y-8">
          <div className="gap-2 gap-y-6 flex flex-col md:flex-row justify-between">
            <div className="gap-2 flex flex-col order-2 md:order-1">
              <BlurFade delay={BLUR_FADE_DELAY}>
                <Badge className="w-fit bg-primary text-primary-foreground rounded-md">
                  {data.hero.badge}
                </Badge>
              </BlurFade>
              <BlurFadeText
                delay={BLUR_FADE_DELAY * 2}
                className="text-3xl font-semibold tracking-tighter sm:text-4xl lg:text-5xl bg-gradient-to-r from-indigo-600 via-violet-600 to-fuchsia-600 dark:from-indigo-400 dark:via-violet-400 dark:to-fuchsia-400 bg-clip-text text-transparent"
                yOffset={8}
                text={data.hero.title}
              />
              <BlurFadeText
                className="text-muted-foreground max-w-[600px] md:text-lg"
                delay={BLUR_FADE_DELAY * 3}
                text={data.hero.subtitle}
              />
              <BlurFade delay={BLUR_FADE_DELAY * 4}>
                <div className="flex flex-wrap gap-2 pt-2">
                  <Button asChild size="sm">
                    <a
                      href={GITHUB_REPO}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <Icons.github className="mr-1.5 size-4" />
                      GitHub
                    </a>
                  </Button>
                  <Button asChild size="sm" variant="outline">
                    <Link href={PRD_URL}>
                      <FileText className="mr-1.5 size-4" />
                      PRD
                    </Link>
                  </Button>
                  <Button asChild size="sm" variant="outline">
                    <a
                      href={LIVE_SYSTEM}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <GlobeIcon className="mr-1.5 size-4" />
                      {t("nav.live")}
                    </a>
                  </Button>
                </div>
              </BlurFade>
            </div>
            <BlurFade delay={BLUR_FADE_DELAY} className="order-1 md:order-2">
              <Avatar className="size-24 md:size-32 border rounded-full shadow-lg ring-4 ring-muted bg-background">
                <AvatarImage alt={data.name} src={data.avatarUrl} />
                <AvatarFallback>{data.initials}</AvatarFallback>
              </Avatar>
            </BlurFade>
          </div>
          <BlurFade delay={BLUR_FADE_DELAY * 5}>
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
              {data.hero.stats.map((stat) => (
                <div
                  key={stat.label}
                  className="border border-border bg-card rounded-xl p-3 text-center"
                >
                  <div className="text-lg font-semibold tracking-tight">
                    {stat.value}
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-0.5">
                    {stat.label}
                  </div>
                </div>
              ))}
            </div>
          </BlurFade>
        </div>
      </section>

      <section id="about">
        <div className="flex min-h-0 flex-col gap-y-4">
          <BlurFade delay={BLUR_FADE_DELAY * 6}>
            <h2 className="text-xl font-bold">{t("section.about")}</h2>
          </BlurFade>
          <BlurFade delay={BLUR_FADE_DELAY * 7}>
            <div className="prose max-w-full text-pretty font-sans leading-relaxed text-muted-foreground dark:prose-invert">
              <Markdown>{data.summary}</Markdown>
            </div>
          </BlurFade>
        </div>
      </section>

      <section id="work">
        <div className="flex min-h-0 flex-col gap-y-6">
          <BlurFade delay={BLUR_FADE_DELAY * 8}>
            <h2 className="text-xl font-bold">{t("section.work")}</h2>
          </BlurFade>
          <BlurFade delay={BLUR_FADE_DELAY * 9}>
            <WorkSection />
          </BlurFade>
        </div>
      </section>

      <section id="education">
        <div className="flex min-h-0 flex-col gap-y-6">
          <BlurFade delay={BLUR_FADE_DELAY * 10}>
            <h2 className="text-xl font-bold">{t("section.education")}</h2>
          </BlurFade>
          <div className="flex flex-col gap-8">
            {data.education.map((education, index) => (
              <BlurFade
                key={education.school}
                delay={BLUR_FADE_DELAY * 11 + index * 0.05}
              >
                <Link
                  href={education.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-x-3 justify-between group"
                >
                  <div className="flex items-center gap-x-3 flex-1 min-w-0">
                    {education.logoUrl ? (
                      <img
                        src={education.logoUrl}
                        alt={education.school}
                        className="size-8 md:size-10 p-1 border rounded-full shadow ring-2 ring-border overflow-hidden object-contain flex-none"
                      />
                    ) : (
                      <div className="size-8 md:size-10 p-1 border rounded-full shadow ring-2 ring-border bg-muted flex-none" />
                    )}
                    <div className="flex-1 min-w-0 flex flex-col gap-0.5">
                      <div className="font-semibold leading-none flex items-center gap-2">
                        {education.school}
                        <ArrowUpRight className="h-3.5 w-3.5 text-muted-foreground opacity-0 -translate-x-2 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200" aria-hidden />
                      </div>
                      <div className="font-sans text-sm text-muted-foreground">
                        {education.degree}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 text-xs tabular-nums text-muted-foreground text-right flex-none">
                    <span>
                      {education.start} - {education.end}
                    </span>
                  </div>
                </Link>
              </BlurFade>
            ))}
          </div>
        </div>
      </section>

      <section id="skills">
        <div className="flex min-h-0 flex-col gap-y-4">
          <BlurFade delay={BLUR_FADE_DELAY * 12}>
            <h2 className="text-xl font-bold">{t("section.skills")}</h2>
          </BlurFade>
          <div className="flex flex-wrap gap-2">
            {data.skills.map((skill, id) => (
              <BlurFade key={skill.name} delay={BLUR_FADE_DELAY * 13 + id * 0.05}>
                <div className="border bg-background border-border ring-2 ring-border/20 rounded-xl h-8 w-fit px-4 flex items-center gap-2">
                  {skill.icon && <skill.icon className="size-4 rounded overflow-hidden object-contain" />}
                  <span className="text-foreground text-sm font-medium">{skill.name}</span>
                </div>
              </BlurFade>
            ))}
          </div>
        </div>
      </section>

      <section id="projects">
        <BlurFade delay={BLUR_FADE_DELAY * 14}>
          <ProjectsSection />
        </BlurFade>
      </section>

      <section id="achievements">
        <BlurFade delay={BLUR_FADE_DELAY * 16}>
          <HackathonsSection />
        </BlurFade>
      </section>

      <section id="contact">
        <BlurFade delay={BLUR_FADE_DELAY * 18}>
          <ContactSection />
        </BlurFade>
      </section>
    </main>
  );
}
