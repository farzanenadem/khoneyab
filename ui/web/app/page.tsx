"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import ChatPanel from "@/components/ChatPanel";
import FiltersPanel from "@/components/FiltersPanel";
import JobCard from "@/components/JobCard";
import QueryUnderstanding from "@/components/QueryUnderstanding";
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
  "دنبال یک موقعیت شغلی در حوزه هوش مصنوعی هستم که به Python، مدل‌های زبانی بزرگ و RAG مرتبط باشد و ترجیحاً در تهران یا به‌صورت دورکاری باشد.",
  "حسابدار با ۳ سال سابقه، آشنا به اکسل و نرم‌افزار سپیدار، ترجیحاً در اصفهان",
  "برنامه نویس فرانت‌اند با React و TypeScript، تمام وقت در تهران",
  "کارآموزی در دیجیتال مارکتینگ و سئو بدون سابقه",
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
  const [sort, setSort] = useState<Sort>("relevance");
  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [tab, setTab] = useState<"search" | "chat">("search");

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

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    run(query, filters, method, topK, sort);
  };

  return (
    <div className="page">
      <header className="hero">
        <nav className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === "search"} className={tab === "search" ? "tab tab-on" : "tab"} onClick={() => setTab("search")}>
            جستجوی توصیفی
          </button>
          <button role="tab" aria-selected={tab === "chat"} className={tab === "chat" ? "tab tab-on" : "tab"} onClick={() => setTab("chat")}>
            گفتگو با دستیار شغلی
          </button>
        </nav>
        <h1>جستجوی توصیفی شغل</h1>
        <p>
          شغل دلخواهتان را به زبان خودتان توصیف کنید: مهارت‌ها، سابقه، مسئولیت‌ها، شهر یا دورکاری. نتایج از
          آگهی‌های واقعی جاب‌ویژن{options ? ` (${options.total.toLocaleString("fa-IR")} آگهی)` : ""} انتخاب
          می‌شوند و برای هر کدام دلیلِ تطابق از متن خود آگهی نشان داده می‌شود.
        </p>
        {tab === "chat" && <ChatPanel />}
        {tab === "search" && (
        <>
        <form onSubmit={onSubmit} className="search">
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
            <button className="btn btn-primary" type="submit" disabled={loading || query.trim().length < 2}>
              {loading ? "در حال جستجو…" : "جستجو"}
            </button>
            <label className="inline">
              مرتب‌سازی
              <select value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
                <option value="relevance">مرتبط‌ترین (با اولویت آگهی‌های تازه)</option>
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
        </form>
        <div className="examples">
          <span className="muted small">نمونه‌ها:</span>
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              className="example"
              onClick={() => {
                setQuery(ex);
                run(ex, filters, method, topK, sort);
              }}
            >
              {ex.length > 60 ? ex.slice(0, 60) + "…" : ex}
            </button>
          ))}
        </div>
        </>
        )}
        {status && <div className="alert">{status}</div>}
      </header>

      {tab === "search" && (
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
                    ? "جستجوی زنده در جاب‌ویژن انجام نشد؛ نتایج از آگهی‌های ذخیره‌شده است."
                    : `جستجوی زنده در جاب‌ویژن برای «${(data.live.keywords || []).join("، ")}»: ${(data.live.new_jobs ?? 0).toLocaleString("fa-IR")} آگهی تازه اضافه شد.`}
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
            <div className="empty">توضیح شغل دلخواهتان را بنویسید یا یکی از نمونه‌ها را امتحان کنید.</div>
          )}
        </section>
      </main>
      )}

      <footer className="site-foot muted small">
        داده‌ها: آگهی‌های عمومی <a href="https://jobvision.ir" target="_blank" rel="noopener noreferrer">jobvision.ir</a>.
        همه اطلاعات نمایش‌داده‌شده عیناً از آگهی‌ها گرفته شده‌اند؛ برای جزئیات و ارسال رزومه به آگهی اصلی مراجعه
        کنید.
      </footer>
    </div>
  );
}
