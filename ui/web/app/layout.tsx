import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "جستجوی توصیفی شغل",
  description: "شغل دلخواهتان را به زبان ساده توصیف کنید و آگهی‌های واقعی مرتبط را ببینید.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fa" dir="rtl">
      <head>
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
