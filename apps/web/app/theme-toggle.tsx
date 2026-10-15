"use client";

import { useEffect, useRef, useState } from "react";

type Theme = "light" | "dark";

const STORAGE_KEY = "evidence-layer-theme";

function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme | null>(null);
  const hasExplicitChoice = useRef(false);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    let saved: string | null = null;

    try {
      saved = window.localStorage.getItem(STORAGE_KEY);
    } catch {
      // The system preference still provides a usable theme if storage is unavailable.
    }

    hasExplicitChoice.current = saved === "light" || saved === "dark";
    const initialTheme: Theme = hasExplicitChoice.current
      ? (saved as Theme)
      : media.matches
        ? "dark"
        : "light";

    applyTheme(initialTheme);
    setTheme(initialTheme);

    const followSystemPreference = (event: MediaQueryListEvent) => {
      if (!hasExplicitChoice.current) {
        const nextTheme = event.matches ? "dark" : "light";
        applyTheme(nextTheme);
        setTheme(nextTheme);
      }
    };

    media.addEventListener("change", followSystemPreference);
    return () => media.removeEventListener("change", followSystemPreference);
  }, []);

  function toggleTheme() {
    const currentTheme =
      theme ?? (document.documentElement.dataset.theme === "dark" ? "dark" : "light");
    const nextTheme = currentTheme === "dark" ? "light" : "dark";

    hasExplicitChoice.current = true;
    applyTheme(nextTheme);
    setTheme(nextTheme);

    try {
      window.localStorage.setItem(STORAGE_KEY, nextTheme);
    } catch {
      // Keep the current-session choice even if browser storage is unavailable.
    }
  }

  return (
    <button
      className="theme-toggle"
      type="button"
      aria-label={
        theme
          ? `Switch to ${theme === "dark" ? "light" : "dark"} mode`
          : "Switch between light and dark modes"
      }
      aria-pressed={theme === "dark"}
      onClick={toggleTheme}
    >
      <svg
        className="theme-icon theme-icon--sun"
        aria-hidden="true"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" />
      </svg>
      <svg
        className="theme-icon theme-icon--moon"
        aria-hidden="true"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M20.2 15.1A8.5 8.5 0 0 1 8.9 3.8 8.6 8.6 0 1 0 20.2 15.1Z" />
      </svg>
    </button>
  );
}
