"use client";

import { FormEvent, useState } from "react";
import JobCard from "@/components/JobCard";
import { ResumeSearchResponse, searchByResume } from "@/lib/api";

export default function ResumePanel() {
  const [file, setFile] = useState<File | null>(null);
  const [topK, setTopK] = useState(10);
  const [data, setData] = useState<ResumeSearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      setData(await searchByResume(file, topK));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const p = data?.profile;
  return (
    <div>
      <form className="search resume-form" onSubmit={submit}>
        <label className={file ? "dropzone dropzone-on" : "dropzone"}>
          <input
            type="file"
            accept=".pdf,.docx,.txt"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            aria-label="فایل رزومه"
          />
          <span className="dz-icon">{file ? "✅" : "📄"}</span>
          <span className="dz-title">{file ? file.name : "فایل رزومه را انتخاب کنید"}</span>
          <span className="muted small">PDF، DOCX یا TXT — حداکثر ۵ مگابایت · ذخیره نمی‌شود 🔒</span>
        </label>
        <div className="search-row">
          <label className="inline">
            تعداد نتایج
            <select value={topK} onChange={(e) => setTopK(Number(e.target.value))}>
              {[10, 20, 30].map((k) => (
                <option key={k} value={k}>
                  {k.toLocaleString("fa-IR")}
                </option>
              ))}
            </select>
          </label>
          <button className="btn btn-primary" type="submit" disabled={!file || loading}>
            {loading ? "در حال تحلیل رزومه…" : "تحلیل رزومه و جستجو"}
          </button>
        </div>
      </form>

      {error && <div className="alert">خطا: {error}</div>}

      {p && data && (
        <div className="results resume-results">
          <div className="understanding">
            <span className="muted small">از رزومه شما:</span>
            {p.roles.slice(0, 2).map((r) => <span key={r} className="u-item">{r}</span>)}
            {p.experience_years !== null && <span className="u-item">{p.experience_years.toLocaleString("fa-IR")} سال سابقه</span>}
            {p.location && <span className="u-item">📍 {p.location}</span>}
            {p.skills.slice(0, 8).map((s) => <span key={s} className="tag">{s}</span>)}
            {p.skills.length > 8 && <span className="tag tag-muted">+{(p.skills.length - 8).toLocaleString("fa-IR")}</span>}
          </div>
          <p className="muted small">{data.results.length.toLocaleString("fa-IR")} آگهی مناسب پیدا شد</p>
          {data.results.length === 0 && <div className="empty">آگهی مرتبطی پیدا نشد.</div>}
          {data.results.map((r) => (
            <JobCard key={r.job.id} result={r} />
          ))}
        </div>
      )}
    </div>
  );
}
