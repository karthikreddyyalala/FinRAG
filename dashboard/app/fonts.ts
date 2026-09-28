import localFont from "next/font/local";

export const cabinetGrotesk = localFont({
  src: [
    { path: "./fonts/CabinetGrotesk-Bold.woff2", weight: "700", style: "normal" },
    { path: "./fonts/CabinetGrotesk-Extrabold.woff2", weight: "800", style: "normal" },
  ],
  variable: "--font-display",
  display: "swap",
});

export const satoshi = localFont({
  src: [
    { path: "./fonts/Satoshi-Regular.woff2", weight: "400", style: "normal" },
    { path: "./fonts/Satoshi-Medium.woff2", weight: "500", style: "normal" },
  ],
  variable: "--font-body",
  display: "swap",
});

export const jetbrainsMono = localFont({
  src: [{ path: "./fonts/JetBrainsMono-Regular.woff2", weight: "400 600", style: "normal" }],
  variable: "--font-mono",
  display: "swap",
});
