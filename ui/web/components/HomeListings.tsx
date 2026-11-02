"use client";

import { useEffect, useState } from "react";
import { HomeOptions, Listing, ListingQuery, ListingResponse, ListingSort, searchHomes, toman } from "@/lib/homes";
import Icon from "@/components/Icon";

const BILLION = 1e9;

export function ListingCard({ r, onPickPrice }: { r: Listing; onPickPrice: (p: number) => void }) {
  return (
    <article className="card h-card">
      {r.image_url ? <img src={r.image_url} alt="" loading="lazy" /> : <div className="h-noimg"><Icon name="home" size={42} /></div>}
      <div className="h-body">
        <div className="h-card-topline"><span className="h-card-type"><Icon name="building" size={13} /> آگهی فروش</span><span className="h-card-source">دیوار</span></div>
        <h3 className="h-title">{r.title}</h3>
        <div className="muted small">
          <Icon name="pin" size={14} /> {r.city}
          {r.district ? `، ${r.district}` : ""}
        </div>
        <div className="h-price">{r.price_toman ? toman(r.price_toman) : r.price_text || "توافقی"}</div>
        <div className="h-meta">
          {r.area_m2 && <span className="tag">{r.area_m2.toLocaleString("fa-IR")} متر</span>}
          {r.rooms && <span className="tag">{r.rooms.toLocaleString("fa-IR")} خواب</span>}
          {r.price_per_m2 && <span className="tag tag-muted">متری {toman(r.price_per_m2)}</span>}
        </div>
        <div className="h-actions">
          <a className="btn" href={r.url} target="_blank" rel="noopener noreferrer">
            مشاهده در دیوار <Icon name="external" size={14} />
          </a>
          {r.price_toman && (
            <button className="btn btn-primary" type="button" onClick={() => onPickPrice(r.price_toman!)}>
              <Icon name="calculator" size={15} /> محاسبه وام
            </button>
          )}
        </div>
      </div>
    </article>
  );
}

export default function HomeListings({ options, onPickPrice }: { options: HomeOptions | null; onPickPrice: (p: number) => void }) {
  const [q, setQ] = useState<ListingQuery>({ sort: "newest" });
  const [data, setData] = useState<ListingResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const updateQuery = (patch: Partial<ListingQuery>) => setQ((current) => ({ ...current, ...patch, offset: 0 }));

  useEffect(() => {
    const t = setTimeout(() => {
      setLoading(true);
      setError(null);
      searchHomes(q).then(setData).catch((e) => setError(e instanceof Error ? e.message : String(e))).finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  const num = (v: string, scale = 1) => (v ? Number(v) * scale : undefined);

  return (
    <div className="h-layout">
      <aside className="h-filters card">
        <label>
          جستجو در عنوان و محله
          <input placeholder="مثلاً: نوساز، پارکینگ، ونک" onChange={(e) => updateQuery({ q: e.target.value })} />
        </label>
        <label>
          شهر
          <select value={q.city ?? ""} onChange={(e) => updateQuery({ city: e.target.value || undefined })}>
            <option value="">همه شهرها</option>
            {options?.cities.map((c) => (
              <option key={c.city} value={c.city}>
                {c.city} ({c.count.toLocaleString("fa-IR")})
              </option>
            ))}
          </select>
        </label>
        <div className="h-row">
          <label>
            حداقل قیمت (میلیارد)
            <input type="number" min={0} step={0.5} onChange={(e) => updateQuery({ min_price: num(e.target.value, BILLION) })} />
          </label>
          <label>
            حداکثر قیمت (میلیارد)
            <input type="number" min={0} step={0.5} onChange={(e) => updateQuery({ max_price: num(e.target.value, BILLION) })} />
          </label>
        </div>
        <div className="h-row">
          <label>
            حداقل متراژ
            <input type="number" min={0} onChange={(e) => updateQuery({ min_area: num(e.target.value) })} />
          </label>
          <label>
            حداکثر متراژ
            <input type="number" min={0} onChange={(e) => updateQuery({ max_area: num(e.target.value) })} />
          </label>
        </div>
        <label>
          تعداد خواب
          <select onChange={(e) => updateQuery({ rooms: num(e.target.value) })}>
            <option value="">فرقی ندارد</option>
            {[1, 2, 3, 4].map((n) => (
              <option key={n} value={n}>
                {n.toLocaleString("fa-IR")} خواب
              </option>
            ))}
          </select>
        </label>
        <label>
          مرتب‌سازی
          <select value={q.sort} onChange={(e) => updateQuery({ sort: e.target.value as ListingSort })}>
            <option value="newest">جدیدترین</option>
            <option value="price_asc">ارزان‌ترین</option>
            <option value="price_desc">گران‌ترین</option>
            <option value="price_per_m2">کمترین قیمت هر متر</option>
          </select>
        </label>
        <p className="muted small">آگهی‌های نمونه از دیوار؛ متراژ و تعداد خواب از عنوان آگهی استخراج شده و ممکن است ناقص باشد.</p>
      </aside>

      <section className="results" aria-live="polite" aria-busy={loading}>
        {loading && <div className="h-loading"><span className="loading-dots"><i /><i /><i /></span> در حال به‌روزرسانی آگهی‌ها…</div>}
        {error && <div className="alert">خطا در دریافت آگهی‌ها: {error}</div>}
        {data && (
          <p className="muted small">
            {data.total.toLocaleString("fa-IR")} آگهی
            {data.median_price_per_m2 ? ` · میانه قیمت هر متر: ${toman(data.median_price_per_m2)}` : ""}
          </p>
        )}
        {data?.total === 0 && <div className="empty"><span className="empty-icon"><Icon name="search" size={30} /></span><strong>آگهی‌ای پیدا نشد</strong><span>فیلترها را کمی بازتر کن تا گزینه‌های بیشتری ببینیم.</span></div>}
        <div className="h-grid">
          {data?.results.map((r) => (
            <ListingCard key={r.id} r={r} onPickPrice={onPickPrice} />
          ))}
        </div>
        {data?.next_offset !== null && data?.next_offset !== undefined && (
          <button className="btn" type="button" onClick={() => setQ({ ...q, offset: data.next_offset! })}>
            آگهی‌های بیشتر
          </button>
        )}
      </section>
    </div>
  );
}
