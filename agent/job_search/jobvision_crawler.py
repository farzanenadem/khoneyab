"""
Jobvision job-ads crawler (uses the site's own public JSON list API, no HTML parsing).

    python -m agent.job_search.jobvision_crawler                     # all ads, list fields only
    python -m agent.job_search.jobvision_crawler -k python -p 5      # 5 pages of "python" ads
    python -m agent.job_search.jobvision_crawler -k "داده" -k "هوش مصنوعی" -p 2

Output: <out>.jsonl (raw records, same format as rfp/jobs.jsonl) + <out>.csv (opens in Excel).

candidateapi.jobvision.ir/robots.txt allows only /api/v1/JobPost/List, so the
Detail API is not used; descriptions come from public job pages (crawler.py).
The same client powers the live crawl that runs alongside every user search.
"""
import argparse
import csv
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, Optional

import requests

from agent.job_search.crawler import DEFAULT_USER_AGENT

API = "https://candidateapi.jobvision.ir/api/v1/JobPost"
PAGE_SIZE = 30  # server caps it at 30


class JobVisionListClient:
    """Thread-safe, rate-limited client for the public job list API."""

    def __init__(self, delay: float = 0.5, timeout: float = 15.0, retries: int = 3,
                 user_agent: str = DEFAULT_USER_AGENT, session: Optional[requests.Session] = None):
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Content-Type": "application/json"})
        self._lock = threading.Lock()
        self._last = 0.0

    def _throttle(self):
        # Requests from parallel threads are still spaced by `delay` overall.
        with self._lock:
            wait = self.delay - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()

    def list_page(self, page: int = 1, keyword: Optional[str] = None) -> dict:
        body = {"pageSize": PAGE_SIZE, "requestedPage": page, "sortBy": 1, "searchId": None}
        if keyword:
            body["keyWord"] = keyword
        for attempt in range(self.retries):
            self._throttle()
            try:
                r = self.session.post(f"{API}/List", json=body, timeout=self.timeout)
                r.raise_for_status()
                return r.json()["data"]
            except (requests.RequestException, KeyError, ValueError):
                time.sleep(min(2 ** attempt, 4))
        raise RuntimeError(f"jobvision list failed: page={page} keyword={keyword!r}")

    def search(self, keywords: Iterable[str], pages: int = 1, workers: int = 4) -> list[dict]:
        """Fetch `pages` pages for every keyword in parallel; returns unique raw job records."""
        tasks = [(k, p) for k in dict.fromkeys(k.strip() for k in keywords if k and k.strip())
                 for p in range(1, pages + 1)]
        seen, out = set(), []
        if not tasks:
            return out
        with ThreadPoolExecutor(max_workers=min(workers, len(tasks))) as pool:
            futures = [pool.submit(self.list_page, p, k) for k, p in tasks]
            for f in as_completed(futures):
                try:
                    posts = f.result().get("jobPosts") or []
                except Exception:
                    continue  # one failed keyword must not break the search
                for post in posts:
                    if post.get("id") not in seen:
                        seen.add(post.get("id"))
                        out.append(post)
        return out


def flatten(p):
    g = lambda d, k="titleFa": (d or {}).get(k)
    loc = p.get("location") or {}
    return {
        "id": p["id"],
        "title": p["title"],
        "company": g(p.get("company"), "nameFa"),
        "province": g(loc.get("province")),
        "city": g(loc.get("city")),
        "category": " | ".join(c["titleFa"] for c in p.get("jobCategories") or []),
        "work_type": g(p.get("workType")),
        "seniority": g(p.get("seniorityLevel")),
        "salary": g(p.get("salary")),
        "industry": g(p.get("industry")),
        "gender": g(p.get("gender")),
        "remote": (p.get("properties") or {}).get("isRemote"),
        "activated": (p.get("activationTime") or {}).get("date"),
        "url": f"https://jobvision.ir/jobs/{p['id']}",
    }


def main():
    ap = argparse.ArgumentParser(description="Crawl jobvision.ir job ads")
    ap.add_argument("-k", "--keyword", action="append", help="search keyword (repeatable)")
    ap.add_argument("-p", "--pages", type=int, default=0, help="max pages per keyword (0 = all)")
    ap.add_argument("--delay", type=float, default=0.5, help="seconds between requests")
    ap.add_argument("-o", "--out", default="jobs", help="output file prefix")
    a = ap.parse_args()

    client = JobVisionListClient(delay=a.delay)
    seen, rows = set(), []
    with open(f"{a.out}.jsonl", "w", encoding="utf-8") as raw:
        for keyword in a.keyword or [None]:
            first = client.list_page(1, keyword)
            total_pages = -(-first["jobPostCount"] // PAGE_SIZE)
            pages = min(total_pages, a.pages) if a.pages else total_pages
            print(f"{keyword or 'all'}: {first['jobPostCount']:,} ads → crawling {pages} page(s)")
            for page in range(1, pages + 1):
                data = first if page == 1 else client.list_page(page, keyword)
                for p in data["jobPosts"]:
                    if p["id"] in seen:
                        continue
                    seen.add(p["id"])
                    rows.append(flatten(p))
                    raw.write(json.dumps(p, ensure_ascii=False) + "\n")
                print(f"\r  page {page}/{pages}  ·  {len(rows):,} ads", end="", flush=True)
            print()

    if rows:
        with open(f"{a.out}.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
    print(f"✓ saved {a.out}.csv and {a.out}.jsonl")


if __name__ == "__main__":
    main()
