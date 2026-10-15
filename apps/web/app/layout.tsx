import type { ReactNode } from "react";
import "./globals.css";

export const metadata = {
  title: "Evidence Explorer — Evidence Layer",
  description:
    "A local prototype for examining synthetic evidence, provenance, open questions, and explicit relationships.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
