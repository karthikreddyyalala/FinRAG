import type { Metadata } from "next";
import "./globals.css";
import { cabinetGrotesk, satoshi, jetbrainsMono } from "./fonts";

export const metadata: Metadata = {
  title: "FinRAG MCP",
  description:
    "Cited, grounded financial intelligence over SEC filings, exposed as MCP tools any AI assistant can call.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <body
        className={`${cabinetGrotesk.variable} ${satoshi.variable} ${jetbrainsMono.variable} font-[family-name:var(--font-body)] min-h-[100dvh] bg-[var(--color-bg)] text-[var(--color-text)] antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
