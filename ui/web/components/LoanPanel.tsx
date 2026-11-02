"use client";

import { useEffect, useState } from "react";
import { LoanCatalog, LoanOverride, Plan, getLoans, planLoans, toman } from "@/lib/homes";
import Icon from "@/components/Icon";

const MILLION = 1e6;

export default function LoanPanel({ price, cities }: { price: number; cities: string[] }) {
  const [form, setForm] = useState({
    price,
    savings: 3_000 * MILLION,
    monthly_income: 60 * MILLION,
    city: "تهران",
    married: true,
    has_child: false,
    first_home: true,
  });
  const [catalog, setCatalog] = useState<LoanCatalog | null>(null);
  const [overrides, setOverrides] = useState<Record<string, LoanOverride>>({});
  const [plan, setPlan] = useState<Plan | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setForm((f) => ({ ...f, price })), [price]);

  useEffect(() => {
    getLoans(form.city, form.married)
      .then((c) => {
        setCatalog(c);
        // New city/marital status changes the caps: reset amounts but keep which loans are picked.
        setOverrides((o) =>
          Object.fromEntries(c.loans.map((l) => [l.id, { id: l.id, selected: o[l.id]?.selected ?? l.id !== "commercial" }])),
        );
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [form.city, form.married]);

  useEffect(() => {
    if (!catalog || form.price <= 0) return;
    const t = setTimeout(() => {
      planLoans({ ...form, loans: Object.values(overrides) })
        .then((p) => {
          setPlan(p);
          setError(null);
        })
        .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    }, 200);
    return () => clearTimeout(t);
  }, [form, overrides, catalog]);

  const setO = (id: string, patch: Partial<LoanOverride>) => setOverrides((o) => ({ ...o, [id]: { ...o[id], ...patch } }));
  const mil = (n: number) => Math.round(n / MILLION);
  const planById = Object.fromEntries((plan?.loans ?? []).map((l) => [l.id, l]));
  const dti = plan?.debt_to_income_pct ?? 0;

  return (
    <div className="h-loans">
      <section className="card h-loan-form">
        <div className="section-heading"><span className="section-icon"><Icon name="calculator" size={18} /></span><div><h2>اطلاعات خرید شما</h2><p>چند عدد ساده برای برآورد واقعی‌تر</p></div></div>
        <div className="h-row">
          <label>
            قیمت خانه (میلیون تومان)
            <input type="number" min={0} value={mil(form.price)} onChange={(e) => setForm({ ...form, price: Number(e.target.value) * MILLION })} />
          </label>
          <label>
            پس‌انداز نقد (میلیون تومان)
            <input type="number" min={0} value={mil(form.savings)} onChange={(e) => setForm({ ...form, savings: Number(e.target.value) * MILLION })} />
          </label>
          <label>
            درآمد ماهانه خانوار (میلیون تومان)
            <input
              type="number"
              min={0}
              value={mil(form.monthly_income)}
              onChange={(e) => setForm({ ...form, monthly_income: Number(e.target.value) * MILLION })}
            />
          </label>
          <label>
            شهر
            <select value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })}>
              {Array.from(new Set(["تهران", ...cities, "سایر شهرها"])).map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="h-checks">
          <label className="check">
            <input type="checkbox" checked={form.married} onChange={(e) => setForm({ ...form, married: e.target.checked })} /> متأهل (زوجین)
          </label>
          <label className="check">
            <input type="checkbox" checked={form.first_home} onChange={(e) => setForm({ ...form, first_home: e.target.checked })} /> خانه اول است
          </label>
          <label className="check">
            <input type="checkbox" checked={form.has_child} onChange={(e) => setForm({ ...form, has_child: e.target.checked })} /> فرزند متولد ۱۴۰۰ به بعد
          </label>
        </div>
      </section>

      <section className="h-loan-list">
        {catalog?.loans.map((l) => {
          const o = overrides[l.id];
          const p = planById[l.id];
          return (
            <article key={l.id} className={`card h-loan ${p?.selected ? "h-loan-on" : ""}`}>
              <div className="h-loan-head">
                <label className="check">
                  <input type="checkbox" checked={o?.selected ?? false} onChange={(e) => setO(l.id, { selected: e.target.checked })} />
                  <strong>{l.name}</strong>
                </label>
                <span className="tag tag-muted">{l.bank}</span>
              </div>
              <p className="muted small">{l.requirement}</p>
              {p && !p.eligible && <p className="h-warn">⚠️ {p.issues.join("، ")}</p>}
              {p?.cap_warning && <p className="h-warn">⚠️ مبلغ واردشده از سقف مرجع بالاتر است؛ حتماً سقف روز بانک را استعلام کنید.</p>}
              <div className="h-row">
                <label>
                  مبلغ (میلیون)
                  <input type="number" min={0} value={mil(o?.amount ?? l.default_amount)} onChange={(e) => setO(l.id, { amount: Number(e.target.value) * MILLION })} />
                </label>
                <label>
                  سود سالانه٪
                  <input type="number" min={0} max={60} step={0.5} value={o?.rate ?? l.rate} onChange={(e) => setO(l.id, { rate: Number(e.target.value) })} />
                </label>
                <label>
                  مدت (سال)
                  <input type="number" min={1} max={30} value={o?.years ?? l.years} onChange={(e) => setO(l.id, { years: Number(e.target.value) })} />
                </label>
              </div>
              {p && (
                <div className="h-loan-out small">
                  قسط ماهانه: <strong>{toman(p.monthly_installment)}</strong> · کل سود: {toman(p.total_interest)}
                  {p.bond_cost > 0 && <> · هزینه تقریبی خرید اوراق: {toman(p.bond_cost)}</>}
                </div>
              )}
            </article>
          );
        })}
        {catalog && (
          <p className="muted small">
            {catalog.disclaimer} (مبنا: {catalog.as_of}) — هر عدد را می‌توانید با شرایط روز بانک ویرایش کنید.
          </p>
        )}
      </section>

      <aside className="card h-summary" aria-live="polite">
        <div className="section-heading"><span className="section-icon section-icon-green"><Icon name="bank" size={18} /></span><div><h2>خلاصه تأمین مالی</h2><p>تصویر کلی توان پرداخت شما</p></div></div>
        {error && <div className="alert">{error}</div>}
        {plan && (
          <>
            <div className="h-kpi">
              <span>جمع وام‌ها</span>
              <strong>{toman(plan.total_loan)}</strong>
              <small className="muted">{plan.loan_share_pct.toLocaleString("fa-IR")}٪ قیمت خانه</small>
            </div>
            <div className="h-kpi">
              <span>قسط ماهانه کل</span>
              <strong>{toman(plan.total_monthly_installment)}</strong>
              {plan.debt_to_income_pct !== null && <small className="muted">{dti.toLocaleString("fa-IR")}٪ درآمد</small>}
            </div>
            <div className="h-bar" aria-hidden="true">
              <span style={{ width: `${Math.min(dti, 100)}%` }} className={dti > 45 ? "bad" : dti > 30 ? "mid" : "ok"} />
            </div>
            <p className="small">{plan.advice}</p>
            {plan.warnings?.map((warning) => <p key={warning} className="muted small">ⓘ {warning}</p>)}
            <div className={`h-kpi ${plan.gap > 0 ? "h-gap" : "h-ok"}`}>
              <span>{plan.gap > 0 ? "کسری بودجه" : "بودجه کافی است"}</span>
              <strong>{plan.gap > 0 ? toman(plan.gap) : "✓"}</strong>
              {plan.bond_cost > 0 && <small className="muted">هزینه اوراق از پس‌انداز کسر شده است</small>}
            </div>
          </>
        )}
      </aside>
    </div>
  );
}
