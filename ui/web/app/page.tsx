"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import CareerRoadmap from "@/components/CareerRoadmap";
import ChatPanel, { ChatSeed } from "@/components/ChatPanel";
import FiltersPanel from "@/components/FiltersPanel";
import JobCard from "@/components/JobCard";
import QueryUnderstanding from "@/components/QueryUnderstanding";
import ResumePanel from "@/components/ResumePanel";
import {
  EMPTY_FILTERS,
  FilterOptions,
  Filters,
  Method,
  SearchResponse,
  Sort,
  getFilterOptions,
  getHealth,
  searchJobs,
} from "@/lib/api";

const EXAMPLES = [
  {
    icon: "🤖",
    label: "هوش مصنوعی",
    text: "دنبال یک موقعیت شغلی در حوزه هوش مصنوعی هستم که به Python، مدل‌های زبانی بزرگ و RAG مرتبط باشد و ترجیحاً در تهران یا به‌صورت دورکاری باشد.",
  },
  { icon: "💻", label: "فرانت‌اند", text: "برنامه نویس فرانت‌اند با React و TypeScript، تمام وقت در تهران" },
  { icon: "📊", label: "حسابداری", text: "حسابدار با ۳ سال سابقه، آشنا به اکسل و نرم‌افزار سپیدار، ترجیحاً در اصفهان" },
  { icon: "📣", label: "کارآموزی", text: "کارآموزی در دیجیتال مارکتینگ و سئو بدون سابقه" },
];

const METHOD_LABELS: Record<Method, string> = {
  hybrid: "ترکیبی (پیشنهادی)",
  semantic: "فقط معنایی",
  bm25: "فقط واژگانی (BM25)",
  keyword: "پایه: هم‌پوشانی واژه‌ها",
};

export default function Home() {
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [options, setOptions] = useState<FilterOptions | null>(null);
  const [method, setMethod] = useState<Method>("hybrid");
  const [topK, setTopK] = useState(10);
  const [sort, setSort] = useState<Sort>("newest");
  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [tab, setTab] = useState<"search" | "resume" | "roadmap">("search");
  const [mode, setMode] = useState<"list" | "chat">("list");
  const [seed, setSeed] = useState<ChatSeed | null>(null);

  useEffect(() => {
    getHealth()
      .then((h) => {
        if (!h.job_search_ready) setStatus(`سرویس جستجو آماده نیست: ${h.job_search_error ?? ""}`);
      })
      .catch(() => setStatus("ارتباط با سرور جستجو برقرار نشد. آیا API روی پورت ۸۰۰۰ اجرا شده است؟"));
    getFilterOptions().then(setOptions).catch(() => setOptions(null));
  }, []);

  const run = useCallback(
    async (q: string, f: Filters, m: Method, k: number, so: Sort = "relevance") => {
      if (q.trim().length < 2) return;
      setLoading(true);
      setError(null);
      try {
        setData(await searchJobs(q.trim(), f, k, m, so));
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  // Re-run the current search when filters or settings change.
  useEffect(() => {
    if (data) run(query, filters, method, topK, sort);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, method, topK, sort]);

  const go = (q: string) => {
    if (q.trim().length < 2) return;
    if (mode === "chat") setSeed({ text: q.trim(), nonce: Date.now() });
    else run(q, filters, method, topK, sort);
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    go(query);
  };

  return (
    <div className="page">
      <div className="topbar">
        <div className="brand">
          <span className="logo">ج</span>
          <span>جاب‌یاب</span>
        </div>
        <span className="topbar-meta">
          {options ? `${options.total.toLocaleString("fa-IR")} آگهی از جاب‌ویژن، جابینجا و ایران‌تلنت` : "در حال اتصال…"}
        </span>
      </div>

      <header className="hero">
        <span className="hero-badge">✨ جستجوی هوشمند شغل به زبان فارسی</span>
        <h1>
          شغل دلخواهت را <span className="accent">توصیف کن</span>، ما پیدایش می‌کنیم
        </h1>
        <p className="hero-sub">
          مهارت‌ها، سابقه، شهر یا دورکاری را به زبان خودت بنویس یا رزومه‌ات را بارگذاری کن. نتایج از آگهی‌های
          واقعی و به‌روز انتخاب می‌شوند و دلیل هر پیشنهاد از متن خود آگهی نشان داده می‌شود.
        </p>

        <nav className="segmented" role="tablist">
          <button role="tab" aria-selected={tab === "search"} className={tab === "search" ? "seg seg-on" : "seg"} onClick={() => setTab("search")}>
            🔍 جستجو و دستیار
          </button>
          <button role="tab" aria-selected={tab === "resume"} className={tab === "resume" ? "seg seg-on" : "seg"} onClick={() => setTab("resume")}>
            📄 جستجو با رزومه
          </button>
          <button role="tab" aria-selected={tab === "roadmap"} className={tab === "roadmap" ? "seg seg-on" : "seg"} onClick={() => setTab("roadmap")}>
            🗺️ نقشه مسیر شغلی
          </button>
        </nav>
        {tab === "resume" && <ResumePanel />}
        {tab === "search" && (
        <>
        <form onSubmit={onSubmit} className="search">
          <div className="mode-switch" role="radiogroup" aria-label="نوع پاسخ">
            <button type="button" role="radio" aria-checked={mode === "list"} className={mode === "list" ? "mode mode-on" : "mode"} onClick={() => setMode("list")}>
              📋 فهرست آگهی‌ها
            </button>
            <button type="button" role="radio" aria-checked={mode === "chat"} className={mode === "chat" ? "mode mode-on" : "mode"} onClick={() => setMode("chat")}>
              💬 پاسخ دستیار هوشمند
            </button>
          </div>
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="مثلاً: دنبال کار در حوزه تحلیل داده با SQL و Power BI در تهران هستم…"
            rows={3}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) onSubmit(e);
            }}
            aria-label="توضیح شغل دلخواه"
          />
          <div className="search-row">
            <details className="advanced">
              <summary>تنظیمات پیشرفته</summary>
              <div className="advanced-body">
                <label className="inline">
                  مرتب‌سازی
                  <select value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
                    <option value="relevance">مرتبط‌ترین</option>
                    <option value="newest">جدیدترین</option>
                  </select>
                </label>
                <label className="inline">
                  روش رتبه‌بندی
                  <select value={method} onChange={(e) => setMethod(e.target.value as Method)}>
                    {(Object.keys(METHOD_LABELS) as Method[]).map((m) => (
                      <option key={m} value={m}>
                        {METHOD_LABELS[m]}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="inline">
                  تعداد نتایج
                  <select value={topK} onChange={(e) => setTopK(Number(e.target.value))}>
                    {[10, 20, 30, 50].map((k) => (
                      <option key={k} value={k}>
                        {k.toLocaleString("fa-IR")}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </details>
            <button className="btn btn-primary btn-lg" type="submit" disabled={loading || query.trim().length < 2}>
              {mode === "chat" ? "بپرس" : loading ? "در حال جستجو…" : "جستجو"}
            </button>
          </div>
        </form>
        <div className="samples">
          {EXAMPLES.map((ex) => (
            <button
              key={ex.label}
              type="button"
              className="sample"
              onClick={() => {
                setQuery(ex.text);
                go(ex.text);
              }}
            >
              <span className="sample-icon">{ex.icon}</span>
              <span className="sample-label">{ex.label}</span>
              <span className="sample-text">{ex.text}</span>
            </button>
          ))}
        </div>
        </>
        )}
        {status && <div className="alert">{status}</div>}
      </header>

      {tab === "roadmap" && <main className="career-main"><CareerRoadmap /></main>}

      {/* Kept mounted so the conversation survives switching modes/tabs. */}
      <main className="chat-main" hidden={tab !== "search" || mode !== "chat"}>
        <ChatPanel seed={seed} />
      </main>

      {tab === "search" && mode === "list" && (
      <main className="layout">
        <FiltersPanel options={options} filters={filters} onChange={setFilters} onReset={() => setFilters(EMPTY_FILTERS)} />

        <section className="results" aria-live="polite">
          {error && <div className="alert">خطا در جستجو: {error}</div>}
          {data && (
            <>
              <QueryUnderstanding q={data.query} />
              {data.live?.enabled && (
                <p className="muted small">
                  {data.live.error
                    ? "جستجوی زنده انجام نشد؛ نتایج از آگهی‌های ذخیره‌شده است."
                    : `جستجوی زنده در جاب‌ویژن، جابینجا و ایران‌تلنت برای «${(data.live.keywords || []).join("، ")}»: ${(data.live.new_jobs ?? 0).toLocaleString("fa-IR")} آگهی تازه اضافه شد.`}
                </p>
              )}
              <p className="muted small">
                {data.results.length.toLocaleString("fa-IR")} آگهی مرتبط از میان{" "}
                {data.total_candidates.toLocaleString("fa-IR")} آگهیِ فعال و منطبق با فیلترها (آگهی‌های منقضی‌شده نمایش داده نمی‌شوند)
              </p>
              {data.results.length === 0 && (
                <div className="empty">آگهی‌ای با این فیلترها پیدا نشد. فیلترها را کمتر کنید.</div>
              )}
              {data.results.map((r) => (
                <JobCard key={r.job.id} result={r} />
              ))}
            </>
          )}
          {!data && !error && (
            <div className="empty">
              <div className="empty-icon">🧭</div>
              توضیح شغل دلخواهتان را بنویسید یا روی یکی از نمونه‌ها کلیک کنید.
            </div>
          )}
        </section>
      </main>
      )}

      <footer className="site-foot muted small">
        داده‌ها: آگهی‌های عمومی{" "}
        <a href="https://jobvision.ir" target="_blank" rel="noopener noreferrer">
          جاب‌ویژن
        </a>
        ،{" "}
        <a href="https://jobinja.ir" target="_blank" rel="noopener noreferrer">
          جابینجا
        </a>{" "}
        و{" "}
        <a href="https://irantalent.com" target="_blank" rel="noopener noreferrer">
          ایران‌تلنت
        </a>
        . همه اطلاعات نمایش‌داده‌شده عیناً از آگهی‌ها گرفته شده‌اند؛ برای جزئیات و ارسال رزومه به آگهی اصلی مراجعه
        کنید.
      </footer>
    </div>
  );
}
