import type { Metadata } from "next";
import { IBM_Plex_Mono, Instrument_Sans } from "next/font/google";

import { TopRail } from "@/components/TopRail";
import "./globals.css";

/**
 * Two faces, two jobs.
 *
 * Instrument Sans states things — a modern grotesque that holds together at
 * display sizes under heavy negative tracking, which is where this product's
 * verdicts live. IBM Plex Mono carries every figure, hash and identifier,
 * because a rupee amount here is a ledger entry and ledger entries align.
 */
const display = Instrument_Sans({
  variable: "--font-instrument",
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
  title: "MarginPilot — is this promotion worth paying for?",
  description:
    "A promotion can lift conversions and still make a merchant poorer. MarginPilot decides whether the economics justify the spend: the assistant proposes, a deterministic policy disposes, an experiment settles the uncertainty.",
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
        <TopRail />
        <main className="flex-1">{children}</main>

        <footer className="mt-24 border-t border-rule">
          <div className="mx-auto flex max-w-[1240px] flex-wrap items-baseline justify-between gap-x-10 gap-y-2 px-8 py-8">
            <p className="eyebrow">
              Demonstration fixture — not research evidence
            </p>
            <p className="t-caption max-w-[64ch] text-ink-subtle">
              Every figure on these screens is produced by the MarginPilot Python
              engine and read over HTTP. None is computed here.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
