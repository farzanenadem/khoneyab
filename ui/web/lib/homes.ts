// Types mirror the /homes/* FastAPI responses (agent/home_search/*).

export type Listing = {
  id: string;
  source?: string;
  url: string;
  title: string;
  category?: string;
  city: string;
  district: string;
  price_text: string;
  price_toman: number | null;
  area_m2: number | null;
  rooms: number | null;
  price_per_m2: number | null;
  subtitle: string;
  tag: string;
  image_url: string;
  crawled_at: string;
  posted_at?: string | null;
};

export type ListingSort = "newest" | "price_asc" | "price_desc" | "price_per_m2";

export type ListingQuery = {
  city?: string;
  q?: string;
  min_price?: number;
  max_price?: number;
  min_area?: number;
  max_area?: number;
  rooms?: number;
  sort?: ListingSort;
  limit?: number;
  offset?: number;
};

export type ListingResponse = {
  total: number;
  results: Listing[];
  median_price_per_m2: number | null;
  limit: number;
  offset: number;
  next_offset: number | null;
};
export type HomeOptions = { total: number; cities: { city: string; count: number }[] };

export type Loan = {
  id: string;
  bank: string;
  name: string;
  caps: Record<string, number>;
  couple_multiplier: number;
  rate: number;
  years: number;
  tier: string;
  requirement: string;
  default_amount: number;
  first_home_only: boolean;
  child_required: boolean;
  bond_cost_ratio: number;
};
export type LoanCatalog = { loans: Loan[]; as_of: string; disclaimer: string };

export type LoanOverride = { id: string; selected: boolean; amount?: number; rate?: number; years?: number };
export type PlanInput = {
  price: number;
  savings: number;
  monthly_income: number;
  city: string;
  married: boolean;
  has_child: boolean;
  first_home: boolean;
  loans: LoanOverride[];
};
export type PlanLoan = {
  id: string;
  name: string;
  selected: boolean;
  eligible: boolean;
  issues: string[];
  amount: number;
  rate: number;
  years: number;
  monthly_installment: number;
  total_repayment: number;
  total_interest: number;
  bond_cost: number;
  cap_warning: boolean;
};
export type Plan = {
  loans: PlanLoan[];
  total_loan: number;
  total_monthly_installment: number;
  bond_cost: number;
  loan_share_pct: number;
  gap: number;
  debt_to_income_pct: number | null;
  advice: string;
  as_of: string;
  warnings: string[];
};

export type RoadmapStep = {
  id: string;
  n: number | null;
  title: string;
  phase: string;
  level: "critical" | "high" | "medium" | "low";
  condition: string | null;
  goal: string;
  reveals?: string;
  authority: string;
  method?: string;
  docs: string;
  when: string;
  required: string;
  risk: string;
  notes: string;
  detail: string;
  sources: { label: string; url: string }[];
};
export type Roadmap = {
  phases: { id: string; title: string; subtitle: string; steps: RoadmapStep[] }[];
  total_steps: number;
  levels: Record<string, string>;
  conditions: { id: string; label: string; default: boolean }[];
  summary: string;
  repeat_note: string;
  misconceptions: { belief: string; why: string }[];
  special_cases: { title: string; text: string }[];
  open_questions: string[];
  source: string;
  disclaimer: string;
};

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`/api${path}`);
  if (!r.ok) throw await readApiError(r);
  return r.json();
}

async function readApiError(response: Response): Promise<Error> {
  try {
    const body = (await response.json()) as { detail?: string | { message?: string } };
    const detail = typeof body.detail === "string" ? body.detail : body.detail?.message;
    return new Error(detail || `خطای سرور (${response.status})`);
  } catch {
    return new Error(`خطای سرور (${response.status})`);
  }
}

export function searchHomes(q: ListingQuery): Promise<ListingResponse> {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) if (v !== undefined && v !== "" && v !== null) params.set(k, String(v));
  return get(`/homes/search?${params}`);
}

export const getHomeOptions = () => get<HomeOptions>("/homes/options");
export const getRoadmap = () => get<Roadmap>("/homes/roadmap");
export const getLoans = (city: string, married: boolean) =>
  get<LoanCatalog>(`/homes/loans?city=${encodeURIComponent(city)}&married=${married}`);

export async function planLoans(input: PlanInput): Promise<Plan> {
  const r = await fetch("/api/homes/loans/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!r.ok) throw await readApiError(r);
  return r.json();
}

/** 4,680,000,000 → "۴٫۶۸ میلیارد تومان" */
export function toman(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  const fa = (x: number, d = 2) => x.toLocaleString("fa-IR", { maximumFractionDigits: d });
  if (Math.abs(n) >= 1e9) return `${fa(n / 1e9)} میلیارد تومان`;
  if (Math.abs(n) >= 1e6) return `${fa(n / 1e6, 1)} میلیون تومان`;
  return `${fa(n, 0)} تومان`;
}

export type HomeChatResponse = {
  thread_id: string;
  reply: string;
  filters: Record<string, unknown> | null;
  understood: string[];
  relaxed: string[];
  results: (Listing & { matched_features?: string[] })[];
};

export async function homeChat(message: string, threadId: string, filters: Record<string, unknown> | null): Promise<HomeChatResponse> {
  const r = await fetch("/api/homes/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, thread_id: threadId, filters }),
  });
  if (!r.ok) throw await readApiError(r);
  return r.json();
}
