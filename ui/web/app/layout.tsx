import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "خونه‌یاب — دستیار خرید خانه",
  description: "آگهی‌های دیوار، محاسبه وام مسکن و نقشه راه استعلام‌های قبل از خرید خانه.",
};

const themeInit = `(() => { try { const saved = localStorage.getItem("khoneyab-theme"); const dark = saved === "dark" || (!saved && matchMedia("(prefers-color-scheme: dark)").matches); document.documentElement.dataset.theme = dark ? "dark" : "light"; } catch {} })()`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fa" dir="rtl" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;500;700;800&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
