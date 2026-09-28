import type { Metadata } from "next";
import "./globals.css";
import { cabinetGrotesk, satoshi, jetbrainsMono } from "./fonts";

const description =
  "Cited, grounded financial intelligence over SEC filings, exposed as MCP tools any AI assistant can call.";

export const metadata: Metadata = {
  // NEXT_PUBLIC_SITE_URL should be set to the real Vercel URL once deployed
  // (Task 22) — this fallback only resolves relative OG/Twitter image URLs
  // during local builds and is never the real production domain.
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
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
        {children}
      </body>
    </html>
  );
}
