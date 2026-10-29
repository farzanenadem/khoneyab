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

const sec = (n: number) => `${n.toLocaleString("fa-IR")} ثانیه`;
const ms = (n: number) => (n >= 1000 ? sec(Math.round(n / 100) / 10) : `${fa(n)} میلی‌ثانیه`);

/** One bar per recent call (oldest to newest); height is relative to the largest value shown. */
function Chart({ values, title, unit, className }: { values: number[]; title: string; unit: string; className: string }) {
  const max = Math.max(1e-9, ...values);
  return (
    <div className="card">
      <h3>{title}</h3>
      {values.length === 0 ? (
        <p className="muted small">هنوز داده‌ای نیست.</p>
      ) : (
        <>
          <div className="usage-chart" role="img" aria-label={`${title}: آخرین ${fa(values.length)} فراخوانی`}>
            {values.map((v, i) => (
              <span key={i} className={className} style={{ height: `${Math.max(4, (v / max) * 100)}%` }} title={`${v.toLocaleString("fa-IR")} ${unit}`} />
            ))}
          </div>
          <p className="muted small">
            آخرین {fa(values.length)} فراخوانی · بیشترین: {max.toLocaleString("fa-IR", { maximumFractionDigits: 1 })} {unit}
          </p>
        </>
      )}
    </div>
  );
}

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
  const [updated, setUpdated] = useState("");

  const load = useCallback(() => {
    getUsage()
      .then((d) => {
        setData(d);
        setError(false);
        setUpdated(new Date().toLocaleTimeString("fa-IR"));
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
          <span className="muted small">آخرین دریافت: {updated}</span>
          <button type="button" className="btn" onClick={load}>تازه‌سازی</button>
          <button type="button" className="link-btn" onClick={() => resetUsage().then(load)}>
            صفر کردن شمارنده‌ها
          </button>
        </div>
      </header>

      {data.history && (
        <div className="card usage-history">
          <h3>کل تاریخچه (ذخیره‌شده، با ری‌استارت پاک نمی‌شود)</h3>
          <div className="usage-kpis">
            <div className="usage-kpi"><span>درخواست ثبت‌شده</span><strong>{fa(data.history.requests)}</strong>
              <small>{fa(data.history.llm_requests)} با مدل زبانی · {fa(data.history.errors)} ناموفق</small></div>
            <div className="usage-kpi"><span>کل توکن</span><strong>{fa(data.history.total_tokens)}</strong>
              <small>ورودی {fa(data.history.input_tokens)} · خروجی {fa(data.history.output_tokens)}</small></div>
            <div className="usage-kpi"><span>میانگین زمان پاسخ</span><strong>{ms(data.history.avg_duration_ms)}</strong></div>
            <div className="usage-kpi"><span>از تاریخ</span>
              <strong className="usage-kpi-sm">{data.history.since ? new Date(data.history.since * 1000).toLocaleDateString("fa-IR") : "—"}</strong>
              <small dir="ltr">{data.history.path}</small></div>
          </div>
        </div>
      )}

      <div className="usage-links">
        <a className="btn" href="http://localhost:6333/dashboard" target="_blank" rel="noopener noreferrer">
          داشبورد Qdrant (آگهی‌های کش‌شده) ↗
        </a>
      </div>

      <h3 className="usage-section">از آخرین راه‌اندازی سرور</h3>
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
          <span>سرعت تولید پاسخ</span>
          <strong>{fa(t.output_tokens_per_second)}</strong>
          <small>توکن خروجی در ثانیه</small>
        </div>
        <div className="usage-kpi">
          <span>زمان پاسخ مدل (میانه)</span>
          <strong>{sec(t.p50_seconds)}</strong>
          <small>۹۵٪ فراخوانی‌ها کمتر از {sec(t.p95_seconds)}</small>
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

      <div className="usage-grid">
        <Chart title="توکن هر فراخوانی" unit="توکن" className="usage-in" values={data.timeline.map((c) => c.total_tokens)} />
        <Chart title="زمان هر فراخوانی" unit="ثانیه" className="usage-out" values={data.timeline.map((c) => c.seconds)} />
      </div>

      <div className="card">
        <h3>سرعت هر قابلیت</h3>
        {data.by_feature.length === 0 ? (
          <p className="muted small">هنوز داده‌ای نیست.</p>
        ) : (
          <div className="usage-table-wrap">
            <table className="usage-table">
              <thead>
                <tr><th>قابلیت</th><th>فراخوانی</th><th>میانه</th><th>۹۵٪ کمتر از</th><th>توکن</th></tr>
              </thead>
              <tbody>
                {data.by_feature.map((f) => (
                  <tr key={f.name}>
                    <td>{FEATURES[f.name] ?? f.name}</td>
                    <td>{fa(f.calls)}</td>
                    <td>{sec(f.p50_seconds)}</td>
                    <td>{sec(f.p95_seconds)}</td>
                    <td>{fa(f.total_tokens)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <h3>سرعت پاسخ‌گویی API</h3>
        <p className="muted small">زمان کل هر درخواست، شامل جستجو که مدل زبانی ندارد.</p>
        {data.endpoints.length === 0 ? (
          <p className="muted small">هنوز درخواستی ثبت نشده.</p>
        ) : (
          <div className="usage-table-wrap">
            <table className="usage-table">
              <thead>
                <tr><th>مسیر</th><th>درخواست</th><th>میانگین</th><th>۹۵٪ کمتر از</th></tr>
              </thead>
              <tbody>
                {data.endpoints.map((e) => (
                  <tr key={e.name}>
                    <td dir="ltr">{e.name}</td>
                    <td>{fa(e.requests)}</td>
                    <td>{ms(e.avg_ms)}</td>
                    <td>{ms(e.p95_ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <h3>آخرین درخواست‌ها</h3>
        <p className="muted small">هر ردیف یک درخواست کاربر است؛ برای دیدن مراحل مدل زبانی بازش کنید.</p>
        {data.requests.length === 0 ? (
          <p className="muted small">هنوز درخواستی ثبت نشده؛ یک جستجو یا گفتگو انجام دهید.</p>
        ) : (
          <div className="req-list">
            {data.requests.slice(0, 25).map((r) => (
              <details className="req-row" key={r.request_id ?? r.time}>
                <summary>
                  <span className={r.status_code >= 400 ? "req-status req-err" : "req-status req-ok"}>
                    {r.status_code >= 400 ? "ناموفق" : "موفق"} · {r.status_code}
                  </span>
                  <bdi dir="ltr" className="req-endpoint">{r.endpoint}</bdi>
                  <span className="muted small">{new Date(r.time * 1000).toLocaleTimeString("fa-IR")}</span>
                  <span>{ms(r.duration_ms)}</span>
                  <strong>
                    {r.status === "not_used" ? "بدون مدل زبانی" : `${fa(r.total_tokens)} توکن${r.complete ? "" : " · ناقص"}`}
                  </strong>
                </summary>
                <p className="small muted">
                  شناسه: <bdi dir="ltr">{r.request_id}</bdi> · ورودی {fa(r.input_tokens)} · خروجی {fa(r.output_tokens)} ·{" "}
                  {fa(r.llm_calls)} فراخوانی مدل
                </p>
                {r.calls.length > 0 && (
                  <div className="usage-table-wrap">
                    <table className="usage-table">
                      <thead>
                        <tr><th>مرحله</th><th>مدل</th><th>ورودی</th><th>خروجی</th><th>ثانیه</th></tr>
                      </thead>
                      <tbody>
                        {r.calls.map((c, i) => (
                          <tr key={i}>
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
              </details>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <h3>آخرین فراخوانی‌های مدل</h3>
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
