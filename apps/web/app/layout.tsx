import type { ReactNode } from "react";
import "./globals.css";

export const metadata = {
  title: "Evidence Layer",
  description: "Platform foundation ready",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
