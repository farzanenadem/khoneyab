"""Descriptive job search: hybrid retrieval, preference-aware ranking, grounded explanations.

score = w_sem * semantic + w_lex * bm25 + w_concept * concept coverage + w_pref * preferences

* semantic   - cosine similarity of the query and the ad (min-max scaled over candidates)
* bm25       - lexical score over weighted fields, with bilingual synonym expansion
* concepts   - share of the user's skill/role concepts literally present in the ad
* preferences- soft match on location/remote, work type, seniority, experience, salary

Weights of components that do not apply to a query (e.g. no preferences stated)
are redistributed. Explanations only quote text that exists in the ad.
"""

import re
import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

import numpy as np

from agent.job_search.index import Embedder, JobIndex, job_fields, passage_text
from agent.job_search.matching import canon, phrase_regex
from agent.job_search.query_parser import Concept, ParsedQuery, QueryParser
from agent.utilities.persian_text import tokenize

DEFAULT_WEIGHTS = {"semantic": 0.45, "lexical": 0.25, "concept": 0.15, "preference": 0.15, "recency": 0.10}
METHODS = ("hybrid", "semantic", "bm25", "keyword")
SORTS = ("relevance", "newest")
RECENCY_HALF_LIFE_DAYS = 14.0
# Hybrid results scoring below this share of the best score are dropped as not relevant.
MIN_RELATIVE_SCORE = 0.6

FIELD_LABELS = {
    "title": "عنوان آگهی",
    "skills": "مهارت‌های موردنیاز",
    "software": "نرم‌افزارهای موردنیاز",
    "categories": "دسته‌بندی شغلی",
    "industry": "صنعت",
    "description": "شرح آگهی",
    "benefits": "مزایا",
    "academic": "رشته و مدرک تحصیلی",
    "company": "شرکت",
}
EVIDENCE_FIELD_ORDER = ["title", "skills", "software", "categories", "industry", "academic", "description", "benefits"]
MAX_EVIDENCE_CHARS = 220
# Fields that define what the job is; a concept found only elsewhere (description,
# benefits) counts half towards concept coverage.
CORE_FIELDS = ("title", "categories", "skills", "software", "industry", "academic")
DESCRIPTION_ONLY_CREDIT = 0.5


@dataclass
class SearchFilters:
    provinces: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    work_types: list[str] = field(default_factory=list)
    seniority: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    remote_only: bool = False
    internship_only: bool = False
    salary_disclosed_only: bool = False
    max_experience_years: Optional[int] = None
    min_salary: Optional[int] = None  # million tomans, compared with the ad's upper bound
    include_expired: bool = False
    posted_within_days: Optional[int] = None

    def accepts(self, job: dict, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if not self.include_expired:
            expires = parse_date(job.get("expires"))
            if expires is not None and expires < now:
                return False
        if self.posted_within_days is not None:
            posted = parse_date(job.get("date_posted"))
            if posted is None or (now - posted).days > self.posted_within_days:
                return False
        if self.provinces and job.get("province") not in self.provinces:
            return False
        if self.cities and job.get("city") not in self.cities:
            return False
        if self.work_types and job.get("work_type") not in self.work_types:
            return False
        if self.seniority and job.get("seniority") not in self.seniority:
            return False
        if self.categories and not set(job.get("categories") or []) & set(self.categories):
            return False
        if self.industries and job.get("industry") not in self.industries:
            return False
        if self.remote_only and not job.get("is_remote"):
            return False
        if self.internship_only and not is_internship(job):
            return False
        if self.salary_disclosed_only and not job.get("salary_text"):
            return False
        if self.max_experience_years is not None:
            req = job.get("required_experience_years")
            if req is not None and req > self.max_experience_years:
                return False
        if self.min_salary is not None:
            top = job.get("salary_max")
            if top is None or top < self.min_salary:
                return False
        return True


def parse_date(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def recency_score(job: dict, now: datetime, half_life_days: float = RECENCY_HALF_LIFE_DAYS) -> float:
    """1.0 for an ad posted now, 0.5 after `half_life_days`, 0 when the date is unknown."""
    posted = parse_date(job.get("date_posted"))
    if posted is None:
        return 0.0
    age = max(0.0, (now - posted).total_seconds() / 86400)
    return 0.5 ** (age / half_life_days)


def is_internship(job: dict) -> bool:
    return bool(
        job.get("is_internship")
        or job.get("seniority") == "کارآموز"
        or "امکان جذب کارآموز" in (job.get("labels") or [])
    )


def concept_regex(concept: Concept) -> re.Pattern:
    parts = sorted({phrase_regex(v).pattern for v in concept.variants if canon(v)}, key=len, reverse=True)
    return re.compile("|".join(parts)) if parts else re.compile(r"(?!x)x")


def _minmax(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    lo, hi = float(values.min()), float(values.max())
    if hi - lo < 1e-9:
        return np.ones_like(values) if hi > 0 else np.zeros_like(values)
    return (values - lo) / (hi - lo)


def _clip(text: str, start: int = 0) -> str:
    text = text.strip()
    if len(text) <= MAX_EVIDENCE_CHARS:
        return text
    begin = max(0, min(start - 60, len(text) - MAX_EVIDENCE_CHARS))
    snippet = text[begin : begin + MAX_EVIDENCE_CHARS].strip()
    return ("…" if begin > 0 else "") + snippet + ("…" if begin + MAX_EVIDENCE_CHARS < len(text) else "")


class JobSearchService:
    def __init__(
        self,
        index: JobIndex,
        embedder: Optional[Embedder],
        synonym_groups: list[list[str]] = (),
        weights: Optional[dict] = None,
        live_crawler=None,
        min_relative_score: float = MIN_RELATIVE_SCORE,
        recency_half_life_days: float = RECENCY_HALF_LIFE_DAYS,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.min_relative_score = min_relative_score
        self.recency_half_life_days = recency_half_life_days
        self.now = now
        self.index = index
        self.embedder = embedder
        self.weights = {**DEFAULT_WEIGHTS, **(weights or {})}
        self.synonym_groups = list(synonym_groups)
        self.live_crawler = live_crawler
        self._lock = threading.RLock()
        self._refresh_derived()
        if live_crawler is not None:
            live_crawler.on_enriched(self.update_job)

    def _refresh_derived(self):
        locations = {j.get("province") for j in self.index.jobs} | {j.get("city") for j in self.index.jobs}
        self.parser = QueryParser(sorted(l for l in locations if l), self.synonym_groups)
        # Canonical text per job, used for concept matching.
        self._canon_all = [canon(" \n ".join(job_fields(j).values())) for j in self.index.jobs]
        self._canon_core = [self._core_text(j) for j in self.index.jobs]

    @staticmethod
    def _core_text(job: dict) -> str:
        f = job_fields(job)
        return canon(" \n ".join(f[k] for k in CORE_FIELDS))

    def _embed(self, jobs: list[dict]) -> np.ndarray:
        if self.embedder is None:
            return np.zeros((len(jobs), self.index.embeddings.shape[1]), dtype=np.float32)
        return self.embedder.embed_passages([passage_text(j) for j in jobs])

    def add_jobs(self, jobs: list[dict]) -> int:
        with self._lock:
            jobs = [j for j in jobs if j["id"] not in self.index.id_to_pos]
            if jobs:
                self.index.add_jobs(jobs, self._embed(jobs))
                self._refresh_derived()
            return len(jobs)

    def update_job(self, job: dict) -> None:
        """Replace a job with its enriched version (called from the live-crawl worker)."""
        with self._lock:
            if job["id"] in self.index.id_to_pos:
                self.index.replace_job(job, self._embed([job])[0])
                pos = self.index.id_to_pos[job["id"]]
                self._canon_all[pos] = canon(" \n ".join(job_fields(job).values()))
                self._canon_core[pos] = self._core_text(job)

    def live_crawl(self, query: str, keywords: Optional[list[str]] = None) -> dict:
        """Fetch fresh ads for the user's keywords and add them to the index."""
        if self.live_crawler is None:
            return {"enabled": False}
        pq = self.parser.parse(query)
        keywords = [k for k in (keywords or [c.label for c in pq.concepts]) if k and len(k) > 1]
        if not keywords and pq.text:
            keywords = [pq.text[:60]]
        try:
            new_jobs = self.live_crawler.fetch(keywords, set(self.index.id_to_pos))
            added = self.add_jobs(new_jobs)
            return {"enabled": True, "keywords": keywords[: self.live_crawler.max_keywords], "new_jobs": added}
        except Exception as e:  # the site being down must not break search
            return {"enabled": True, "keywords": keywords, "new_jobs": 0, "error": str(e)}

    # ---------- scoring components ----------

    def _semantic(self, query: str) -> np.ndarray:
        if self.embedder is None or len(self.index) == 0:
            return np.zeros(len(self.index), dtype=np.float32)
        return self.index.embeddings @ self.embedder.embed_query(query)

    def _keyword_overlap(self, query: str) -> np.ndarray:
        """Baseline: number of distinct query tokens present in the ad (no weighting/synonyms)."""
        q = set(tokenize(query))
        out = np.zeros(len(self.index), dtype=np.float32)
        if not q:
            return out
        for i, job in enumerate(self.index.jobs):
            out[i] = len(q & set(tokenize(" ".join(job_fields(job).values()))))
        return out

    def _concept_hits(self, regexes: list[re.Pattern], positions: np.ndarray) -> np.ndarray:
        """1.0 if a concept is in a core field, DESCRIPTION_ONLY_CREDIT if only elsewhere, else 0."""
        hits = np.zeros((len(positions), len(regexes)), dtype=np.float32)
        for r, pos in enumerate(positions):
            text, core = self._canon_all[pos], self._canon_core[pos]
            for c, rx in enumerate(regexes):
                if rx.search(text) is not None:
                    hits[r, c] = 1.0 if rx.search(core) is not None else DESCRIPTION_ONLY_CREDIT
        return hits

    @staticmethod
    def preference_checks(job: dict, pq: ParsedQuery) -> list[dict]:
        """Each check: {type, ok (bool|None), text}. Text uses only the ad's own values."""
        checks = []
        place = "، ".join(x for x in (job.get("city"), job.get("province")) if x) or "نامشخص"
        if pq.locations or pq.wants_remote:
            in_loc = bool(pq.locations) and (
                job.get("province") in pq.locations or job.get("city") in pq.locations
            )
            remote = bool(job.get("is_remote"))
            ok = in_loc or (pq.wants_remote and remote)
            wanted = " یا ".join(pq.locations + (["دورکاری"] if pq.wants_remote else []))
            facts = [f"محل کار: {place}"]
            if remote:
                facts.append("امکان دورکاری دارد")
            elif pq.wants_remote:
                facts.append("دورکاری در آگهی ذکر نشده")
            checks.append({"type": "location", "ok": ok, "text": f"{' — '.join(facts)} (ترجیح شما: {wanted})"})
        if pq.work_types:
            wt = job.get("work_type") or ""
            ok = any(w in wt for w in pq.work_types) if wt else None
            checks.append({"type": "work_type", "ok": ok, "text": f"نوع همکاری: {wt or 'ذکر نشده'}"})
        if pq.seniority:
            level = job.get("seniority") or ""
            ok = (level in pq.seniority) if level else None
            checks.append({"type": "seniority", "ok": ok, "text": f"سطح ارشدیت: {level or 'ذکر نشده'}"})
        if pq.wants_internship:
            ok = is_internship(job)
            checks.append({"type": "internship", "ok": ok, "text": "امکان جذب کارآموز دارد" if ok else "کارآموزی در آگهی ذکر نشده"})
        if pq.experience_years is not None:
            req = job.get("required_experience_years")
            if req is None:
                checks.append({"type": "experience", "ok": None, "text": "سابقه موردنیاز ذکر نشده"})
            else:
                checks.append({
                    "type": "experience",
                    "ok": req <= pq.experience_years,
                    "text": f"سابقه موردنیاز: {req} سال (سابقه شما: {pq.experience_years} سال)",
                })
        if pq.min_salary is not None:
            if job.get("salary_text"):
                ok = job.get("salary_max") is not None and job["salary_max"] >= pq.min_salary
                checks.append({"type": "salary", "ok": ok, "text": f"حقوق اعلام‌شده: {job['salary_text']}"})
            else:
                checks.append({"type": "salary", "ok": None, "text": "حقوق در آگهی اعلام نشده"})
        return checks

    @staticmethod
    def _preference_score(checks: list[dict]) -> Optional[float]:
        if not checks:
            return None
        vals = [1.0 if c["ok"] else (0.5 if c["ok"] is None else 0.0) for c in checks]
        return sum(vals) / len(vals)

    # ---------- explanations ----------

    def explain(self, job: dict, pq: ParsedQuery, regexes: list[re.Pattern], checks: list[dict]) -> dict:
        fields = job_fields(job)
        matched, missing = [], []
        for concept, rx in zip(pq.concepts, regexes):
            evidence = None
            for name in EVIDENCE_FIELD_ORDER:
                raw = fields.get(name) or ""
                if not raw:
                    continue
                units = raw.splitlines() if name == "description" else [raw]
                for unit in units:
                    m = rx.search(canon(unit))
                    if m:
                        evidence = {
                            "concept": concept.label,
                            "field": name,
                            "field_label": FIELD_LABELS[name],
                            "evidence": _clip(unit, m.start()),
                            "matched_term": m.group(0),
                        }
                        break
                if evidence:
                    break
            if evidence:
                matched.append(evidence)
            else:
                missing.append(concept.label)

        good_prefs = [c for c in checks if c["ok"]]
        parts = []
        if matched:
            by_field = {}
            for m in matched:
                by_field.setdefault(m["field_label"], []).append(f"«{m['concept']}»")
            parts.append("؛ ".join(f"{', '.join(v)} در {k}" for k, v in by_field.items()) + " آمده است")
        if good_prefs:
            parts.append("با ترجیحات شما (" + "، ".join(c["text"].split(" (")[0] for c in good_prefs) + ") سازگار است")
        if not parts:
            basis = "شباهت معنایی عنوان و دسته‌بندی" if self.embedder is not None else "واژه‌های مرتبط"
            summary = (
                "هیچ‌یک از عبارات درخواست شما عیناً در این آگهی نیامده؛ "
                f"این نتیجه فقط بر اساس {basis} پیشنهاد شده است."
            )
        else:
            summary = "این آگهی: " + "، و ".join(parts) + "."
        if not job.get("enriched"):
            summary += " (شرح کامل این آگهی در دسترس نبود؛ تطبیق بر اساس عنوان و مشخصات ساختاریافته است.)"
        return {"summary": summary, "matched": matched, "missing": missing, "preferences": checks}

    # ---------- public API ----------

    def search(
        self,
        query: str,
        filters: Optional[SearchFilters] = None,
        top_k: int = 10,
        method: str = "hybrid",
        live: bool = False,
        keywords: Optional[list[str]] = None,
        sort: str = "relevance",
    ) -> dict:
        if method not in METHODS:
            raise ValueError(f"method must be one of {METHODS}")
        if sort not in SORTS:
            raise ValueError(f"sort must be one of {SORTS}")
        query = (query or "").strip()
        live_info = self.live_crawl(query, keywords) if (live and query) else {"enabled": False}
        with self._lock:
            result = self._search(query, filters, top_k, method, sort)
        result["live"] = live_info
        return result

    def _search(self, query: str, filters: Optional[SearchFilters], top_k: int, method: str, sort: str = "relevance") -> dict:
        filters = filters or SearchFilters()
        pq = self.parser.parse(query)
        now = self.now()

        mask = np.array([filters.accepts(j, now) for j in self.index.jobs], dtype=bool)
        if pq.location_strict and pq.locations:
            mask &= np.array(
                [
                    j.get("province") in pq.locations
                    or j.get("city") in pq.locations
                    or (pq.wants_remote and j.get("is_remote"))
                    for j in self.index.jobs
                ],
                dtype=bool,
            )
        positions = np.flatnonzero(mask)
        total = int(len(positions))
        if total == 0 or not query:
            return {"query": pq.to_dict(), "total_candidates": total, "method": method, "results": []}

        regexes = [concept_regex(c) for c in pq.concepts]
        semantic_raw = self._semantic(query)[positions] if method in ("hybrid", "semantic") else None
        bm25_raw = None
        if method in ("hybrid", "bm25"):
            bm25_raw = self.index.bm25.scores(tokenize(query + " " + pq.expansion_text))[positions]

        if method == "keyword":
            final = self._keyword_overlap(query)[positions]
            components = {"keyword": final}
        elif method == "semantic":
            final = semantic_raw
            components = {"semantic": semantic_raw}
        elif method == "bm25":
            final = bm25_raw
            components = {"lexical": bm25_raw}
        else:
            w = dict(self.weights)
            sem = _minmax(semantic_raw) if self.embedder is not None else np.zeros(total)
            if self.embedder is None:
                w["semantic"] = 0.0
            bm_max = float(bm25_raw.max()) if total else 0.0
            lex = bm25_raw / bm_max if bm_max > 0 else np.zeros(total)
            if regexes:
                coverage = self._concept_hits(regexes, positions).mean(axis=1)
            else:
                coverage, w["concept"] = np.zeros(total), 0.0
            pref = np.zeros(total)
            has_prefs = bool(
                pq.locations or pq.wants_remote or pq.work_types or pq.seniority
                or pq.wants_internship or pq.experience_years is not None or pq.min_salary is not None
            )
            if has_prefs:
                for r, pos in enumerate(positions):
                    pref[r] = self._preference_score(self.preference_checks(self.index.jobs[pos], pq)) or 0.0
            else:
                w["preference"] = 0.0
            recency = np.array(
                [recency_score(self.index.jobs[pos], now, self.recency_half_life_days) for pos in positions]
            )
            # Topical relevance (what the job is about) decides which ads qualify;
            # preferences and recency only reorder the qualifying ads.
            topic_w = w["semantic"] + w["lexical"] + w["concept"]
            topical = (w["semantic"] * sem + w["lexical"] * lex + w["concept"] * coverage) / (topic_w or 1.0)
            denom = sum(w.values()) or 1.0
            final = (
                w["semantic"] * sem + w["lexical"] * lex + w["concept"] * coverage
                + w["preference"] * pref + w["recency"] * recency
            ) / denom
            components = {"semantic": semantic_raw if self.embedder is not None else sem, "lexical": bm25_raw,
                          "concept": coverage, "preference": pref, "recency": recency}

        # Stable sort: ties keep dataset order.
        order = np.argsort(-final, kind="stable")
        if method == "hybrid" and len(order):
            # Drop ads whose topic is far from the best-matching ad, however well
            # they fit the location or how recent they are.
            floor = self.min_relative_score * float(topical.max())
            order = order[topical[order] >= floor]
        order = order[: max(1, top_k)]
        if sort == "newest":
            posted = [parse_date(self.index.jobs[positions[r]].get("date_posted")) for r in order]
            oldest = datetime.min.replace(tzinfo=timezone.utc)
            order = [r for _, r in sorted(zip(posted, order), key=lambda x: x[0] or oldest, reverse=True)]
        results = []
        for rank, r in enumerate(order, 1):
            job = self.index.jobs[positions[r]]
            checks = self.preference_checks(job, pq)
            results.append({
                "rank": rank,
                "score": round(float(final[r]), 4),
                "score_breakdown": {k: round(float(v[r]), 4) for k, v in components.items()},
                "job": job,
                "explanation": self.explain(job, pq, regexes, checks),
            })
        return {"query": pq.to_dict(), "total_candidates": total, "method": method, "sort": sort, "results": results}

    def filter_options(self) -> dict:
        jobs = self.index.jobs

        def counted(values):
            return [{"value": v, "count": c} for v, c in Counter(v for v in values if v).most_common()]

        return {
            "provinces": counted(j.get("province") for j in jobs),
            "cities": counted(j.get("city") for j in jobs),
            "work_types": counted(j.get("work_type") for j in jobs),
            "seniority": counted(j.get("seniority") for j in jobs),
            "categories": counted(c for j in jobs for c in j.get("categories") or []),
            "industries": counted(j.get("industry") for j in jobs),
            "remote_count": sum(1 for j in jobs if j.get("is_remote")),
            "internship_count": sum(1 for j in jobs if is_internship(j)),
            "salary_disclosed_count": sum(1 for j in jobs if j.get("salary_text")),
            "total": len(jobs),
            "enriched": sum(1 for j in jobs if j.get("enriched")),
            "index_meta": self.index.meta,
        }

    def get_job(self, job_id: str) -> Optional[dict]:
        pos = self.index.id_to_pos.get(str(job_id))
        return None if pos is None else self.index.jobs[pos]
