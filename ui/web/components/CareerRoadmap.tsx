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

const TARGET_EXAMPLES = ["تحلیلگر داده", "برنامه‌نویس فرانت‌اند", "مهندس هوش مصنوعی", "حسابدار", "دیجیتال مارکتینگ"];

type SavedState ={ roadmap: SavedRoadmap; inProgressIds: string[] };
type StatusFilter = "all" | "remaining" | "in-progress" | "completed";

const STATUS_FILTERS: { id: StatusFilter; label: string }[] = [
  { id: "all", label: "همه" },
  { id: "remaining", label: "باقی‌مانده" },
  { id: "in-progress", label: "در حال یادگیری" },
  { id: "completed", label: "تکمیل‌شده" },
];

const fa = (n: number) => n.toLocaleString("fa-IR");

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
        setError("برای این شغل آگهی پیدا نشد. عنوان ساده‌تری امتحان کنید؛ مثلاً «برنامه‌نویس» به‌جای «برنامه‌نویس ارشد بک‌اند».");
        return;
      }
      const completed = roadmap?.nodes.filter((node) => node.status === "completed").map((node) => node.id) ?? [];
      const nextInProgress = inProgressIds.filter((id) => !completed.includes(id));
      const nextRoadmap = buildRoadmap(response, profile, completed, nextInProgress);
      setRoadmap(nextRoadmap);
      setInProgressIds(nextInProgress);
      setSelected(null);
    } catch (reason) {
      console.error(reason);
      setError("ارتباط با سرور برقرار نشد. چند لحظه بعد دوباره تلاش کنید.");
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

  function toggleDone(node: RoadmapNode) {
    setNodeStatus(node.id, node.status === "completed" ? "not-started" : "completed");
  }

  const progress = roadmap ? roadmapProgress(roadmap.nodes) : { completed: 0, total: 0, percent: 0 };
  const allNodes = roadmap?.nodes ?? [];
  const nextNode = allNodes.find((node) => node.status !== "completed" && !isBlocked(node, allNodes));
  const activeNodes = allNodes.filter((node) => node.status === "in-progress");
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
    return matchesStatus;
  });

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
          <h2 id="career-title">نقشه مسیر شغلی</h2>
          <p>شغل هدفتان را بگویید؛ از آگهی‌های واقعی می‌فهمیم چه مهارت‌هایی لازم دارید و قدم‌به‌قدم همراهتان هستیم.</p>
        </div>
        {roadmap && (
          <button
            className="career-reset"
            type="button"
            onClick={() => {
              if (progress.completed > 0 && !window.confirm("پیشرفت فعلی پاک می‌شود. نقشه جدید بسازیم؟")) return;
              setRoadmap(null);
              setInProgressIds([]);
              setError(null);
            }}
          >
            نقشه جدید
          </button>
        )}
      </header>

      {!roadmap && (
        <form className="career-form" onSubmit={analyze}>
          <label className="career-field career-field-wide">
            می‌خواهید به چه شغلی برسید؟
            <input required autoFocus value={profile.targetRole} onChange={(event) => updateProfile("targetRole", event.target.value)} placeholder="مثلاً: تحلیلگر داده" />
          </label>
          <div className="career-chips career-field-wide" aria-label="پیشنهادها">
            {TARGET_EXAMPLES.map((role) => (
              <button key={role} type="button" className={profile.targetRole === role ? "career-chip career-chip-on" : "career-chip"} onClick={() => updateProfile("targetRole", role)}>
                {role}
              </button>
            ))}
          </div>
          <label className="career-field career-field-wide">
            چه چیزهایی را الان بلدید؟ <span className="career-optional">اختیاری · با ویرگول جدا کنید</span>
            <input value={profile.skills} onChange={(event) => updateProfile("skills", event.target.value)} placeholder="مثلاً: Python، Excel، Git" />
          </label>
          <details className="career-more career-field-wide">
            <summary>جزئیات بیشتر (اختیاری)</summary>
            <div className="career-more-body">
          <label className="career-field">
            تحصیلات یا پیشینه
            <input value={profile.background} onChange={(event) => updateProfile("background", event.target.value)} placeholder="مثلاً: کارشناسی مهندسی صنایع" />
          </label>
          <label className="career-field">
            نقش یا مرحله فعلی
            <input value={profile.currentRole} onChange={(event) => updateProfile("currentRole", event.target.value)} placeholder="مثلاً: کارشناس فروش، دانشجو" />
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
            </div>
          </details>
          {error && <div className="career-error" role="alert">{error}</div>}
          <div className="career-form-foot">
            <button className="career-submit" type="submit" disabled={stage !== "idle" || !profile.targetRole.trim()}>
              {stage === "searching" ? "در حال بررسی آگهی‌ها…" : "ساخت نقشه راه"}
            </button>
          </div>
        </form>
      )}

      {roadmap && (
        <>
          {error && <div className="career-error" role="alert">{error}</div>}
          <div className="career-summary">
            <div className="career-goal"><span>هدف</span><strong>{roadmap.profile.targetRole}</strong>{profileSummary && <small>{profileSummary}</small>}</div>
            <div className="career-progress-block">
              <div className="career-progress-label"><span>پیشرفت</span><strong>{fa(progress.percent)}٪</strong></div>
              <div className="career-progress-bar" role="progressbar" aria-label="پیشرفت نقشه" aria-valuenow={progress.percent} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${progress.percent}%` }} /></div>
              <small>{fa(progress.completed)} از {fa(progress.total)} گام</small>
            </div>
            <div className="career-summary-stat">
              <span>گام بعدی</span>
              {nextNode ? (
                <button type="button" className="career-next" onClick={() => setSelected(nextNode)}>{nextNode.title} ←</button>
              ) : (
                <strong>🎉 همه گام‌ها تکمیل شد</strong>
              )}
            </div>
          </div>

          <p className="career-market-note">
            <span className="career-live-dot" aria-hidden="true" />
            بر اساس {fa(roadmap.jobs.length)} آگهی واقعی مرتبط با «{roadmap.profile.targetRole}»
            {activeNodes.length > 0 && <> · در حال یادگیری: {activeNodes.slice(0, 2).map((node) => node.title).join("، ")}</>}
          </p>

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
                <h3>مسیر یادگیری</h3>
                <div className="career-chips" role="radiogroup" aria-label="نمایش گام‌ها">
                  {STATUS_FILTERS.map((f) => (
                    <button key={f.id} type="button" role="radio" aria-checked={statusFilter === f.id} className={statusFilter === f.id ? "career-chip career-chip-on" : "career-chip"} onClick={() => setStatusFilter(f.id)}>
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>
              <p className="career-hint">روی دایره بزنید تا گام تکمیل شود؛ روی هر گام بزنید تا جزئیات و منابع را ببینید.</p>
              <div className="career-roadmap">
                <div className="career-phase-label"><span>۱</span><div><strong>مهارت‌هایی که بازار می‌خواهد</strong><small>پرتکرارترها اول</small></div></div>
                <div className="career-track">
                  {visibleNodes.filter((node) => node.phase === "requirements").map((node) => (
                    <RoadmapCard key={node.id} node={node} nodes={roadmap.nodes} onSelect={setSelected} onToggle={toggleDone} />
                  ))}
                </div>
                {visibleNodes.some((node) => node.phase === "practice") && (
                  <>
                    <div className="career-phase-label career-phase-practice"><span>۲</span><div><strong>پروژهٔ عملی</strong><small>برای نمونه‌کار و رزومه</small></div></div>
                    <div className="career-track career-track-practice">
                      {visibleNodes.filter((node) => node.phase === "practice").map((node) => (
                        <RoadmapCard key={node.id} node={node} nodes={roadmap.nodes} onSelect={setSelected} onToggle={toggleDone} />
                      ))}
                    </div>
                  </>
                )}
                {visibleNodes.length === 0 && <div className="career-filter-empty">در این دسته گامی نیست.</div>}
              </div>
            </>
          )}

          <footer className="career-footnote">پیشرفت شما فقط در همین مرورگر ذخیره می‌شود.</footer>
        </>
      )}

      {selected && roadmap && (
        <div className="career-drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelected(null); }}>
          <aside className="career-drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
            <button className="career-drawer-close" type="button" aria-label="بستن جزئیات" onClick={() => setSelected(null)}>×</button>
            <p className="career-kicker">{selected.kind === "project" ? "تمرین پیشنهادی" : selected.kind === "qualification" ? "شرط تحصیلی ثبت‌شده" : "مهارت مشاهده‌شده"}</p>
            <h2 id="drawer-title">{selected.title}</h2>
            <div className="career-drawer-actions">
              {isBlocked(selected, roadmap.nodes) ? (
                <small>اول پیش‌نیازهای زیر را تکمیل کنید.</small>
              ) : (
                <>
                  <button type="button" className={selected.status === "completed" ? "career-act career-act-done" : "career-act career-act-primary"} onClick={() => setNodeStatus(selected.id, selected.status === "completed" ? "not-started" : "completed")}>
                    {selected.status === "completed" ? "✓ تکمیل شد (بازگردانی)" : "✓ تکمیلش کردم"}
                  </button>
                  {selected.status !== "completed" && (
                    <button type="button" className="career-act" onClick={() => setNodeStatus(selected.id, selected.status === "in-progress" ? "not-started" : "in-progress")}>
                      {selected.status === "in-progress" ? "توقف یادگیری" : "شروع یادگیری"}
                    </button>
                  )}
                </>
              )}
            </div>
            {selected.kind === "project" ? (
              <>
                <p>یک نمونه‌کار کوچک مرتبط با «{roadmap.profile.targetRole}» بسازید و مهارت‌هایی را که یاد گرفته‌اید در آن به‌کار ببرید.</p>
                <h3>کِی تمام است؟</h3><p>وقتی پروژه قابل نمایش است، README دارد و می‌توانید درباره‌اش توضیح دهید.</p>
                {selected.prerequisites.length > 0 && <><h3>پیش‌نیازها</h3><ul>{selected.prerequisites.map((id) => <li key={id}>{roadmap.nodes.find((node) => node.id === id)?.title}</li>)}</ul></>}
              </>
            ) : (
              <>
                <p>{selected.kind === "qualification" ? "این شرط تحصیلی در آگهی‌های زیر آمده است." : `در ${fa(selected.count)} از ${fa(selected.totalAds)} آگهی مرتبط خواسته شده.`}</p>
                {selected.alreadyKnown && <p className="career-known-note">این را بلدید؛ کافی است تکمیلش کنید.</p>}
                {selected.kind === "skill" && <><h3>چطور یاد بگیرم؟</h3><p>یک تمرین کوچک با «{selected.title}» انجام دهید؛ وقتی توانستید یک کار مستقل با آن انجام دهید، تمام است.</p></>}
                {selected.resource && <p><a href={selected.resource.url} target="_blank" rel="noopener noreferrer">📘 {selected.resource.label} ↗</a></p>}
                {selected.evidence.length > 0 && <><h3>نمونه آگهی‌ها</h3><ul className="career-evidence-list">{selected.evidence.slice(0, 5).map((job, index) => <li key={`${job.title}-${index}`}>{job.url ? <a href={job.url} target="_blank" rel="noopener noreferrer">{job.title}</a> : job.title}</li>)}</ul></>}
              </>
            )}
          </aside>
        </div>
      )}
    </section>
  );
}

function RoadmapCard({ node, nodes, onSelect, onToggle }: {
  node: RoadmapNode;
  nodes: RoadmapNode[];
  onSelect: (node: RoadmapNode) => void;
  onToggle: (node: RoadmapNode) => void;
}) {
  const state = displayStatus(node, nodes);
  const share = node.totalAds ? Math.round((node.count / node.totalAds) * 100) : 0;
  return (
    <div className={`career-node career-node-${state} career-node-${node.kind}`}>
      <button
        type="button"
        className="career-node-dot"
        aria-label={state === "completed" ? `برگرداندن «${node.title}» به انجام‌نشده` : `علامت تکمیل «${node.title}»`}
        aria-pressed={state === "completed"}
        disabled={state === "blocked"}
        onClick={() => onToggle(node)}
      >
        {state === "completed" ? "✓" : ""}
      </button>
      <button type="button" className="career-node-body" onClick={() => onSelect(node)}>
        <span className="career-node-main">
          <strong>{node.title}</strong>
          <span className="career-node-meta">
            {node.kind === "project" ? "پروژهٔ پیشنهادی" : node.kind === "qualification" ? "شرط تحصیلی" : `در ${fa(share)}٪ آگهی‌ها`}
            {node.alreadyKnown && " · بلدید"}
          </span>
          {node.kind !== "project" && (
            <span className="career-node-bar" aria-hidden="true"><span style={{ width: `${share}%` }} /></span>
          )}
        </span>
        {state !== "not-started" && (
          <span className="career-node-state">{state === "completed" ? "تکمیل‌شده" : state === "in-progress" ? "در حال یادگیری" : "منتظر پیش‌نیاز"}</span>
        )}
        <span className="career-node-open" aria-hidden="true">‹</span>
      </button>
    </div>
  );
}