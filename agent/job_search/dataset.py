"""Load the JobVision listing export and normalize it to the search schema.

Every value in a normalized job comes from the source record or from its cached
detail page; nothing is inferred or filled in. Missing values stay empty/None.
"""

import json
from pathlib import Path
from typing import Iterable, Optional

from agent.job_search.crawler import job_url
from agent.utilities.persian_text import normalize_for_search

SOURCE_NAME = "jobvision.ir"


def _fa(item) -> str:
    if not isinstance(item, dict):
        return ""
    return (item.get("titleFa") or item.get("title") or "").strip()


def _en(item) -> str:
    if not isinstance(item, dict):
        return ""
    return (item.get("titleEn") or "").strip()


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{line_no}: invalid JSON ({e})") from e
    return rows


def normalize_listing(raw: dict, detail: Optional[dict] = None) -> Optional[dict]:
    """Map one listing record (+ optional enrichment) to the flat job schema."""
    job_id = raw.get("id")
    title = (raw.get("title") or "").strip()
    if job_id is None or not title:
        return None

    props = raw.get("properties") or {}
    company = raw.get("company") or {}
    location = raw.get("location") or {}
    salary = raw.get("salary") or None
    salary_shown = bool(props.get("salaryCanBeShown")) and bool(salary)

    job = {
        "id": str(job_id),
        "source": SOURCE_NAME,
        "url": job_url(job_id),
        "title": title,
        "company": (company.get("nameFa") or company.get("nameEn") or "").strip(),
        "company_en": (company.get("nameEn") or "").strip(),
        "company_url": (
            f"https://jobvision.ir{company['pageUrl']}" if company.get("pageUrl") else ""
        ),
        "company_logo": company.get("logoUrl") or "",
        "province": _fa(location.get("province")),
        "province_en": _en(location.get("province")),
        "city": _fa(location.get("city")),
        "city_en": _en(location.get("city")),
        "region": _fa(location.get("region")),
        "categories": [c for c in (_fa(x) for x in raw.get("jobCategories") or []) if c],
        "categories_en": [c for c in (_en(x) for x in raw.get("jobCategories") or []) if c],
        "industry": _fa(raw.get("industry")),
        "work_type": _fa(raw.get("workType")),
        "seniority": _fa(raw.get("seniorityLevel")),
        "gender": _fa(raw.get("gender")),
        "benefits": [b for b in (_fa(x) for x in raw.get("benefits") or []) if b],
        "labels": [str(x) for x in raw.get("labels") or []],
        "is_remote": bool(props.get("isRemote")),
        "is_internship": bool(props.get("isInternship")),
        "is_urgent": bool(props.get("isUrgent")),
        "required_experience_years": props.get("requiredRelatedExperienceYears"),
        "salary_text": _fa(salary) if salary_shown else "",
        "salary_min": salary.get("min") if salary_shown else None,
        "salary_max": salary.get("max") if salary_shown else None,
        "date_posted": ((raw.get("activationTime") or {}).get("date") or ""),
        "expires": ((raw.get("expireTime") or {}).get("date") or ""),
        "description": "",
        "skills": [],
        "software": [],
        "languages": [],
        "academic": [],
        "work_days": "",
        "enriched": False,
    }

    if detail:
        job["description"] = detail.get("description") or ""
        job["skills"] = list(detail.get("skills") or [])
        job["software"] = list(detail.get("software") or [])
        job["languages"] = list(detail.get("languages") or [])
        job["academic"] = list(detail.get("academic") or [])
        job["work_days"] = detail.get("work_days") or ""
        if detail.get("url"):
            job["url"] = detail["url"]
        if detail.get("is_remote") is True:
            job["is_remote"] = True
        job["enriched"] = True

    return job


def dedupe_key(job: dict) -> tuple:
    return (
        normalize_for_search(job["title"]),
        normalize_for_search(job["company"]),
        job["province"],
        job["city"],
    )


def deduplicate(jobs: Iterable[dict]) -> list[dict]:
    """Drop repeated ids and re-posts of the same title by the same company in the same city.

    The first occurrence wins, except that an enriched copy replaces a bare one.
    """
    by_key: dict[tuple, int] = {}
    seen_ids: set[str] = set()
    out: list[dict] = []
    for job in jobs:
        if job["id"] in seen_ids:
            continue
        seen_ids.add(job["id"])
        key = dedupe_key(job)
        if key in by_key:
            idx = by_key[key]
            if job["enriched"] and not out[idx]["enriched"]:
                out[idx] = job
            continue
        by_key[key] = len(out)
        out.append(job)
    return out


def load_jobs(listing_paths, details_dir: Optional[Path] = None) -> list[dict]:
    """`listing_paths`: one path or several (e.g. the dataset plus live-crawled ads)."""
    if isinstance(listing_paths, (str, Path)):
        listing_paths = [listing_paths]
    details_dir = Path(details_dir) if details_dir else None
    raws = [r for p in listing_paths if Path(p).exists() for r in read_jsonl(Path(p))]
    jobs = []
    for raw in raws:
        detail = None
        if details_dir is not None and raw.get("id") is not None:
            p = details_dir / f"{int(raw['id'])}.json"
            if p.exists():
                detail = json.loads(p.read_text(encoding="utf-8"))
        job = normalize_listing(raw, detail)
        if job is not None:
            jobs.append(job)
    return deduplicate(jobs)
