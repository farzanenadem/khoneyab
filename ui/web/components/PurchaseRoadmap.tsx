"use client";

import { useEffect, useMemo, useState } from "react";
import { Roadmap, RoadmapStep, getRoadmap } from "@/lib/homes";
import Icon from "@/components/Icon";

const DONE_KEY = "khoneyab-roadmap-done";
const COND_KEY = "khoneyab-roadmap-conditions";

function load<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return v ? (JSON.parse(v) as T) : fallback;
  } catch {
    return fallback;
  }
}

function save(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: state lives for this visit only */
  }
}

function Step({ s, done, onToggle, levelLabel }: { s: RoadmapStep; done: boolean; onToggle: () => void; levelLabel: string }) {
  return (
    <article className={`card h-step h-lvl-${s.level} ${done ? "h-step-done" : ""}`}>
      <div className="h-step-top">
        <label className="check h-step-head">
          <input type="checkbox" checked={done} onChange={onToggle} />
          <strong>{s.title}</strong>
        </label>
        <span className={`h-level h-level-${s.level}`}>ریسک {levelLabel}</span>
      </div>
      <p className="small h-step-goal">
        {s.goal}
        {s.reveals ? ` — ${s.reveals}` : ""}
      </p>
      <div className="h-step-facts small">
        <span><Icon name="building" size={14} /> {s.authority}</span>
        <span><Icon name="refresh" size={14} /> {s.when}</span>
        <span><Icon name="shield" size={14} /> {s.required}</span>
      </div>
      <details className="h-step-more">
        <summary>جزئیات، اقدام در صورت مشکل و منابع</summary>
        <dl>
          {s.method && (
            <>
              <dt>روش دریافت</dt>
              <dd>{s.method}</dd>
            </>
          )}
          {s.docs && (
            <>
              <dt>مدارک لازم</dt>
              <dd>{s.docs}</dd>
            </>
          )}
          <dt>ریسک انجام‌ندادن</dt>
          <dd>{s.risk}</dd>
          {s.detail && (
            <>
              <dt>شرح و اقدام</dt>
              <dd>{s.detail}</dd>
            </>
          )}
          {s.notes && (
            <>
              <dt>محدودیت‌ها و نکات</dt>
              <dd>{s.notes}</dd>
            </>
          )}
          {s.sources.length > 0 && (
            <>
              <dt>منبع</dt>
              <dd className="h-sources">
                {s.sources.map((src) => (
                  <a key={src.url} href={src.url} target="_blank" rel="noopener noreferrer">
                    {src.label}
                  </a>
                ))}
              </dd>
            </>
          )}
        </dl>
      </details>
    </article>
  );
}

export default function PurchaseRoadmap() {
  const [roadmap, setRoadmap] = useState<Roadmap | null>(null);
  const [done, setDone] = useState<Set<string>>(new Set());
  const [conds, setConds] = useState<Record<string, boolean>>({});
  const [onlyCritical, setOnlyCritical] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getRoadmap()
      .then((r) => {
        setRoadmap(r);
        const defaults = Object.fromEntries(r.conditions.map((c) => [c.id, c.default]));
        setConds({ ...defaults, ...load<Record<string, boolean>>(COND_KEY, {}) });
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    setDone(new Set(load<string[]>(DONE_KEY, [])));
  }, []);

  const toggleDone = (id: string) => {
    const next = new Set(done);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setDone(next);
    save(DONE_KEY, [...next]);
  };

  const toggleCond = (id: string) => {
    const next = { ...conds, [id]: !conds[id] };
    setConds(next);
    save(COND_KEY, next);
  };

  const applies = useMemo(() => (s: RoadmapStep) => !s.condition || conds[s.condition], [conds]);
  const applicable = roadmap?.phases.flatMap((p) => p.steps.filter(applies)) ?? [];

  if (error) return <div className="alert">خطا در دریافت نقشه راه: {error}</div>;
  if (!roadmap) return <div className="empty">در حال بارگذاری…</div>;

  const doneCount = applicable.filter((s) => done.has(s.id)).length;
  const criticalLeft = applicable.filter((s) => s.level === "critical" && !done.has(s.id)).length;
  const pct = applicable.length ? Math.round((doneCount / applicable.length) * 100) : 0;
  const activeSpecial = roadmap.special_cases.filter((c) =>
    roadmap.conditions.some((k) => conds[k.id] && c.title.includes(SPECIAL_HINT[k.id] ?? "\u0000")),
  );

  return (
    <div className="h-roadmap">
      <div className="card h-progress">
        <p className="small">{roadmap.summary}</p>
        <div>
          <strong>{doneCount.toLocaleString("fa-IR")}</strong> از {applicable.length.toLocaleString("fa-IR")} استعلام مربوط به
          معامله شما انجام شده
          {criticalLeft > 0 && <span className="h-level h-level-critical">{criticalLeft.toLocaleString("fa-IR")} مورد بحرانی مانده</span>}
        </div>
        <div className="h-bar">
          <span className="ok" style={{ width: `${pct}%` }} />
        </div>
      </div>

      <section className="card h-conds">
        <h2>معامله شما چه وضعیتی دارد؟</h2>
        <p className="muted small">موارد مربوط را انتخاب کنید تا فقط استعلام‌های لازم برای همین معامله نمایش داده شود.</p>
        <div className="chip-list">
          {roadmap.conditions.map((c) => (
            <button
              key={c.id}
              type="button"
              aria-pressed={!!conds[c.id]}
              className={conds[c.id] ? "chip chip-on" : "chip"}
              onClick={() => toggleCond(c.id)}
            >
              {conds[c.id] ? "✓ " : ""}
              {c.label}
            </button>
          ))}
        </div>
        <label className="check small">
          <input type="checkbox" checked={onlyCritical} onChange={(e) => setOnlyCritical(e.target.checked)} /> فقط موارد با ریسک بحرانی
        </label>
        {activeSpecial.length > 0 && (
          <ul className="h-special small">
            {activeSpecial.map((c) => (
              <li key={c.title}>
                <strong>{c.title}:</strong> {c.text}
              </li>
            ))}
          </ul>
        )}
      </section>

      {roadmap.phases.map((phase, i) => {
        const steps = phase.steps.filter(applies).filter((s) => !onlyCritical || s.level === "critical");
        if (steps.length === 0) return null;
        return (
          <section key={phase.id} className="h-phase">
            <h2>
              <span className="h-phase-num">{(i + 1).toLocaleString("fa-IR")}</span> {phase.title}
              <span className="muted small h-phase-sub">{phase.subtitle}</span>
            </h2>
            {steps.map((s) => (
              <Step key={s.id} s={s} done={done.has(s.id)} onToggle={() => toggleDone(s.id)} levelLabel={roadmap.levels[s.level]} />
            ))}
          </section>
        );
      })}

      <div className="alert h-repeat">🔁 تکرار ضروری: {roadmap.repeat_note}</div>

      <section className="card h-extra">
        <h2>برداشت‌های نادرست رایج</h2>
        <table className="h-table">
          <tbody>
            {roadmap.misconceptions.map((m) => (
              <tr key={m.belief}>
                <th>«{m.belief}»</th>
                <td>{m.why}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card h-extra">
        <h2>پرسش‌هایی که از دفترخانه یا وکیل بپرسید</h2>
        <ol className="small">
          {roadmap.open_questions.map((q) => (
            <li key={q}>{q}</li>
          ))}
        </ol>
      </section>

      <p className="muted small">
        {roadmap.disclaimer} منبع: {roadmap.source}
      </p>
    </div>
  );
}

// Which special-case heading (section 6 of the source) belongs to each condition.
const SPECIAL_HINT: Record<string, string> = {
  inherit: "ارثی",
  poa: "وکالتی",
  under_construction: "در حال ساخت",
  presale: "پیش‌فروش",
  mortgage: "در رهن",
  old_deed: "ثبت ناقص",
  tenant: "مستأجر",
  waqf: "وقفی",
  multi_owner: "چند مالک",
  company: "شرکت",
  land: "روستایی",
};
