import type { ReactNode } from "react";
import "./globals.css";

export const metadata = {
  title: "Evidence Explorer — Evidence Layer",
  description:
    "A local prototype for examining synthetic evidence, provenance, open questions, and explicit relationships.",
};

const themeBootstrap = `(() => {
  try {
    const saved = localStorage.getItem("evidence-layer-theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme =
      saved === "light" || saved === "dark" ? saved : prefersDark ? "dark" : "light";
  } catch {
    document.documentElement.dataset.theme =
      window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
})();`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
