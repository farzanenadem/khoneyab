import { ParsedQuery } from "@/lib/api";

export default function QueryUnderstanding({ q }: { q: ParsedQuery }) {
  const items: { label: string; value: string }[] = [];
  if (q.concepts.length) items.push({ label: "مهارت‌ها و حوزه‌ها", value: q.concepts.map((c) => c.label).join("، ") });
  if (q.locations.length)
    items.push({ label: q.location_strict ? "مکان (قطعی)" : "مکان ترجیحی", value: q.locations.join("، ") });
  if (q.wants_remote) items.push({ label: "دورکاری", value: "بله" });
  if (q.work_types.length) items.push({ label: "نوع همکاری", value: q.work_types.join("، ") });
  if (q.seniority.length) items.push({ label: "سطح", value: q.seniority.join("، ") });
  if (q.wants_internship) items.push({ label: "کارآموزی", value: "بله" });
  if (q.experience_years !== null) items.push({ label: "سابقه شما", value: `${q.experience_years} سال` });
  if (q.min_salary !== null) items.push({ label: "حداقل حقوق", value: `${q.min_salary} میلیون تومان` });

  if (!items.length) return null;
  return (
    <div className="understanding">
      <span className="muted small">برداشت سیستم از توضیح شما:</span>
      {items.map((it) => (
        <span key={it.label} className="u-item">
          <b>{it.label}:</b> {it.value}
        </span>
      ))}
    </div>
  );
}
