"use client";

import { KeyboardEvent, useEffect, useState } from "react";
import HomeChat from "@/components/HomeChat";
import HomeListings from "@/components/HomeListings";
import LoanPanel from "@/components/LoanPanel";
import PurchaseRoadmap from "@/components/PurchaseRoadmap";
import Icon, { IconName } from "@/components/Icon";
import ThemeToggle from "@/components/ThemeToggle";
import { HomeOptions, getHomeOptions } from "@/lib/homes";

type Tab = "listings" | "loans" | "roadmap";
type Mode = "chat" | "list";

const MODES: { id: Mode; icon: IconName; label: string }[] = [
  { id: "chat", icon: "chat", label: "گفتگو با دستیار" },
  { id: "list", icon: "list", label: "فهرست و فیلترها" },
];

const TABS: { id: Tab; icon: IconName; label: string }[] = [
  { id: "listings", icon: "home", label: "آگهی‌های خرید خانه" },
  { id: "loans", icon: "bank", label: "وام‌های مسکن بانک‌ها" },
  { id: "roadmap", icon: "map", label: "نقشه راه استعلام‌ها" },
];

/** Arrow/Home/End keyboard navigation for the tab list (RTL: ArrowLeft moves forward). */
function arrowNav(e: KeyboardEvent<HTMLElement>, current: Tab, select: (id: Tab) => void) {
  const ids = TABS.map((t) => t.id);
  const i = ids.indexOf(current);
  const next =
    e.key === "ArrowLeft" ? ids[(i + 1) % ids.length]
    : e.key === "ArrowRight" ? ids[(i - 1 + ids.length) % ids.length]
    : e.key === "Home" ? ids[0]
    : e.key === "End" ? ids[ids.length - 1]
    : null;
  if (!next) return;
  e.preventDefault();
  select(next);
  document.getElementById("tab-" + next)?.focus();
}

export default function Home() {
  const [tab, setTab] = useState<Tab>("listings");
  const [options, setOptions] = useState<HomeOptions | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [price, setPrice] = useState(10_000_000_000);
  const [mode, setMode] = useState<Mode>("chat");
  const pickPrice = (p: number) => {
    setPrice(p);
    setTab("loans");
  };

  useEffect(() => {
    getHomeOptions()
      .then((o) => {
        setOptions(o);
        if (!o.total) setStatus("هنوز آگهی‌ای ذخیره نشده؛ ابتدا python -m agent.home_search.divar_crawler را اجرا کنید.");
      })
      .catch(() => setStatus("ارتباط با سرور برقرار نشد. آیا API روی پورت ۸۰۰۰ اجرا شده است؟"));
  }, []);

  return (
    <div className="page">
      <div className="topbar">
        <div className="brand">
          <span className="logo"><Icon name="home" size={21} strokeWidth={2.2} /></span>
          <span className="brand-copy">خونه‌یاب <small>HOME FINDER</small></span>
        </div>
        <nav className="top-nav" aria-label="ناوبری اصلی">
          <button type="button" className={`top-nav-link ${tab === "listings" ? "top-nav-link-on" : ""}`} onClick={() => setTab("listings")}>خانه‌ها</button>
          <button type="button" className={`top-nav-link ${tab === "loans" ? "top-nav-link-on" : ""}`} onClick={() => setTab("loans")}>توان مالی</button>
          <button type="button" className={`top-nav-link ${tab === "roadmap" ? "top-nav-link-on" : ""}`} onClick={() => setTab("roadmap")}>مسیر امن خرید</button>
        </nav>
        <div className="topbar-actions">
          <span className="topbar-meta"><span className="live-dot" />
            {options ? `${options.total.toLocaleString("fa-IR")} آگهی نمونه از دیوار` : "در حال اتصال…"}
          </span>
          <ThemeToggle />
        </div>
      </div>

      <header className="hero">
        <div className="hero-grid">
          <div className="hero-copy">
            <span className="hero-badge"><span className="hero-badge-dot" /><Icon name="sparkles" size={15} /> دستیار خرید خانه</span>
            <h1>برای خانه‌ای که <span className="accent">دوستش داری</span> دقیق‌تر انتخاب کن</h1>
            <p className="hero-sub">
              آگهی‌های واقعی را کنار هم ببین، بودجه‌ات را بسنج و قبل از هر پرداخت با خیال جمع جلو برو.
            </p>
            <div className="hero-trust"><span><Icon name="shield" size={15} /> داده‌های واقعی</span><span><Icon name="calculator" size={15} /> محاسبه شفاف</span><span><Icon name="check" size={15} /> بدون حدس</span></div>
          </div>
          <div className="hero-art" aria-hidden="true">
            <div className="art-window">
              <div className="art-window-bar"><span /><span /><span /></div>
              <div className="art-window-body">
                <div className="art-house"><Icon name="home" size={54} strokeWidth={1.35} /></div>
                <div className="art-lines"><i /><i /><i /></div>
              </div>
              <div className="art-window-footer"><span><Icon name="pin" size={14} /> تهران و کرج</span><b>انتخاب مطمئن</b></div>
            </div>
            <div className="float-card float-card-top"><span className="float-icon"><Icon name="check" size={15} /></span><span><b>۱٬۴۶۶ آگهی واقعی</b><small>آماده‌ی جست‌وجو</small></span></div>
            <div className="float-card float-card-bottom"><Icon name="shield" size={16} /><span>قبل از معامله، بررسی کن</span></div>
          </div>
        </div>
        <nav className="segmented" role="tablist" aria-label="بخش‌ها" onKeyDown={(e) => arrowNav(e, tab, setTab)}>
          {TABS.map((t) => (
            <button
              key={t.id}
              id={`tab-${t.id}`}
              role="tab"
              aria-selected={tab === t.id}
              aria-controls={`panel-${t.id}`}
              tabIndex={tab === t.id ? 0 : -1}
              className={tab === t.id ? "seg seg-on" : "seg"}
              onClick={() => setTab(t.id)}
            >
              <Icon name={t.icon} size={17} /> <span>{t.label}</span>
            </button>
          ))}
        </nav>
        <div className="hero-stats" aria-label="مزیت‌های خونه‌یاب">
          <div><strong>۱٬۴۶۶</strong><span>آگهی آماده‌ی بررسی</span></div>
          <div><strong>۳</strong><span>ابزار برای تصمیم‌گیری</span></div>
          <div><strong>۱۰۰٪</strong><span>شفاف و مستند</span></div>
        </div>
        {status && <div className="alert">{status}</div>}
      </header>

      <main className="career-main" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "listings" && (
          <div className="mode-switch h-modes" role="radiogroup" aria-label="نوع جستجو">
            {MODES.map((m) => (
              <button
                key={m.id}
                type="button"
                role="radio"
                aria-checked={mode === m.id}
                className={mode === m.id ? "mode mode-on" : "mode"}
                onClick={() => setMode(m.id)}
              >
                <Icon name={m.icon} size={17} /> {m.label}
              </button>
            ))}
          </div>
        )}
        {/* Kept mounted so the conversation survives switching modes/tabs. */}
        <div hidden={tab !== "listings" || mode !== "chat"}>
          <HomeChat onPickPrice={pickPrice} />
        </div>
        {tab === "listings" && mode === "list" && <HomeListings options={options} onPickPrice={pickPrice} />}
        {/* Kept mounted so the loan form survives switching tabs. */}
        <div hidden={tab !== "loans"}>
          <LoanPanel price={price} cities={options?.cities.map((c) => c.city) ?? []} />
        </div>
        {tab === "roadmap" && <PurchaseRoadmap />}
      </main>
    </div>
  );
}
