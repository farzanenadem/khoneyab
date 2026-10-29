"""Additional job boards for the live crawl: Jobinja and IranTalent.

Both clients return jobs already normalized to the search schema.

* Jobinja (jobinja.ir): robots.txt allows everything; the public keyword search page
  is parsed, and each job page's schema.org JobPosting JSON-LD adds the description later.
* IranTalent (irantalent.com): robots.txt forbids its search pages (`/jobs-search`, any
  `?` URL), so keywords are mapped to the allowed category pages listed in its
  job-filter sitemap (e.g. /jobs/python-developer); each page embeds 30 full ads.
"""

import html
import json
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import quote

import requests

from agent.job_search.crawler import DEFAULT_USER_AGENT, RobotsRules
from agent.job_search.dataset import empty_job
from agent.utilities.persian_text import DIGITS, html_to_text


class PoliteClient:
    """requests session with a shared minimum delay, retries and robots.txt checks."""

    def __init__(self, base: str, delay: float = 1.0, timeout: float = 15.0, user_agent: str = DEFAULT_USER_AGENT,
                 session: Optional[requests.Session] = None, robots: Optional[RobotsRules] = None):
        self.base = base.rstrip("/")
        self.delay, self.timeout = delay, timeout
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept-Language": "fa"})
        self.user_agent = user_agent
        self._robots = robots
        self._lock = threading.Lock()
        self._last = 0.0

    @property
    def robots(self) -> RobotsRules:
        if self._robots is None:
            r = self._get_raw(f"{self.base}/robots.txt")
            self._robots = RobotsRules(r.text if r is not None and r.ok else "", self.user_agent)
        return self._robots

    def _get_raw(self, url: str) -> Optional[requests.Response]:
        for attempt in range(2):
            with self._lock:
                wait = self.delay - (time.monotonic() - self._last)
                if wait > 0:
                    time.sleep(wait)
                self._last = time.monotonic()
            try:
                r = self.session.get(url, timeout=self.timeout)
            except requests.RequestException:
                continue
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(2 * (attempt + 1), 4))
                continue
            return r
        return None

    def get(self, url: str) -> Optional[str]:
        if not self.robots.can_fetch(url):
            return None
        r = self._get_raw(url)
        return r.text if r is not None and r.ok else None


def _json_ld_job(page: str) -> Optional[dict]:
    for m in re.finditer(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', page, re.S):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            return data
    return None


def _split_place(text: str) -> tuple[str, str]:
    parts = [p.strip() for p in re.split(r"[،,]", text or "") if p.strip()]
    if not parts:
        return "", ""
    return parts[0], (parts[1] if len(parts) > 1 else parts[0])


# ---------------- Jobinja ----------------

class JobinjaClient(PoliteClient):
    SOURCE = "jobinja.ir"

    def __init__(self, **kw):
        super().__init__("https://jobinja.ir", **kw)

    def search(self, keyword: str, page: int = 1) -> list[dict]:
        url = f"{self.base}/jobs?filters%5Bkeywords%5D%5B0%5D={quote(keyword)}&page={page}"
        text = self.get(url)
        return self.parse_list(text) if text else []

    @classmethod
    def parse_list(cls, page: str, today: Optional[datetime] = None) -> list[dict]:
        today = today or datetime.now(timezone.utc)
        jobs = []
        for block in page.split('<li class="o-listView__item ')[1:]:
            link = re.search(r'class="c-jobListView__titleLink"[^>]*href="([^"]+)"[^>]*>\s*(.*?)\s*</a>', block, re.S)
            if not link:
                continue
            url = html.unescape(link.group(1)).split("?")[0]
            code = re.search(r"/jobs/([^/]+)/", url)
            metas = [html.unescape(re.sub(r"<[^>]+>", " ", m)).replace("‌", " ")
                     for m in re.findall(r'<li class="c-jobListView__metaItem">(.*?)</li>', block, re.S)]
            metas = [re.sub(r"\s+", " ", m).strip() for m in metas]
            company = metas[0] if metas else ""
            province, city = _split_place(metas[1] if len(metas) > 1 else "")
            contract = re.sub(r"\(.*", "", metas[2]).replace("قرارداد", "").strip() if len(metas) > 2 else ""
            days = re.search(r"\((.*?)روز پیش\)", block)
            posted = ""
            if days:
                n = days.group(1).translate(DIGITS).strip()
                if n.isdigit():
                    posted = (today - timedelta(days=int(n))).isoformat(timespec="seconds")
            elif "امروز" in block or "ساعت پیش" in block:
                posted = today.isoformat(timespec="seconds")
            title = html.unescape(re.sub(r"\s+", " ", link.group(2))).strip()
            jobs.append(empty_job(
                id=f"jobinja-{code.group(1) if code else url}",
                source=cls.SOURCE,
                url=url,
                title=title,
                company=company.split("|")[0].strip(),
                province=province,
                city=city,
                work_type=contract,
                is_remote="دورکاری" in contract,
                date_posted=posted,
            ))
        return jobs

    def enrich(self, job: dict) -> Optional[dict]:
        page = self.get(job["url"])
        ld = _json_ld_job(page) if page else None
        if not ld:
            return None
        job = dict(job)
        job["description"] = html_to_text(ld.get("description") or "")
        job["date_posted"] = ld.get("datePosted") or job["date_posted"]
        job["expires"] = ld.get("validThrough") or job["expires"]
        head = job["description"][:400].lower()
        if "remote" in str(ld.get("jobLocationType", "")).lower() or "دورکاری" in head or "remote" in head:
            job["is_remote"] = True
        job["enriched"] = True
        return job


# ---------------- IranTalent ----------------

class IranTalentClient(PoliteClient):
    SOURCE = "irantalent.com"
    SITEMAP = "https://www.irantalent.com/fa/job-filter/sitemap.xml"

    def __init__(self, slug_cache: Optional[Path] = None, **kw):
        super().__init__("https://www.irantalent.com", **kw)
        self.slug_cache = Path(slug_cache) if slug_cache else None
        self._slugs: Optional[list[str]] = None

    @property
    def slugs(self) -> list[str]:
        """Category slugs from the job-filter sitemap (location variants removed), cached for a day."""
        if self._slugs is None:
            cache = self.slug_cache
            if cache and cache.exists() and time.time() - cache.stat().st_mtime < 86400:
                self._slugs = json.loads(cache.read_text(encoding="utf-8"))
            else:
                text = self.get(self.SITEMAP) or ""
                locs = re.findall(r"<loc>https://www\.irantalent\.com/jobs/([^<]+)</loc>", text)
                self._slugs = sorted({l for l in locs if "-jobs-in-" not in l and not l.startswith("jobs-in-")})
                if cache and self._slugs:
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    cache.write_text(json.dumps(self._slugs), encoding="utf-8")
        return self._slugs

    def slugs_for(self, variants: Iterable[str], limit: int = 2) -> list[str]:
        """Category pages whose slug contains all words of an English keyword variant."""
        out = []
        for v in variants:
            words = [w for w in re.split(r"[^a-z0-9#+]+", v.lower()) if w]
            if not words or not all(w.isascii() for w in words):
                continue
            for slug in self.slugs:
                parts = slug.split("-")
                if all(w in parts for w in words) and slug not in out:
                    out.append(slug)
            if len(out) >= limit:
                break
        # Shortest (most general) category first.
        return sorted(out, key=len)[:limit]

    def search_slug(self, slug: str) -> list[dict]:
        page = self.get(f"{self.base}/jobs/{slug}")
        return self.parse_page(page) if page else []

    @classmethod
    def parse_page(cls, page: str) -> list[dict]:
        m = re.search(r'<script id="ng-state"[^>]*>(.*?)</script>', page, re.S)
        if not m:
            return []
        try:
            state = json.loads(m.group(1))
            items = state["serverSideSearchResult"]["data"]["data"]
        except (json.JSONDecodeError, KeyError, TypeError):
            return []
        return [j for j in (cls.normalize(x) for x in items) if j]

    @classmethod
    def normalize(cls, x: dict) -> Optional[dict]:
        if not x.get("id") or not (x.get("title_farsi") or x.get("title")):
            return None
        loc = x.get("location") or {}
        employer = x.get("employer") or {}
        brand = x.get("brand_data") or {}
        salary_text, smin, smax = "", None, None
        if x.get("is_show_salary") and (x.get("salary_from") or x.get("salary_to")):
            smin, smax = x.get("salary_from"), x.get("salary_to")
            nums = [f"{v:,}" for v in (smin, smax) if v]
            salary_text = " تا ".join(nums) + (" میلیون تومان" if max(v for v in (smin, smax) if v) < 10000 else " تومان")
        province = loc.get("title_farsi") or x.get("location_text_farsi") or ""
        work_type = (x.get("employment_type") or {}).get("title_farsi") or ""
        return empty_job(
            id=f"irantalent-{x['id']}",
            source=cls.SOURCE,
            url=f"https://www.irantalent.com/job/{x.get('slug') or 'job'}/{x['id']}",
            title=x.get("title_farsi") or x.get("title"),
            company=employer.get("name_farsi") or brand.get("company_legal_name_fa") or employer.get("name") or "",
            company_logo=employer.get("logo_path") or "",
            province=province,
            city=x.get("location_text_farsi") or province,
            categories=[c.get("title_farsi") for c in x.get("job_category") or [] if c.get("title_farsi")],
            work_type=work_type,
            seniority=", ".join(s.get("title_farsi") for s in x.get("seniority") or [] if s.get("title_farsi")),
            is_remote=x.get("work_type") in ("remote", "hybrid"),
            salary_text=salary_text,
            salary_min=smin,
            salary_max=smax,
            date_posted=x.get("lived_at") or x.get("created_at") or "",
            expires=x.get("expired_at") or "",
            description=html_to_text(x.get("role_description_farsi") or x.get("role_description") or ""),
            enriched=bool(x.get("role_description_farsi") or x.get("role_description")),
        )
