"use client";

import { useCallback, useEffect, useState } from "react";
import { UsageRow, UsageSummary, getUsage, resetUsage } from "@/lib/api";

const FEATURES: Record<string, string> = {
  chat: "دستیار گفتگو",
  resume: "تحلیل رزومه",
  roadmap: "نقشه راه شغل",
  other: "سایر",
};
const STEPS: Record<string, string> = {
  coordinator_router: "مسیریاب (مدل سریع)",
  filter_docs: "فیلتر آگهی‌ها (مدل سریع)",
  generate_with_context: "تولید پاسخ از آگهی‌ها",
  fallback: "پاسخ عمومی",
};

const fa = (n: number) => Math.round(n).toLocaleString("fa-IR");
const usd = (n: number | null) => (n === null ? "—" : `$${n < 0.01 ? n.toFixed(5) : n.toFixed(3)}`);

function Bars({ rows, label }: { rows: UsageRow[]; label: (n: string) => string }) {
  const max = Math.max(1, ...rows.map((r) => r.total_tokens));
  if (rows.length === 0) return <p className="muted small">هنوز داده‌ای نیست.</p>;
  return (
    <ul className="usage-bars">
      {rows.map((r) => (
        <li key={r.name}>
          <div className="usage-bar-head">
            <span>{label(r.name)}</span>
            <span className="muted small">
              {fa(r.total_tokens)} توکن · {fa(r.calls)} فراخوانی
            </span>
          </div>
          <div className="usage-bar" aria-hidden="true">
            <span className="usage-in" style={{ width: `${(r.input_tokens / max) * 100}%` }} />
            <span className="usage-out" style={{ width: `${(r.output_tokens / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

export default function UsagePanel() {
  const [data, setData] = useState<UsageSummary | null>(null);
  const [error, setError] = useState(false);
  const [live, setLive] = useState(true);

  const load = useCallback(() => {
    getUsage()
      .then((d) => {
        setData(d);
        setError(false);
      })
      .catch(() => setError(true));
  }, []);

  useEffect(() => {
    load();
    if (!live) return;
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, [live, load]);

  if (error && !data) return <div className="alert">ارتباط با سرور برقرار نشد.</div>;
  if (!data) return <div className="empty">در حال بارگذاری…</div>;

  const t = data.total;
  const inShare = t.total_tokens ? Math.round((t.input_tokens / t.total_tokens) * 100) : 0;

  return (
    <section className="usage" aria-labelledby="usage-title">
      <header className="usage-head">
        <div>
          <h2 id="usage-title">مصرف توکن مدل زبانی</h2>
          <p className="muted small">
            از آخرین راه‌اندازی سرور · متن پرسش‌ها و پاسخ‌ها ذخیره نمی‌شود، فقط تعداد توکن و زمان.
          </p>
        </div>
        <div className="usage-actions">
          <label className="inline small">
            <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} /> به‌روزرسانی زنده
          </label>
          <button type="button" className="link-btn" onClick={() => resetUsage().then(load)}>
            صفر کردن شمارنده‌ها
          </button>
        </div>
      </header>

      <div className="usage-kpis">
        <div className="usage-kpi">
          <span>کل توکن</span>
          <strong>{fa(t.total_tokens)}</strong>
        </div>
        <div className="usage-kpi">
          <span>فراخوانی مدل</span>
          <strong>{fa(t.calls)}</strong>
        </div>
        <div className="usage-kpi">
          <span>میانگین هر فراخوانی</span>
          <strong>{fa(t.avg_tokens_per_call)}</strong>
          <small>توکن · {t.avg_seconds_per_call.toLocaleString("fa-IR")} ثانیه</small>
        </div>
        <div className="usage-kpi">
          <span>هزینهٔ تخمینی</span>
          <strong>{usd(t.cost_usd)}</strong>
          {!data.pricing_configured && <small>قیمت‌ها تنظیم نشده</small>}
        </div>
      </div>

      <div className="usage-split" aria-label="سهم ورودی و خروجی">
        <div className="usage-bar usage-bar-lg" aria-hidden="true">
          <span className="usage-in" style={{ width: `${inShare}%` }} />
          <span className="usage-out" style={{ width: `${t.total_tokens ? 100 - inShare : 0}%` }} />
        </div>
        <p className="small">
          <span>
            <span className="dot usage-in" />
            ورودی (پرامپت و آگهی‌ها): {fa(t.input_tokens)} ({fa(inShare)}٪)
          </span>
          <span>
            <span className="dot usage-out" />
            خروجی (پاسخ مدل): {fa(t.output_tokens)}
          </span>
        </p>
      </div>

      {(data.errors > 0 || data.calls_without_usage > 0) && (
        <p className="alert">
          {data.errors > 0 && <>خطا در {fa(data.errors)} فراخوانی. </>}
          {data.calls_without_usage > 0 && (
            <>برای {fa(data.calls_without_usage)} فراخوانی، سرویس‌دهنده تعداد توکن را اعلام نکرد.</>
          )}
        </p>
      )}

      <div className="usage-grid">
        <div className="card">
          <h3>به تفکیک قابلیت</h3>
          <Bars rows={data.by_feature} label={(n) => FEATURES[n] ?? n} />
        </div>
        <div className="card">
          <h3>به تفکیک مرحلهٔ دستیار</h3>
          <Bars rows={data.by_step} label={(n) => STEPS[n] ?? n} />
        </div>
        <div className="card">
          <h3>به تفکیک مدل</h3>
          <Bars rows={data.by_model} label={(n) => n} />
        </div>
      </div>

      <div className="card">
        <h3>آخرین فراخوانی‌ها</h3>
        {data.recent.length === 0 ? (
          <p className="muted small">هنوز فراخوانی‌ای ثبت نشده؛ در تب «جستجو و دستیار» یک سؤال از دستیار بپرسید.</p>
        ) : (
          <div className="usage-table-wrap">
            <table className="usage-table">
              <thead>
                <tr>
                  <th>زمان</th>
                  <th>قابلیت</th>
                  <th>مرحله</th>
                  <th>مدل</th>
                  <th>ورودی</th>
                  <th>خروجی</th>
                  <th>ثانیه</th>
                </tr>
              </thead>
              <tbody>
                {data.recent.slice(0, 15).map((c, i) => (
                  <tr key={i}>
                    <td>{new Date(c.time * 1000).toLocaleTimeString("fa-IR")}</td>
                    <td>{FEATURES[c.feature] ?? c.feature}</td>
                    <td>{c.step ? (STEPS[c.step] ?? c.step) : "—"}</td>
                    <td dir="ltr">{c.model}</td>
                    <td>{fa(c.input_tokens)}</td>
                    <td>{fa(c.output_tokens)}</td>
                    <td>{c.seconds.toLocaleString("fa-IR")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
