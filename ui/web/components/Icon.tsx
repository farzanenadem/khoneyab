import type { ReactNode } from "react";

type IconName =
  | "sparkles"
  | "chat"
  | "list"
  | "home"
  | "bank"
  | "map"
  | "search"
  | "pin"
  | "calculator"
  | "shield"
  | "arrow"
  | "external"
  | "check"
  | "refresh"
  | "building"
  | "sun"
  | "moon";

const paths: Record<IconName, ReactNode> = {
  sparkles: <><path d="m12 3-1.2 5.8L5 10l5.8 1.2L12 17l1.2-5.8L19 10l-5.8-1.2L12 3Z"/><path d="m19 15-.6 2.4L16 18l2.4.6L19 21l.6-2.4L22 18l-2.4-.6L19 15ZM5 3l-.5 2L2.5 5.5 4.5 6 5 8l.5-2 2-.5-2-.5L5 3Z"/></>,
  chat: <><path d="M20 11.5a7.3 7.3 0 0 1-7.7 7.2 8.7 8.7 0 0 1-3.5-.7L4 20l1.2-3.8a7 7 0 0 1-1.2-4.2A7.3 7.3 0 0 1 11.7 5 7.3 7.3 0 0 1 20 11.5Z"/><path d="M8 11.5h.01M12 11.5h.01M16 11.5h.01"/></>,
  list: <><path d="M8 6h11M8 12h11M8 18h11"/><path d="M4 6h.01M4 12h.01M4 18h.01"/></>,
  home: <><path d="m3 10 9-7 9 7"/><path d="M5 9v11h14V9M9 20v-6h6v6"/></>,
  bank: <><path d="m3 9 9-5 9 5H3Z"/><path d="M5 10v7M9 10v7M15 10v7M19 10v7M3 20h18M4 17h16"/></>,
  map: <><path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6Z"/><path d="M9 3v15M15 6v15"/></>,
  search: <><circle cx="10.8" cy="10.8" r="6.4"/><path d="m16 16 4.5 4.5"/></>,
  pin: <><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z"/><circle cx="12" cy="10" r="2.2"/></>,
  calculator: <><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 7h8M8 11h.01M12 11h.01M16 11h.01M8 15h.01M12 15h.01M16 15h.01M8 18h8"/></>,
  shield: <><path d="M12 3 20 6v5c0 5.2-3.4 8.3-8 10-4.6-1.7-8-4.8-8-10V6l8-3Z"/><path d="m8.5 12 2.2 2.2 4.8-4.8"/></>,
  arrow: <path d="M5 12h13M13 6l6 6-6 6"/>,
  external: <><path d="M14 5h5v5M19 5l-8 8"/><path d="M18 13v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h5"/></>,
  check: <path d="m5 12 4 4L19 6"/>,
  refresh: <><path d="M20 11a8 8 0 0 0-14.7-3L3 11"/><path d="M3 5v6h6M4 13a8 8 0 0 0 14.7 3L21 13"/><path d="M21 19v-6h-6"/></>,
  building: <><path d="M4 21V5a2 2 0 0 1 2-2h9v18M15 8h5a1 1 0 0 1 1 1v12M8 7h3M8 11h3M8 15h3M18 12h1M18 16h1M2 21h20"/></>,
  sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></>,
  moon: <path d="M20.5 15.2A8.5 8.5 0 0 1 8.8 3.5 8.5 8.5 0 1 0 20.5 15.2Z"/>,
};

export default function Icon({ name, size = 20, strokeWidth = 1.8, className = "" }: { name: IconName; size?: number; strokeWidth?: number; className?: string }) {
  return (
    <svg className={`icon ${className}`} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[name]}
    </svg>
  );
}

export type { IconName };
