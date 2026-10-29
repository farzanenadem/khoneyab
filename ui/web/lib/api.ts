// Types mirror the FastAPI responses in ui/src/api.py and agent/job_search/search.py.

export type Software = { name: string; level: string };

export type Job = {
  id: string;
  source: string;
  url: string;
  title: string;
  company: string;
  company_url: string;
  company_logo: string;
  province: string;
  city: string;
  region: string;
  categories: string[];
  industry: string;
  work_type: string;
  seniority: string;
  gender: string;
  benefits: string[];
  labels: string[];
  is_remote: boolean;
  is_internship: boolean;
  is_urgent: boolean;
  required_experience_years: number | null;
  salary_text: string;
  date_posted: string;
  expires: string;
  description: string;
  skills: string[];
  software: Software[];
  languages: Software[];
  academic: string[];
  work_days: string;
  enriched: boolean;
};

export type Evidence = {
  concept: string;
  field: string;
  field_label: string;
  evidence: string;
  matched_term: string;
};

export type PreferenceCheck = { type: string; ok: boolean | null; text: string };

export type SearchResult = {
  rank: number;
  score: number;
  score_breakdown: Record<string, number>;
  job: Job;
  explanation: {
    summary: string;
    matched: Evidence[];
    missing: string[];
    preferences: PreferenceCheck[];
  };
  resume_match?: { matched_skills: string[]; missing_skills: string[] };
};

export type ParsedQuery = {
  text: string;
  locations: string[];
  location_strict: boolean;
  wants_remote: boolean;
  wants_internship: boolean;
  work_types: string[];
  seniority: string[];
  experience_years: number | null;
  min_salary: number | null;
  concepts: { label: string; variants: string[] }[];
};

export type SearchResponse = {
  query: ParsedQuery;
  total_candidates: number;
  method: string;
  results: SearchResult[];
  live?: { enabled: boolean; keywords?: string[]; new_jobs?: number; error?: string };
};

export type Filters = {
  provinces: string[];
  cities: string[];
  work_types: string[];
  seniority: string[];
  categories: string[];
  industries: string[];
  remote_only: boolean;
  internship_only: boolean;
  salary_disclosed_only: boolean;
  max_experience_years: number | null;
  min_salary: number | null;
  posted_within_days: number | null;
  sources: string[];
};

export const SOURCE_LABELS: Record<string, string> = {
  "jobvision.ir": "جاب‌ویژن",
  "jobinja.ir": "جابینجا",
  "irantalent.com": "ایران‌تلنت",
};

export const EMPTY_FILTERS: Filters = {
  provinces: [],
  cities: [],
  work_types: [],
  seniority: [],
  categories: [],
  industries: [],
  remote_only: false,
  internship_only: false,
  salary_disclosed_only: false,
  max_experience_years: null,
  min_salary: null,
  posted_within_days: null,
  sources: [],
};

export type Option = { value: string; count: number };

export type FilterOptions = {
  sources: Option[];
  provinces: Option[];
  cities: Option[];
  work_types: Option[];
  seniority: Option[];
  categories: Option[];
  industries: Option[];
  remote_count: number;
  internship_count: number;
  salary_disclosed_count: number;
  total: number;
  enriched: number;
};

export type Method = "hybrid" | "semantic" | "bm25" | "keyword";
export type Sort = "relevance" | "newest";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export function searchJobs(query: string, filters: Filters, topK: number, method: Method, sort: Sort = "relevance") {
  return request<SearchResponse>("/jobs/search", {
    method: "POST",
    body: JSON.stringify({ query, filters, top_k: topK, method, sort }),
  });
}

export function getFilterOptions() {
  return request<FilterOptions>("/jobs/filters");
}

export function getHealth() {
  return request<{ job_search_ready: boolean; jobs_indexed: number; job_search_error: string | null }>(
    "/health",
  );
}

export type ChatResponse = {
  response: string;
  thread_id: string;
  sources: { content: string; metadata: { job_id?: string; title?: string; url?: string } }[];
  usage?: TokenUsage;
};

export function sendChat(message: string, threadId: string) {
  return request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({ message, thread_id: threadId }),
  });
}

export type ResumeProfile = {
  skills: string[];
  experience_years: number | null;
  education: string[];
  roles: string[];
  location: string | null;
  source: "llm" | "rules";
};

export type ResumeSearchResponse = SearchResponse & { profile: ResumeProfile; generated_query: string };

export async function searchByResume(file: File, topK: number): Promise<ResumeSearchResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("top_k", String(topK));
  const res = await fetch("/api/resume/search", { method: "POST", body: form });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json();
}

export type RoadmapStage = { skill: string; why: string; steps: string[]; weeks: number | null };

export type Roadmap = {
  job_id: string;
  title: string;
  summary: string;
  have_skills: string[];
  stages: RoadmapStage[];
  requirements_listed: boolean;
  source: "llm" | "rules";
};

export type UsageRow = {
  name: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  seconds: number;
  cost_usd: number | null;
};

export type UsageCall = {
  time: number;
  feature: string;
  model: string;
  step: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  seconds: number;
};

/** Tokens of one HTTP request (also returned with each /chat answer). */
export type TokenUsage = {
  request_id: string | null;
  llm_calls: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  seconds: number;
  complete: boolean;
  status: "reported" | "partial" | "not_used";
};

export type RequestUsage = TokenUsage & {
  endpoint: string;
  time: number;
  status_code: number;
  duration_ms: number;
  calls: { step: string; model: string; input_tokens: number; output_tokens: number; seconds: number }[];
};

export type UsageSummary = {
  since: number;
  total: Omit<UsageRow, "name"> & {
    avg_tokens_per_call: number;
    avg_seconds_per_call: number;
    p50_seconds: number;
    p95_seconds: number;
    output_tokens_per_second: number;
  };
  errors: number;
  calls_without_usage: number;
  pricing_configured: boolean;
  by_feature: (UsageRow & { p50_seconds: number; p95_seconds: number })[];
  by_model: UsageRow[];
  by_step: UsageRow[];
  recent: UsageCall[];
  timeline: { time: number; total_tokens: number; seconds: number; feature: string }[];
  requests: RequestUsage[];
  history: {
    requests: number;
    total_tokens: number;
    input_tokens: number;
    output_tokens: number;
    avg_duration_ms: number;
    errors: number;
    llm_requests: number;
    since: number | null;
    path: string;
  } | null;
  endpoints: { name: string; requests: number; avg_ms: number; p95_ms: number }[];
};

export const getUsage = () => request<UsageSummary>("/usage");
export const resetUsage = () => request<{ status: string }>("/usage/reset", { method: "POST" });

export function getRoadmap(jobId: string, knownSkills: string[]) {
  return request<Roadmap>(`/jobs/${encodeURIComponent(jobId)}/roadmap`, {
    method: "POST",
    body: JSON.stringify({ known_skills: knownSkills }),
  });
}
