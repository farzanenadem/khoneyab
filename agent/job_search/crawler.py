"""Polite enrichment crawler for public JobVision job-detail pages.

The listing export (jobs.jsonl) has no description or skills. For every job id we
fetch https://jobvision.ir/jobs/<id> (allowed by robots.txt, which only blocks
query strings, UTM links and login pages), read the server-rendered detail JSON,
and keep only the fields needed for matching. Results are cached per job so the
crawl is resumable and the demo never depends on the live site.
"""

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional
from urllib.parse import quote, urlsplit

import requests

from agent.utilities.persian_text import html_to_text

BASE_URL = "https://jobvision.ir"
DEFAULT_USER_AGENT = (
    "RahnamaHackathonJobSearchBot/1.0 (educational prototype; low-rate, cached)"
)


def job_url(job_id) -> str:
    return f"{BASE_URL}/jobs/{job_id}"


class RobotsRules:
    """robots.txt matcher with Google semantics (`*` wildcard, `$` anchor, longest rule wins).

    urllib.robotparser ignores wildcards, which would make `disallow: *?*` a no-op.
    """

    def __init__(self, text: str, user_agent: str = "*"):
        self.rules: list[tuple[bool, str]] = []
        agents: list[str] = []
        in_rules = False
        groups: dict[str, list[tuple[bool, str]]] = {}
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (p.strip() for p in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if in_rules:
                    agents, in_rules = [], False
                agents.append(value.lower())
                for a in agents:
                    groups.setdefault(a, [])
            elif key in ("allow", "disallow"):
                in_rules = True
                if not value:
                    continue
                for a in agents:
                    groups.setdefault(a, []).append((key == "allow", value))
        ua = user_agent.lower()
        specific = [a for a in groups if a != "*" and a in ua]
        self.rules = groups[specific[0]] if specific else groups.get("*", [])

    @staticmethod
    def _to_regex(pattern: str) -> re.Pattern:
        anchored = pattern.endswith("$")
        body = pattern[:-1] if anchored else pattern
        regex = ".*".join(re.escape(part) for part in body.split("*"))
        return re.compile("^" + regex + ("$" if anchored else ""))

    def can_fetch(self, url: str) -> bool:
        parts = urlsplit(url)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        best: Optional[tuple[int, bool]] = None
        for allow, pattern in self.rules:
            if self._to_regex(pattern).match(path):
                candidate = (len(pattern), allow)
                # Longest match wins; on a tie, allow wins.
                if best is None or candidate[0] > best[0] or (
                    candidate[0] == best[0] and allow
                ):
                    best = candidate
        return True if best is None else best[1]


def extract_detail(page_html: str) -> Optional[dict]:
    """Return the JobPost/Detail object embedded in the page (Angular ng-state), if any."""
    m = re.search(r'<script id="ng-state"[^>]*>(.*?)</script>', page_html, re.S)
    if m:
        try:
            state = json.loads(m.group(1))
            for key, value in state.items():
                if "JobPost/Detail" in key and isinstance(value, dict):
                    return value
        except json.JSONDecodeError:
            pass
    return None


def extract_json_ld(page_html: str) -> Optional[dict]:
    for m in re.finditer(
        r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page_html, re.S
    ):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            return data
    return None


def _fa(item) -> str:
    if not isinstance(item, dict):
        return ""
    return (item.get("titleFa") or item.get("title") or item.get("titleEn") or "").strip()


def parse_job_page(page_html: str, job_id, final_url: str = "") -> Optional[dict]:
    """Keep only matching-relevant fields from a job page."""
    detail = extract_detail(page_html)
    ld = extract_json_ld(page_html)
    if detail is None and ld is None:
        return None

    out = {
        "id": int(job_id),
        "url": final_url or job_url(job_id),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    if detail is not None:
        out["description"] = html_to_text(detail.get("description") or "")
        out["skills"] = [s for s in (_fa(x) for x in detail.get("skills") or []) if s]
        out["software"] = [
            {"name": _fa(x.get("software")), "level": _fa(x.get("skill"))}
            for x in detail.get("softwareRequirements") or []
            if _fa(x.get("software"))
        ]
        out["languages"] = [
            {"name": _fa(x.get("language")), "level": _fa(x.get("skill"))}
            for x in detail.get("languageRequirements") or []
            if _fa(x.get("language"))
        ]
        academic = []
        for x in detail.get("academicRequirements") or []:
            if isinstance(x, dict):
                # Structure varies; keep every nested title (degree level, field, ...).
                parts = [_fa(v) for v in x.values() if isinstance(v, dict)]
                academic.append(" - ".join(p for p in parts if p))
        out["academic"] = [a for a in academic if a]
        out["work_days"] = detail.get("workDays") or ""
        out["is_remote"] = detail.get("isRemote")
        out["military_service_required"] = detail.get("shouldDoneMilitaryService")
        out["age_min"] = detail.get("requiredAgeMin")
        out["age_max"] = detail.get("requiredAgeMax")
    else:
        out["description"] = (ld.get("description") or "").strip()
        out["skills"], out["software"], out["languages"], out["academic"] = [], [], [], []
        out["work_days"] = ld.get("workHours") or ""

    return out


@dataclass
class CrawlStats:
    fetched: int = 0
    cached: int = 0
    disallowed: int = 0
    failed: int = 0
    errors: list = field(default_factory=list)


class JobVisionEnricher:
    def __init__(
        self,
        cache_dir: Path,
        delay: float = 1.5,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = 30.0,
        max_retries: int = 3,
        session: Optional[requests.Session] = None,
        sleep: Callable[[float], None] = time.sleep,
        robots: Optional[RobotsRules] = None,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.sleep = sleep
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept-Language": "fa"})
        self.user_agent = user_agent
        self._robots = robots
        self._last_request = 0.0

    def cache_path(self, job_id) -> Path:
        return self.cache_dir / f"{int(job_id)}.json"

    def load_cached(self, job_id) -> Optional[dict]:
        p = self.cache_path(job_id)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return None

    @property
    def robots(self) -> RobotsRules:
        if self._robots is None:
            r = self._get(f"{BASE_URL}/robots.txt")
            self._robots = RobotsRules(r.text if r is not None and r.ok else "", self.user_agent)
        return self._robots

    def _throttle(self):
        wait = self.delay - (time.monotonic() - self._last_request)
        if wait > 0:
            self.sleep(wait)
        self._last_request = time.monotonic()

    def _get(self, url: str) -> Optional[requests.Response]:
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                r = self.session.get(url, timeout=self.timeout)
            except requests.RequestException:
                self.sleep(self.delay * (2 ** attempt))
                continue
            if r.status_code in (429, 500, 502, 503, 504):
                retry_after = r.headers.get("Retry-After", "")
                self.sleep(float(retry_after) if retry_after.isdigit() else self.delay * (2 ** (attempt + 1)))
                continue
            return r
        return None

    def enrich_one(self, job_id, stats: Optional[CrawlStats] = None) -> Optional[dict]:
        stats = stats or CrawlStats()
        cached = self.load_cached(job_id)
        if cached is not None:
            stats.cached += 1
            return cached

        url = job_url(job_id)
        if not self.robots.can_fetch(url):
            stats.disallowed += 1
            return None

        r = self._get(url)
        if r is None or not r.ok:
            stats.failed += 1
            stats.errors.append((job_id, None if r is None else r.status_code))
            return None

        record = parse_job_page(r.text, job_id, final_url=_readable_url(r.url))
        if record is None:
            stats.failed += 1
            stats.errors.append((job_id, "unparseable"))
            return None

        self.cache_path(job_id).write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8"
        )
        stats.fetched += 1
        return record

    def enrich_many(
        self, job_ids: Iterable, progress: Optional[Callable[[int, int, CrawlStats], None]] = None
    ) -> CrawlStats:
        ids = list(job_ids)
        stats = CrawlStats()
        for i, job_id in enumerate(ids, 1):
            self.enrich_one(job_id, stats)
            if progress:
                progress(i, len(ids), stats)
        return stats


def _readable_url(url: str) -> str:
    """requests returns percent-encoded slugs; store a URL that is still valid but readable."""
    from urllib.parse import unquote

    try:
        decoded = unquote(url)
        quote(decoded, safe=":/")
        return decoded
    except Exception:
        return url
