/* eslint-disable @next/next/no-img-element */
"use client";

import { Badge } from "@/components/ui/badge";
import Link from "next/link";
import { useI18n } from "@/lib/i18n";
import {
  Timeline,
  TimelineItem,
  TimelineConnectItem,
} from "@/components/timeline";

export default function HackathonsSection() {
  const { t, data } = useI18n();

  return (
    <section id="achievements" className="overflow-hidden">
      <div className="flex min-h-0 flex-col gap-y-8 w-full">
        <div className="flex flex-col gap-y-4 items-center justify-center">
          <div className="flex items-center w-full">
            <div className="flex-1 h-px bg-linear-to-r from-transparent from-5% via-border via-95% to-transparent" />
            <div className="border bg-primary z-10 rounded-xl px-4 py-1">
              <span className="text-background text-sm font-medium">
                {t("section.achievements")}
              </span>
            </div>
            <div className="flex-1 h-px bg-linear-to-l from-transparent from-5% via-border via-95% to-transparent" />
          </div>
          <div className="flex flex-col gap-y-3 items-center justify-center">
            <h2 className="text-3xl font-bold tracking-tighter sm:text-4xl">
              {t("section.achievements")}
            </h2>
            <p className="text-muted-foreground md:text-lg/relaxed lg:text-base/relaxed xl:text-lg/relaxed text-balance text-center">
              {t("section.achievements.subtitle")}
            </p>
          </div>
        </div>
        <Timeline>
          {data.achievements.map((item) => (
            <TimelineItem
              key={item.title + item.dates}
              className="w-full flex items-start justify-between gap-10"
            >
              <TimelineConnectItem className="flex items-start justify-center">
                {item.image ? (
                  <img
                    src={item.image}
                    alt={item.title}
                    className="size-10 bg-card z-10 shrink-0 overflow-hidden p-1 border rounded-full shadow ring-2 ring-border object-contain flex-none"
                  />
                ) : (
                  <div className="size-10 bg-card z-10 shrink-0 overflow-hidden p-1 border rounded-full shadow ring-2 ring-border flex-none" />
                )}
              </TimelineConnectItem>
              <div className="flex flex-1 flex-col justify-start gap-2 min-w-0">
                {item.dates && (
                  <time className="text-xs text-muted-foreground">
                    {item.dates}
                  </time>
                )}
                {item.title && (
                  <h3 className="font-semibold leading-none">{item.title}</h3>
                )}
                {item.location && (
                  <p className="text-sm text-muted-foreground">
                    {item.location}
                  </p>
                )}
                {item.win && (
                  <Badge className="w-fit bg-primary text-primary-foreground">
                    {item.win}
                  </Badge>
                )}
                {item.description && (
                  <p className="text-sm text-muted-foreground leading-relaxed wrap-break-word">
                    {item.description}
                  </p>
                )}
                {item.links && item.links.length > 0 && (
                  <div className="mt-1 flex flex-row flex-wrap items-start gap-2">
                    {item.links.map((link, idx) => (
                      <Link
                        href={link.href}
                        key={idx}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <Badge className="flex items-center gap-1.5 text-xs bg-primary text-primary-foreground">
                          {link.icon}
                          {link.title}
                        </Badge>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            </TimelineItem>
          ))}
        </Timeline>
      </div>
    </section>
  );
}
