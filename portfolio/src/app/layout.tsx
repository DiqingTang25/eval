import Navbar from "@/components/navbar";
import { ThemeProvider } from "@/components/theme-provider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SITE } from "@/data/resume";
import { LanguageProvider } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { Metadata } from "next";
import "./globals.css";
import { FlickeringGrid } from "@/components/magicui/flickering-grid";

export const metadata: Metadata = {
  metadataBase: new URL(SITE.url),
  title: {
    default: SITE.name,
    template: `%s | ${SITE.name}`,
  },
  description: SITE.description,
  openGraph: {
    title: `${SITE.name} · ${SITE.enName}`,
    description: SITE.description,
    url: SITE.url,
    siteName: SITE.name,
    locale: "zh_CN",
    type: "website",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
  twitter: {
    title: `${SITE.name} · ${SITE.enName}`,
    card: "summary_large_image",
  },
  verification: {
    google: "",
    yandex: "",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body
        className={cn(
          "min-h-screen bg-background font-sans antialiased relative"
        )}
      >
        <ThemeProvider attribute="class" defaultTheme="light">
          <LanguageProvider>
            <TooltipProvider delayDuration={0}>
              <div className="absolute inset-0 top-0 left-0 right-0 h-[100px] overflow-hidden z-0">
                <FlickeringGrid
                  className="h-full w-full"
                  squareSize={2}
                  gridGap={2}
                  style={{
                    maskImage: "linear-gradient(to bottom, black, transparent)",
                    WebkitMaskImage:
                      "linear-gradient(to bottom, black, transparent)",
                  }}
                />
              </div>
              <div className="relative z-10 max-w-2xl mx-auto py-12 pb-24 sm:py-24 px-6">
                {children}
              </div>
              <Navbar />
            </TooltipProvider>
          </LanguageProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
