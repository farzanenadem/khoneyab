"""Live crawl: fetch fresh ads for the user's keywords from several job boards while they search.

Sources (all queried in parallel, each with its own rate limit):
  * JobVision public list API      -> raw records, normalized like the dataset
  * Jobinja keyword search page    -> normalized; descriptions added in the background
  * IranTalent category pages      -> normalized, descriptions included

New ads are added to the in-memory index and appended to data/live/ (so the next
index build keeps them).
"""

import json
import queue
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Iterable, Optional

from agent._core.settings import get_logger
from agent.job_search.crawler import JobVisionEnricher
from agent.job_search.dataset import normalize_listing
from agent.job_search.jobvision_crawler import JobVisionListClient

logger = get_logger("live_crawl")


class LiveCrawler:
    def __init__(
        self,
        client: Optional[JobVisionListClient],
        store_path: Path,
        pages_per_keyword: int = 1,
        max_keywords: int = 4,
        enricher: Optional[JobVisionEnricher] = None,
        jobinja=None,
        irantalent=None,
    ):
        self.client = client
        self.jobinja = jobinja
        self.irantalent = irantalent
        self.store_path = Path(store_path)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        # Already-normalized ads from the other boards go to a sibling file.
        self.other_store_path = self.store_path.with_name("other_sources.jsonl")
        self.pages_per_keyword = pages_per_keyword
        self.max_keywords = max_keywords
        self.enricher = enricher
        self._write_lock = threading.Lock()
        self._queue: "queue.Queue[tuple[str, dict, dict]]" = queue.Queue()
        self._on_enriched: Optional[Callable[[dict], None]] = None
        if enricher is not None or jobinja is not None:
            threading.Thread(target=self._enrich_worker, daemon=True).start()

    def on_enriched(self, callback: Callable[[dict], None]) -> None:
        self._on_enriched = callback

    def _tasks(self, keywords: list[str], variants: dict) -> list[tuple[str, Callable[[], list]]]:
        tasks = []
        if self.client is not None:
            tasks.append(("jobvision", lambda: self.client.search(keywords, pages=self.pages_per_keyword)))
        if self.jobinja is not None:
            for kw in keywords:
                tasks.append(("jobinja", lambda kw=kw: self.jobinja.search(kw)))
        if self.irantalent is not None:
            slugs = []
            for kw in keywords:
                for slug in self.irantalent.slugs_for(variants.get(kw) or [kw], limit=1):
                    if slug not in slugs:
                        slugs.append(slug)
            for slug in slugs[:3]:
                tasks.append(("irantalent", lambda slug=slug: self.irantalent.search_slug(slug)))
        return tasks

    def fetch(self, keywords: Iterable[str], known_ids: set, variants: Optional[dict] = None) -> list[dict]:
        """Crawl every source in parallel and return normalized jobs not already indexed."""
        keywords = [k for k in dict.fromkeys(keywords) if k][: self.max_keywords]
        tasks = self._tasks(keywords, variants or {})
        jobs, new_raw, new_other, counts, seen = [], [], [], {}, set(known_ids)
        if not tasks:
            return jobs
        with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as pool:
            futures = {pool.submit(fn): name for name, fn in tasks}
            for f in as_completed(futures):
                name = futures[f]
                try:
                    items = f.result() or []
                except Exception:
                    items = []  # one board failing must not break the search
                counts[name] = counts.get(name, 0) + len(items)
                for item in items:
                    if name == "jobvision":
                        job = normalize_listing(item)
                        raw = item
                    else:
                        job, raw = item, None
                    if job is None or job["id"] in seen:
                        continue
                    seen.add(job["id"])
                    jobs.append(job)
                    if raw is not None:
                        new_raw.append(raw)
                        if self.enricher is not None:
                            self._queue.put(("jobvision", raw, job))
                    else:
                        new_other.append(job)
                        if name == "jobinja" and not job["enriched"]:
                            self._queue.put(("jobinja", {}, job))
        with self._write_lock:
            for path, rows in ((self.store_path, new_raw), (self.other_store_path, new_other)):
                if rows:
                    with open(path, "a", encoding="utf-8") as f:
                        for row in rows:
                            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        # Keywords may come from a resume, so only counts are logged (NF-03).
        logger.info(f"live crawl ({len(keywords)} keywords): fetched {counts}, {len(jobs)} new")
        return jobs

    def _enrich_worker(self):
        while True:
            kind, raw, job = self._queue.get()
            try:
                if kind == "jobvision":
                    detail = self.enricher.enrich_one(raw["id"])
                    enriched = normalize_listing(raw, detail) if detail else None
                else:
                    enriched = self.jobinja.enrich(job)
                if enriched and self._on_enriched:
                    self._on_enriched(enriched)
            except Exception as e:  # background work must never crash the API
                logger.info(f"enrichment failed ({kind}): {type(e).__name__}")
