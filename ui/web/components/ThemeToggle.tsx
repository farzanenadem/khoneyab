"use client";

import { useEffect, useState } from "react";
import Icon from "@/components/Icon";

type Theme = "light" | "dark";
const KEY = "khoneyab-theme";

function preferredTheme(): Theme {
  if (typeof window === "undefined") return "light";
  const saved = window.localStorage.getItem(KEY);
  if (saved === "dark" || saved === "light") return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("light");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const next = preferredTheme();
    setTheme(next);
    document.documentElement.dataset.theme = next;
    setReady(true);
  }, []);

  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    window.localStorage.setItem(KEY, next);
  };

  return (
    <button className="theme-toggle" type="button" onClick={toggle} aria-label={theme === "dark" ? "فعال کردن حالت روشن" : "فعال کردن حالت تاریک"} title={theme === "dark" ? "حالت روشن" : "حالت تاریک"}>
      <span className="theme-toggle-icon">{ready && <Icon name={theme === "dark" ? "sun" : "moon"} size={17} />}</span>
      <span className="theme-toggle-label">{theme === "dark" ? "روشن" : "تاریک"}</span>
    </button>
  );
}
