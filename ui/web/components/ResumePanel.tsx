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
        <p className="muted small">
          🔒 رزومه فقط برای همین جستجو و در حافظه سرور پردازش می‌شود؛ ذخیره نمی‌شود و در لاگ‌ها ثبت نمی‌شود.
          برای استخراج مهارت‌ها ممکن است متن آن به مدل زبانی (DeepSeek از طریق Metis) ارسال شود.
        </p>
        <div className="search-row">
          <input
            type="file"
            accept=".pdf,.docx,.txt"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            aria-label="فایل رزومه"
          />
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
        <p className="muted small">فرمت‌های مجاز: PDF، DOCX، TXT (حداکثر ۵ مگابایت؛ PDF اسکن‌شده پشتیبانی نمی‌شود).</p>
      </form>

      {error && <div className="alert">خطا: {error}</div>}

      {p && data && (
        <div className="results resume-results">
          <div className="understanding">
            <span className="muted small">
              پروفایل استخراج‌شده از رزومه ({p.source === "llm" ? "با مدل زبانی، تأییدشده با متن رزومه" : "قاعده‌محور"}):
            </span>
            {p.roles.length > 0 && <span className="u-item"><b>عنوان‌ها:</b> {p.roles.join("، ")}</span>}
            {p.skills.length > 0 && <span className="u-item"><b>مهارت‌ها:</b> {p.skills.join("، ")}</span>}
            {p.experience_years !== null && <span className="u-item"><b>سابقه:</b> {p.experience_years} سال</span>}
            {p.education.length > 0 && <span className="u-item"><b>تحصیلات:</b> {p.education.join("، ")}</span>}
            {p.location && <span className="u-item"><b>مکان:</b> {p.location}</span>}
          </div>
          <p className="muted small">
            عبارت جستجوی ساخته‌شده: «{data.generated_query}»
            {data.live?.enabled && !data.live.error && ` — ${(data.live.new_jobs ?? 0).toLocaleString("fa-IR")} آگهی تازه از سایت‌های کاریابی اضافه شد`}
          </p>
          {data.results.length === 0 && <div className="empty">آگهی مرتبطی پیدا نشد.</div>}
          {data.results.map((r) => (
            <JobCard key={r.job.id} result={r} />
          ))}
        </div>
      )}
    </div>
  );
}
