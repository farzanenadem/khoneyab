"use client";

import { FormEvent, useEffect, useState } from "react";
import { EMPTY_FILTERS, searchJobs } from "@/lib/api";
import {
  buildRoadmap,
  CareerProfile,
  isBlocked,
  RoadmapNode,
  roadmapProgress,
  SavedRoadmap,
} from "@/lib/roadmap";

const STORAGE_KEY = "rahnama-career-roadmap-v1";
const EMPTY_PROFILE: CareerProfile = {
  background: "",
  currentRole: "",
  skills: "",
  experience: "beginner",
  targetRole: "",
  location: "",
  remote: false,
  hoursPerWeek: 5,
};

type SavedState = { roadmap: SavedRoadmap; inProgressIds: string[] };
type StatusFilter = "all" | "remaining" | "in-progress" | "completed";

function displayStatus(node: RoadmapNode, nodes: RoadmapNode[]) {
  if (isBlocked(node, nodes)) return "blocked";
  return node.status;
}

export default function CareerRoadmap() {
  const [profile, setProfile] = useState(EMPTY_PROFILE);
  const [roadmap, setRoadmap] = useState<SavedRoadmap | null>(null);
  const [inProgressIds, setInProgressIds] = useState<string[]>([]);
  const [selected, setSelected] = useState<RoadmapNode | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [phaseFilter, setPhaseFilter] = useState("all");
  const [stage, setStage] = useState<"idle" | "searching">("idle");
  const [error, setError] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as SavedState;
        if (parsed.roadmap?.profile && Array.isArray(parsed.roadmap.nodes)) {
          setRoadmap(parsed.roadmap);
          setProfile(parsed.roadmap.profile);
          setInProgressIds(Array.isArray(parsed.inProgressIds) ? parsed.inProgressIds : []);
        }
      }
    } catch {
      localStorage.removeItem(STORAGE_KEY);
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    if (!roadmap) {
      localStorage.removeItem(STORAGE_KEY);
      return;
    }
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ roadmap, inProgressIds } satisfies SavedState));
    } catch {
      setError("ذخیره‌سازی محلی در این مرورگر در دسترس نیست.");
    }
  }, [hydrated, roadmap, inProgressIds]);

  const updateProfile = (field: keyof CareerProfile, value: string | boolean | number) => {
    setProfile((current) => ({ ...current, [field]: value }));
  };

  async function analyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!profile.targetRole.trim()) {
      setError("عنوان شغل هدف را وارد کنید.");
      return;
    }
    setError(null);
    setStage("searching");
    try {
      const query = [profile.targetRole.trim(), profile.location.trim(), profile.remote ? "دورکاری" : ""]
        .filter(Boolean)
        .join(" ");
      const response = await searchJobs(query, EMPTY_FILTERS, 50, "hybrid", "relevance");
      if (!response.results?.length) {
        setError("برای این عنوان آگهی مرتبطی در نتایج جستجو پیدا نشد. عنوان یا موقعیت را تغییر دهید و دوباره تلاش کنید.");
        return;
      }
      const completed = roadmap?.nodes.filter((node) => node.status === "completed").map((node) => node.id) ?? [];
      const nextInProgress = inProgressIds.filter((id) => !completed.includes(id));
      const nextRoadmap = buildRoadmap(response, profile, completed, nextInProgress);
      setRoadmap(nextRoadmap);
      setInProgressIds(nextInProgress);
      setSelected(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setStage("idle");
    }
  }

  function setNodeStatus(id: string, status: RoadmapNode["status"]) {
    setRoadmap((current) => current && ({
      ...current,
      nodes: current.nodes.map((node) => node.id === id ? { ...node, status } : node),
    }));
    setInProgressIds((current) => status === "in-progress"
      ? [...new Set([...current, id])]
      : current.filter((value) => value !== id));
    setSelected((current) => current?.id === id ? { ...current, status } : current);
  }

  const progress = roadmap ? roadmapProgress(roadmap.nodes) : { completed: 0, total: 0, percent: 0 };
  const allNodes = roadmap?.nodes ?? [];
  const nextNode = allNodes.find((node) => node.status !== "completed" && !isBlocked(node, allNodes));
  const activeNodes = allNodes.filter((node) => node.status === "in-progress");
  const completedProjects = allNodes.filter((node) => node.kind === "project" && node.status === "completed").length;
  const requirementNodes = allNodes.filter((node) => node.kind !== "project");
  const experienceLabel = roadmap?.profile.experience === "beginner" ? "تازه‌کار"
    : roadmap?.profile.experience === "some" ? "کمی تجربه"
      : "باتجربه";
  const profileSummary = roadmap ? [
    roadmap.profile.currentRole,
    roadmap.profile.background,
    `سطح تجربه: ${experienceLabel}`,
    roadmap.profile.location ? `موقعیت: ${roadmap.profile.location}` : "",
    roadmap.profile.remote ? "دورکاری هم مناسب است" : "",
  ].filter(Boolean).join(" · ") : "";
  const visibleNodes = allNodes.filter((node) => {
    const state = displayStatus(node, allNodes);
    const matchesStatus = statusFilter === "all"
      || (statusFilter === "remaining" && state !== "completed")
      || state === statusFilter;
    const matchesPhase = phaseFilter === "all" || node.phase === phaseFilter;
    return matchesStatus && matchesPhase;
  }) ?? [];

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setSelected(null);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <section className="career-shell" aria-labelledby="career-title">
      <header className="career-heading">
        <div>
          <p className="career-kicker">بر پایه آگهی‌های واقعی جاب‌ویژن</p>
          <h2 id="career-title">نقشه مسیر شغلی</h2>
          <p>مهارت‌های موردنیاز نقش هدفتان را از آگهی‌های مرتبط پیدا کنید و پیشرفتتان را دنبال کنید.</p>
        </div>
        {roadmap && <button className="career-reset" type="button" onClick={() => { setRoadmap(null); setInProgressIds([]); setError(null); }}>نقشه جدید</button>}
      </header>

      {!roadmap && (
        <form className="career-form" onSubmit={analyze}>
          <div className="career-form-title">
            <h3>از کجا شروع کنیم؟</h3>
            <button type="button" className="career-example" onClick={() => setProfile({
              background: "کارشناسی علوم کامپیوتر",
              currentRole: "تازه‌کار در هوش مصنوعی",
              skills: "Python، Git",
              experience: "beginner",
              targetRole: "مهندس هوش مصنوعی",
              location: "",
              remote: false,
              hoursPerWeek: 5,
            })}>بارگذاری نمونه</button>
          </div>
          <label className="career-field career-field-wide">
            شغل هدف <span aria-hidden="true">*</span>
            <input required value={profile.targetRole} onChange={(event) => updateProfile("targetRole", event.target.value)} placeholder="مثلاً: تحلیلگر داده" />
          </label>
          <label className="career-field">
            تحصیلات یا پیشینه
            <input value={profile.background} onChange={(event) => updateProfile("background", event.target.value)} placeholder="مثلاً: کارشناسی مهندسی صنایع" />
          </label>
          <label className="career-field">
            نقش یا مرحله فعلی
            <input value={profile.currentRole} onChange={(event) => updateProfile("currentRole", event.target.value)} placeholder="مثلاً: کارشناس فروش، دانشجو" />
          </label>
          <label className="career-field career-field-wide">
            مهارت‌ها و ابزارهایی که بلدید
            <input value={profile.skills} onChange={(event) => updateProfile("skills", event.target.value)} placeholder="با ویرگول جدا کنید؛ مثلاً: Python، Git" />
          </label>
          <label className="career-field">
            میزان تجربه در این حوزه
            <select value={profile.experience} onChange={(event) => updateProfile("experience", event.target.value)}>
              <option value="beginner">تازه‌کار</option>
              <option value="some">کمی تجربه دارم</option>
              <option value="experienced">باتجربه</option>
            </select>
          </label>
          <label className="career-field">
            زمان یادگیری در هفته
            <span className="career-hours"><input type="number" min="1" max="80" value={profile.hoursPerWeek} onChange={(event) => updateProfile("hoursPerWeek", Number(event.target.value))} /><span>ساعت</span></span>
          </label>
          <label className="career-field">
            موقعیت دلخواه <span className="career-optional">اختیاری</span>
            <input value={profile.location} onChange={(event) => updateProfile("location", event.target.value)} placeholder="مثلاً: تهران" />
          </label>
          <label className="career-check">
            <input type="checkbox" checked={profile.remote} onChange={(event) => updateProfile("remote", event.target.checked)} />
            دورکاری هم مناسب است
          </label>
          {error && <div className="career-error" role="alert">{error}</div>}
          <div className="career-form-foot">
            <p>پیشینه و زمان یادگیری برای شخصی‌سازی نمایش استفاده می‌شود؛ جستجو بر اساس شغل هدف انجام می‌شود.</p>
            <button className="career-submit" type="submit" disabled={stage !== "idle"}>
              {stage === "searching" ? "در حال جستجوی آگهی‌ها…" : "تحلیل بازار و ساخت نقشه"}
            </button>
          </div>
        </form>
      )}

      {roadmap && (
        <>
          {error && <div className="career-error" role="alert">{error}</div>}
          <div className="career-summary">
            <div className="career-goal"><span>هدف</span><strong>{roadmap.profile.targetRole}</strong><small>{profileSummary || "پیشینه وارد نشده"}</small></div>
            <div className="career-progress-block">
              <div className="career-progress-label"><span>پیشرفت نقشه</span><strong>{progress.percent}٪</strong></div>
              <div className="career-progress-bar" role="progressbar" aria-label="پیشرفت نقشه" aria-valuenow={progress.percent} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${progress.percent}%` }} /></div>
              <small>{progress.completed} از {progress.total} گام</small>
            </div>
            <div className="career-summary-stat"><span>گام بعدی</span><strong>{nextNode?.title ?? "همه گام‌ها تکمیل شد"}</strong></div>
          </div>

          <div className="career-market-note">
            <span className="career-live-dot" />
            <div><strong>{roadmap.jobs.length} آگهی مرتبط</strong><span> از {roadmap.totalCandidates} نتیجه کاندیدا بررسی شد. تکرار مهارت‌ها فقط شمارش در همین نمونه است؛ آگهی‌ها سطح «ضروری» را از «ترجیحی» جدا نمی‌کنند.</span></div>
            <span className="career-market-date">{roadmap.profile.hoursPerWeek} ساعت در هفته</span>
          </div>

          <div className="career-metrics" aria-label="وضعیت فعلی">
            <div><span>در حال یادگیری</span><strong>{activeNodes.length}</strong><small>{activeNodes.slice(0, 2).map((node) => node.title).join("، ") || "هنوز گامی شروع نشده"}</small></div>
            <div><span>پروژه‌های تکمیل‌شده</span><strong>{completedProjects}</strong><small>از {roadmap.nodes.filter((node) => node.kind === "project").length} تمرین پیشنهادی</small></div>
            <div><span>مهارت‌های پرتکرارِ باقی‌مانده</span><strong>{requirementNodes.filter((node) => !node.alreadyKnown && node.count > 1 && node.status !== "completed").length}</strong><small>در بیش از یک آگهی دیده شده</small></div>
          </div>

          {requirementNodes.length === 0 && (
            <div className="career-insufficient">
              <h3>برای ساخت نقشه، جزئیات بیشتری لازم است</h3>
              <p>{roadmap.jobs.length} آگهی برگشت، اما مهارت یا شرایط ساختاریافته‌ای در آن‌ها ثبت نشده بود. بنابراین هیچ مهارتی را حدس نمی‌زنیم.</p>
              <p>آگهی‌های نمونه:</p>
              <ul>{roadmap.jobs.slice(0, 5).map((job, index) => <li key={`${job.title}-${index}`}>{job.url ? <a href={job.url} target="_blank" rel="noopener noreferrer">{job.title}</a> : job.title}</li>)}</ul>
            </div>
          )}

          {requirementNodes.length > 0 && (
            <>
              <div className="career-roadmap-head">
                <div><h3>مسیر یادگیری</h3><span>{roadmap.nodes.length} گام بر اساس داده‌های موجود</span></div>
                <div className="career-filters">
                  <label><span className="sr-only">فیلتر وضعیت</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}>
                    <option value="all">همه وضعیت‌ها</option><option value="remaining">باقی‌مانده</option><option value="in-progress">در حال یادگیری</option><option value="completed">تکمیل‌شده</option>
                  </select></label>
                  <label><span className="sr-only">فیلتر مرحله</span><select value={phaseFilter} onChange={(event) => setPhaseFilter(event.target.value)}>
                    <option value="all">همه مرحله‌ها</option><option value="requirements">مهارت‌ها و شرایط</option><option value="practice">تمرین</option>
                  </select></label>
                </div>
              </div>
              <div className="career-roadmap">
                <div className="career-phase-label"><span>۰۱</span><div><strong>نیازهای مشاهده‌شده در بازار</strong><small>به ترتیب تکرار در آگهی‌ها؛ پیش‌نیاز بین مهارت‌ها در داده‌ها مشخص نشده</small></div></div>
                <div className="career-track">
                  {visibleNodes.filter((node) => node.phase === "requirements").map((node) => (
                    <RoadmapCard key={node.id} node={node} nodes={roadmap.nodes} onSelect={setSelected} />
                  ))}
                </div>
                {visibleNodes.some((node) => node.phase === "practice") && (
                  <>
                    <div className="career-phase-label career-phase-practice"><span>۰۲</span><div><strong>کاربرد عملی</strong><small>پیشنهاد عمومی برای تمرین مهارت‌های هدف</small></div></div>
                    <div className="career-track career-track-practice">
                      {visibleNodes.filter((node) => node.phase === "practice").map((node) => (
                        <RoadmapCard key={node.id} node={node} nodes={roadmap.nodes} onSelect={setSelected} />
                      ))}
                    </div>
                  </>
                )}
                {visibleNodes.length === 0 && <div className="career-filter-empty">گامی با این فیلترها وجود ندارد.</div>}
              </div>
            </>
          )}

          <footer className="career-footnote">مهارت‌ها و شرایط از فیلدهای ساختاریافته آگهی‌های برگشتی استخراج شده‌اند. تمرین پروژه‌ای پیشنهاد عمومی است، نه الزام اعلام‌شده از سوی کارفرما. وضعیت پیشرفت فقط در همین مرورگر ذخیره می‌شود.</footer>
        </>
      )}

      {selected && roadmap && (
        <div className="career-drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelected(null); }}>
          <aside className="career-drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
            <button className="career-drawer-close" type="button" aria-label="بستن جزئیات" onClick={() => setSelected(null)}>×</button>
            <p className="career-kicker">{selected.kind === "project" ? "تمرین پیشنهادی" : selected.kind === "qualification" ? "شرط تحصیلی ثبت‌شده" : "مهارت مشاهده‌شده"}</p>
            <h2 id="drawer-title">{selected.title}</h2>
            {selected.kind === "project" ? (
              <>
                <p>یک نمونه‌کار مرتبط با {roadmap.profile.targetRole} بسازید و مهارت‌های در حال یادگیری را در آن به‌کار ببرید. نوع پروژه از آگهی‌ها استنتاج نشده است.</p>
                <h3>معیار تکمیل</h3><p>نمونه‌کار قابل ارائه باشد، README داشته باشد و بتوانید تصمیم‌های فنی و نتیجه را توضیح دهید.</p>
                {selected.prerequisites.length > 0 && <><h3>پیش‌نیازهای پیشنهادی</h3><ul>{selected.prerequisites.map((id) => <li key={id}>{roadmap.nodes.find((node) => node.id === id)?.title}</li>)}</ul></>}
              </>
            ) : (
              <>
                <p>{selected.kind === "qualification" ? "این شرط در اطلاعات تحصیلی آگهی‌های زیر ثبت شده است؛ وضعیت خود را بررسی کنید." : `این مهارت در ${selected.count} مورد از ${selected.totalAds} آگهی برگشتی دیده شده است و می‌تواند برای نقش «${roadmap.profile.targetRole}» مرتبط باشد.`}</p>
                {selected.alreadyKnown && <p className="career-known-note">این مورد با مهارت‌هایی که وارد کردید هم‌پوشانی دارد؛ نیازی به شروع دوباره نیست.</p>}
                {selected.kind === "skill" && <><h3>تمرین پیشنهادی</h3><p>یک تمرین کوچک با «{selected.title}» انجام دهید و خروجی را طوری مستند کنید که بتوانید روش کارتان را توضیح دهید.</p><h3>معیار تکمیل</h3><p>بتوانید یک کار مستقل با این مهارت انجام دهید، نتیجه را بررسی کنید و محدودیت‌های راه‌حل را شرح دهید.</p></>}
                {selected.resource && <><h3>منبع رسمی</h3><a href={selected.resource.url} target="_blank" rel="noopener noreferrer">{selected.resource.label} ↗</a></>}
                {selected.evidence.length > 0 && <><h3>شواهد از آگهی‌ها</h3><ul className="career-evidence-list">{selected.evidence.map((job, index) => <li key={`${job.title}-${index}`}>{job.url ? <a href={job.url} target="_blank" rel="noopener noreferrer">{job.title}</a> : job.title}</li>)}</ul></>}
                <h3>زمان یادگیری</h3><p>{roadmap.profile.hoursPerWeek} ساعت در هفته در پروفایل شما ثبت شده؛ زمان لازم برای این مهارت در داده‌های آگهی‌ها مشخص نیست.</p>
              </>
            )}
            <div className="career-drawer-actions">
              <label className="career-complete-toggle">
                <input type="checkbox" checked={selected.status === "completed"} disabled={isBlocked(selected, roadmap.nodes)} onChange={(event) => setNodeStatus(selected.id, event.target.checked ? "completed" : "not-started")} />
                این گام را تکمیل کردم
              </label>
              {selected.status !== "completed" && <button type="button" disabled={isBlocked(selected, roadmap.nodes)} onClick={() => setNodeStatus(selected.id, selected.status === "in-progress" ? "not-started" : "in-progress")}>{selected.status === "in-progress" ? "توقف یادگیری" : "شروع یادگیری"}</button>}
              {isBlocked(selected, roadmap.nodes) && <small>پس از تکمیل پیش‌نیازهای پیشنهادی فعال می‌شود.</small>}
            </div>
          </aside>
        </div>
      )}
    </section>
  );
}

function RoadmapCard({ node, nodes, onSelect }: { node: RoadmapNode; nodes: RoadmapNode[]; onSelect: (node: RoadmapNode) => void }) {
  const state = displayStatus(node, nodes);
  return (
    <button className={`career-node career-node-${state} career-node-${node.kind}`} type="button" onClick={() => onSelect(node)}>
      <span className="career-node-dot" aria-hidden="true">{state === "completed" ? "✓" : state === "blocked" ? "–" : ""}</span>
      <span className="career-node-main">
        <span className="career-node-label">{node.kind === "qualification" ? "شرط تحصیلی" : node.kind === "project" ? "پروژه" : "مهارت"}{node.alreadyKnown ? " · آشنا هستید" : ""}</span>
        <strong>{node.title}</strong>
        <span className="career-node-meta">{node.kind === "project" ? "تمرین پیشنهادی عمومی" : `در ${node.count} از ${node.totalAds} آگهی`}</span>
      </span>
      <span className="career-node-state">{state === "completed" ? "تکمیل‌شده" : state === "in-progress" ? "در حال یادگیری" : state === "blocked" ? "در انتظار پیش‌نیاز" : node.count > 1 ? "پرتکرار در نمونه" : "در یک آگهی"}</span>
      <span className="career-node-open" aria-hidden="true">‹</span>
    </button>
  );
}