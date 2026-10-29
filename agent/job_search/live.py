"""Live crawl: fetch fresh JobVision ads for the user's keywords while they search.

New ads are normalized like the dataset, added to the in-memory index, appended to
data/live/jobs.jsonl (so the next index build keeps them) and, in a background
thread, enriched with their public job page (description, software, ...).
"""

import json
import queue
import threading
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
        client: JobVisionListClient,
        store_path: Path,
        pages_per_keyword: int = 1,
        max_keywords: int = 4,
        enricher: Optional[JobVisionEnricher] = None,
    ):
        self.client = client
        self.store_path = Path(store_path)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.pages_per_keyword = pages_per_keyword
        self.max_keywords = max_keywords
        self.enricher = enricher
        self._write_lock = threading.Lock()
        self._queue: "queue.Queue[tuple[dict, dict]]" = queue.Queue()
        self._on_enriched: Optional[Callable[[dict], None]] = None
        if enricher is not None:
            threading.Thread(target=self._enrich_worker, daemon=True).start()

    def on_enriched(self, callback: Callable[[dict], None]) -> None:
        self._on_enriched = callback

    def fetch(self, keywords: Iterable[str], known_ids: set) -> list[dict]:
        """Crawl the keywords in parallel and return normalized jobs not already indexed."""
        keywords = [k for k in dict.fromkeys(keywords) if k][: self.max_keywords]
        raws = self.client.search(keywords, pages=self.pages_per_keyword)
        new_raw = [r for r in raws if str(r.get("id")) not in known_ids]
        jobs = []
        for raw in new_raw:
            job = normalize_listing(raw)
            if job is not None:
                jobs.append(job)
                if self.enricher is not None:
                    self._queue.put((raw, job))
        if new_raw:
            with self._write_lock, open(self.store_path, "a", encoding="utf-8") as f:
                for raw in new_raw:
                    f.write(json.dumps(raw, ensure_ascii=False) + "\n")
        logger.info(f"live crawl {keywords}: {len(raws)} ads, {len(jobs)} new")
        return jobs

    def _enrich_worker(self):
        while True:
            raw, _ = self._queue.get()
            try:
                detail = self.enricher.enrich_one(raw["id"])
                if detail and self._on_enriched:
                    self._on_enriched(normalize_listing(raw, detail))
            except Exception as e:  # background work must never crash the API
                logger.info(f"enrichment failed for {raw.get('id')}: {e}")
