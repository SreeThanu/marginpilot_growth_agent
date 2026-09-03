import type { Metadata } from "next";
import { IBM_Plex_Mono, Schibsted_Grotesk } from "next/font/google";

import { ScenarioProvider } from "@/components/ScenarioContext";
import { TopRail } from "@/components/TopRail";
import "./globals.css";

/**
 * Two faces, two jobs. Schibsted Grotesk states things — it is a news face,
 * built for headlines that have to be read once and understood. IBM Plex Mono
 * carries every figure, because a rupee amount in this product is a ledger
 * entry and ledger entries align.
 */
const display = Schibsted_Grotesk({
  variable: "--font-schibsted",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const mono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "MarginPilot — should this merchant promote?",
  description:
    "AI growth decisions, grounded in merchant economics. The assistant proposes; a deterministic economic policy decides.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${display.variable} ${mono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <ScenarioProvider>
          <TopRail />
          <main className="mx-auto w-full max-w-[1180px] flex-1 px-6 pt-8 pb-24 lg:px-8">
            {children}
          </main>
          <footer className="border-t border-rule px-6 py-6 lg:px-8">
            <div className="mx-auto flex max-w-[1180px] flex-wrap items-center justify-between gap-3">
              <p className="eyebrow">
                Demonstration fixture — not research evidence
              </p>
              <p className="text-[0.78rem] text-slate-soft">
                Every figure on these screens is produced by the MarginPilot
                Python engine and read over HTTP. None is computed here.
              </p>
            </div>
          </footer>
        </ScenarioProvider>
      </body>
    </html>
  );
}
