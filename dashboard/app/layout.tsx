import type { Metadata } from "next";
import "./globals.css";
import { Analytics } from "@vercel/analytics/next";
import { cabinetGrotesk, satoshi, jetbrainsMono } from "./fonts";
import { MotionProvider } from "@/components/motion-provider";

const description =
  "A public MCP server that returns cited passages from SEC filings and checks the figures in an answer against them.";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "https://dashboard-weld-nine-28.vercel.app"),
  title: "FinRAG MCP",
  description,
  openGraph: {
    title: "FinRAG MCP",
    description,
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "FinRAG MCP",
    description,
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <body
        className={`${cabinetGrotesk.variable} ${satoshi.variable} ${jetbrainsMono.variable} font-[family-name:var(--font-body)] min-h-[100dvh] bg-[var(--color-bg)] text-[var(--color-text)] antialiased`}
      >
        <MotionProvider>{children}</MotionProvider>
        <Analytics />
      </body>
    </html>
  );
}
