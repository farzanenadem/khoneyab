"""Qdrant cache for live-crawled ads.

Every ad the live crawl adds to the index is upserted here together with its embedding,
so after an API restart the ads are loaded straight back into the index: no re-crawl and
no re-embedding. The cache is best-effort: if Qdrant is down, search keeps working and the
failure is only logged.

Point id = uuid5(job id), so re-crawls and enrichment updates overwrite the same point.
The collection is tied to the embedding model; a model change makes the cache be ignored.
"""

import time
import uuid
from typing import Optional

import numpy as np

from agent._core.settings import get_logger

logger = get_logger("crawl_cache")

COLLECTION = "crawled_jobs"
_NAMESPACE = uuid.UUID("6f1c2b4e-8f5a-4c1e-9d7b-3a2e5f0c1d42")


def point_id(job_id: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, job_id))


class CrawlCache:
    def __init__(self, client, model_name: str, dim: int, collection: str = COLLECTION):
        self.client = client
        self.model_name = model_name
        self.dim = dim
        self.collection = collection
        self._ready = False

    def _ensure(self) -> None:
        if self._ready:
            return
        from qdrant_client import models

        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                self.collection, vectors_config=models.VectorParams(size=self.dim, distance=models.Distance.COSINE)
            )
        self._ready = True

    def delete(self, job_ids: list[str]) -> int:
        if not job_ids:
            return 0
        try:
            from qdrant_client import models

            self.client.delete(self.collection, points_selector=models.PointIdsList(points=[point_id(i) for i in job_ids]))
            return len(job_ids)
        except Exception as e:
            logger.info(f"crawl cache delete failed: {type(e).__name__}")
            return 0

    def put(self, jobs: list[dict], vectors: np.ndarray) -> int:
        """Upsert ads with their vectors; returns how many were written (0 on failure)."""
        if not jobs:
            return 0
        try:
            from qdrant_client import models

            self._ensure()
            now = time.time()
            self.client.upsert(self.collection, points=[
                models.PointStruct(
                    id=point_id(job["id"]),
                    vector=np.asarray(vec, dtype=np.float32).tolist(),
                    payload={"job": job, "model": self.model_name, "cached_at": now},
                )
                for job, vec in zip(jobs, vectors)
            ])
            return len(jobs)
        except Exception as e:  # the cache must never break search
            logger.info(f"crawl cache write failed: {type(e).__name__}")
            return 0

    def load(self, batch: int = 512) -> tuple[list[dict], np.ndarray, list[float]]:
        """All cached ads embedded with this model, as (jobs, vectors, cached_at timestamps)."""
        jobs, vectors, cached_at = [], [], []
        empty = ([], np.zeros((0, self.dim), dtype=np.float32), [])
        try:
            if not self.client.collection_exists(self.collection):
                return empty
            offset = None
            while True:
                points, offset = self.client.scroll(
                    self.collection, limit=batch, offset=offset, with_payload=True, with_vectors=True
                )
                for p in points:
                    payload = p.payload or {}
                    if payload.get("model") == self.model_name and payload.get("job") and p.vector is not None:
                        jobs.append(payload["job"])
                        vectors.append(p.vector)
                        cached_at.append(float(payload.get("cached_at") or 0))
                if offset is None:
                    break
        except Exception as e:
            logger.info(f"crawl cache read failed: {type(e).__name__}")
            return empty
        return jobs, np.asarray(vectors, dtype=np.float32).reshape(len(vectors), self.dim), cached_at

    def count(self) -> Optional[int]:
        try:
            if not self.client.collection_exists(self.collection):
                return 0
            return self.client.count(self.collection, exact=True).count
        except Exception:
            return None
