"use client";

import { useState } from "react";
import { SearchResult } from "@/lib/api";

const BREAKDOWN_LABELS: Record<string, string> = {
  semantic: "شباهت معنایی",
  lexical: "تطابق واژگانی (BM25)",
  concept: "پوشش مهارت‌ها",
  preference: "ترجیحات",
  recency: "تازگی آگهی",
  keyword: "هم‌پوشانی واژه‌ها",
};

function ago(iso: string) {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (Number.isNaN(days)) return "";
  if (days <= 0) return "امروز";
  if (days === 1) return "دیروز";
  return `${days.toLocaleString("fa-IR")} روز پیش`;
}

function faDate(iso: string) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("fa-IR", { year: "numeric", month: "long", day: "numeric" });
  } catch {
    return "";
  }
}

function Highlight({ text, term }: { text: string; term: string }) {
  // Evidence is already a verbatim quote; highlighting is best-effort on the raw text.
  const idx = term ? text.toLowerCase().indexOf(term.toLowerCase()) : -1;
  if (idx < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, idx)}
      <mark>{text.slice(idx, idx + term.length)}</mark>
      {text.slice(idx + term.length)}
    </>
  );
}

export default function JobCard({ result }: { result: SearchResult }) {
  const { job, explanation, score, score_breakdown, rank } = result;
  const [open, setOpen] = useState(false);
  const place = [job.city, job.province].filter(Boolean).join("، ");
  const skills = [...job.skills, ...job.software.map((s) => (s.level ? `${s.name} (${s.level})` : s.name))];

  return (
    <article className="card">
      <header className="card-head">
        <div className="rank">{rank.toLocaleString("fa-IR")}</div>
        <div className="card-title">
          <h3>
            <a href={job.url} target="_blank" rel="noopener noreferrer">
              {job.title}
            </a>
          </h3>
          <div className="company">
            {job.company_url ? (
              <a href={job.company_url} target="_blank" rel="noopener noreferrer">
                {job.company || "نام شرکت ذکر نشده"}
              </a>
            ) : (
              job.company || "نام شرکت ذکر نشده"
            )}
          </div>
        </div>
        <div className="score" title="امتیاز نهایی رتبه‌بندی (۰ تا ۱)">
          {(score * 100).toFixed(0)}
          <span>٪</span>
        </div>
      </header>

      <div className="meta">
        {place && <span className="tag">📍 {place}</span>}
        {job.is_remote && <span className="tag tag-green">امکان دورکاری</span>}
        {job.is_internship && <span className="tag tag-green">کارآموزی</span>}
        {job.work_type && <span className="tag">{job.work_type}</span>}
        {job.seniority && <span className="tag">{job.seniority}</span>}
        {job.required_experience_years !== null && (
          <span className="tag">سابقه: {job.required_experience_years.toLocaleString("fa-IR")} سال</span>
        )}
        <span className="tag">{job.salary_text ? `💰 ${job.salary_text}` : "حقوق اعلام نشده"}</span>
        {job.date_posted && (
          <span className="tag tag-muted" title={faDate(job.date_posted)}>
            🕒 {ago(job.date_posted)}
          </span>
        )}
      </div>

      <section className="why">
        <h4>چرا این آگهی؟</h4>
        <p>{explanation.summary}</p>
        {explanation.matched.length > 0 && (
          <ul className="evidence">
            {explanation.matched.map((m, i) => (
              <li key={i}>
                <span className="ev-concept">{m.concept}</span>
                <span className="ev-field">{m.field_label}:</span>
                <q>
                  <Highlight text={m.evidence} term={m.matched_term} />
                </q>
              </li>
            ))}
          </ul>
        )}
        {explanation.preferences.length > 0 && (
          <ul className="prefs">
            {explanation.preferences.map((p, i) => (
              <li key={i} className={p.ok === true ? "ok" : p.ok === false ? "no" : "unknown"}>
                <span aria-hidden>{p.ok === true ? "✔" : p.ok === false ? "✖" : "?"}</span> {p.text}
              </li>
            ))}
          </ul>
        )}
        {explanation.missing.length > 0 && (
          <p className="missing">
            در آگهی ذکر نشده: {explanation.missing.map((m) => `«${m}»`).join("، ")}
          </p>
        )}
      </section>

      <footer className="card-foot">
        <a className="btn" href={job.url} target="_blank" rel="noopener noreferrer">
          مشاهده آگهی در جاب‌ویژن ↗
        </a>
        <button type="button" className="link-btn" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? "بستن جزئیات" : "جزئیات آگهی"}
        </button>
      </footer>

      {open && (
        <div className="details">
          {job.categories.length > 0 && (
            <p>
              <b>دسته‌بندی:</b> {job.categories.join("، ")}
            </p>
          )}
          {job.industry && (
            <p>
              <b>صنعت:</b> {job.industry}
            </p>
          )}
          {skills.length > 0 && (
            <p>
              <b>مهارت‌ها و نرم‌افزارها:</b> {skills.join("، ")}
            </p>
          )}
          {job.languages.length > 0 && (
            <p>
              <b>زبان:</b> {job.languages.map((l) => `${l.name} ${l.level}`).join("، ")}
            </p>
          )}
          {job.benefits.length > 0 && (
            <p>
              <b>مزایا:</b> {job.benefits.join("، ")}
            </p>
          )}
          {job.gender && (
            <p>
              <b>جنسیت:</b> {job.gender}
            </p>
          )}
          {job.work_days && (
            <p>
              <b>ساعت کاری:</b> {job.work_days}
            </p>
          )}
          {job.description ? (
            <div className="desc">{job.description}</div>
          ) : (
            <p className="muted">شرح کامل این آگهی در دسترس نیست؛ برای جزئیات به آگهی اصلی مراجعه کنید.</p>
          )}
          <div className="breakdown">
            {Object.entries(score_breakdown).map(([k, v]) => (
              <span key={k}>
                {BREAKDOWN_LABELS[k] || k}: {v.toFixed(3)}
              </span>
            ))}
          </div>
        </div>
      )}
    </article>
  );
}
