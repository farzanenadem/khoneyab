"use client";

import { Filters, FilterOptions, Option, SOURCE_LABELS } from "@/lib/api";

type Props = {
  options: FilterOptions | null;
  filters: Filters;
  onChange: (f: Filters) => void;
  onReset: () => void;
};

type ListKey = "provinces" | "work_types" | "seniority" | "categories" | "sources";

function MultiSelect({
  label,
  options,
  selected,
  onChange,
  limit,
}: {
  label: string;
  options: (Option & { label?: string })[];
  selected: string[];
  onChange: (v: string[]) => void;
  limit?: number;
}) {
  const shown = limit ? options.slice(0, limit) : options;
  const toggle = (value: string) =>
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);
  return (
    <fieldset className="filter-group">
      <legend>{label}</legend>
      <div className="chip-list">
        {shown.map((o) => (
          <button
            type="button"
            key={o.value}
            className={`chip ${selected.includes(o.value) ? "chip-on" : ""}`}
            onClick={() => toggle(o.value)}
            aria-pressed={selected.includes(o.value)}
          >
            {o.label || o.value}
            <span className="chip-count">{o.count.toLocaleString("fa-IR")}</span>
          </button>
        ))}
      </div>
    </fieldset>
  );
}

export default function FiltersPanel({ options, filters, onChange, onReset }: Props) {
  if (!options) return <aside className="filters muted">در حال بارگذاری فیلترها…</aside>;

  const set = <K extends keyof Filters>(key: K, value: Filters[K]) => onChange({ ...filters, [key]: value });
  const list = (key: ListKey) => (v: string[]) => set(key, v);

  return (
    <aside className="filters">
      <div className="filters-head">
        <h2>فیلترها</h2>
        <button type="button" className="link-btn" onClick={onReset}>
          پاک کردن
        </button>
      </div>
      <p className="muted small">
        فیلترها قطعی‌اند؛ ترجیحاتی که در متن می‌نویسید فقط در رتبه‌بندی اثر دارند.
      </p>

      <fieldset className="filter-group">
        <legend>شرایط</legend>
        <label className="check">
          <input type="checkbox" checked={filters.remote_only} onChange={(e) => set("remote_only", e.target.checked)} />
          فقط دورکاری ({options.remote_count.toLocaleString("fa-IR")})
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={filters.internship_only}
            onChange={(e) => set("internship_only", e.target.checked)}
          />
          امکان کارآموزی ({options.internship_count.toLocaleString("fa-IR")})
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={filters.salary_disclosed_only}
            onChange={(e) => set("salary_disclosed_only", e.target.checked)}
          />
          فقط آگهی‌های با حقوق اعلام‌شده ({options.salary_disclosed_count.toLocaleString("fa-IR")})
        </label>
      </fieldset>

      <fieldset className="filter-group">
        <legend>تاریخ انتشار</legend>
        <select
          className="num"
          value={filters.posted_within_days ?? ""}
          onChange={(e) => set("posted_within_days", e.target.value === "" ? null : Number(e.target.value))}
        >
          <option value="">همه آگهی‌های فعال</option>
          <option value="1">۲۴ ساعت اخیر</option>
          <option value="3">۳ روز اخیر</option>
          <option value="7">یک هفته اخیر</option>
          <option value="30">یک ماه اخیر</option>
        </select>
      </fieldset>

      <fieldset className="filter-group">
        <legend>حداکثر سابقه موردنیاز (سال)</legend>
        <input
          type="number"
          min={0}
          max={30}
          className="num"
          value={filters.max_experience_years ?? ""}
          placeholder="بدون محدودیت"
          onChange={(e) => set("max_experience_years", e.target.value === "" ? null : Number(e.target.value))}
        />
      </fieldset>

      <fieldset className="filter-group">
        <legend>حداقل سقف حقوق (میلیون تومان)</legend>
        <input
          type="number"
          min={0}
          className="num"
          value={filters.min_salary ?? ""}
          placeholder="بدون محدودیت"
          onChange={(e) => set("min_salary", e.target.value === "" ? null : Number(e.target.value))}
        />
      </fieldset>

      <MultiSelect
        label="منبع آگهی"
        options={(options.sources || []).map((o) => ({ ...o, label: SOURCE_LABELS[o.value] || o.value }))}
        selected={filters.sources}
        onChange={list("sources")}
      />
      <MultiSelect label="استان" options={options.provinces} selected={filters.provinces} onChange={list("provinces")} limit={14} />
      <MultiSelect label="نوع همکاری" options={options.work_types} selected={filters.work_types} onChange={list("work_types")} />
      <MultiSelect label="سطح ارشدیت" options={options.seniority} selected={filters.seniority} onChange={list("seniority")} />
      <MultiSelect label="دسته‌بندی شغلی" options={options.categories} selected={filters.categories} onChange={list("categories")} limit={20} />
    </aside>
  );
}
