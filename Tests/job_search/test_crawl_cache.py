import numpy as np
from qdrant_client import QdrantClient

from agent.job_search.crawl_cache import CrawlCache
from agent.job_search.index import JobIndex
from agent.job_search.search import JobSearchService

from .conftest import NOW


def _new_job(base: dict, job_id: str, title: str) -> dict:
    return {**base, "id": job_id, "title": title}


def _cache(client, embedder, index):
    return CrawlCache(client, embedder.model_name, int(index.meta["dim"]))


def test_live_jobs_survive_a_restart_without_reembedding(jobs, embedder, synonyms):
    client = QdrantClient(":memory:")
    index = JobIndex.build(jobs, embedder)
    first = JobSearchService(index, embedder, synonyms, now=lambda: NOW, crawl_cache=_cache(client, embedder, index))
    crawled = [_new_job(jobs[0], "live-1", "برنامه نویس Rust"), _new_job(jobs[1], "live-2", "مهندس داده")]
    assert first.add_jobs(crawled) == 2

    # "Restart": a fresh service over the original index gets the crawled ads back from Qdrant.
    index2 = JobIndex.build(jobs, embedder)
    calls = []
    original = embedder.embed_passages
    embedder.embed_passages = lambda texts: calls.append(len(texts)) or original(texts)
    try:
        second = JobSearchService(index2, embedder, synonyms, now=lambda: NOW, crawl_cache=_cache(client, embedder, index2))
    finally:
        embedder.embed_passages = original
    assert second.cached_jobs_loaded == 2
    assert {"live-1", "live-2"} <= set(second.index.id_to_pos)
    assert calls == []  # vectors came from the cache
    pos = second.index.id_to_pos["live-1"]
    assert np.allclose(second.index.embeddings[pos], first.index.embeddings[first.index.id_to_pos["live-1"]], atol=1e-5)


def test_enrichment_overwrites_the_cached_ad(jobs, embedder, synonyms):
    client = QdrantClient(":memory:")
    index = JobIndex.build(jobs, embedder)
    cache = _cache(client, embedder, index)
    service = JobSearchService(index, embedder, synonyms, now=lambda: NOW, crawl_cache=cache)
    service.add_jobs([_new_job(jobs[0], "live-1", "برنامه نویس")])
    service.update_job({**_new_job(jobs[0], "live-1", "برنامه نویس"), "description": "شرح کامل", "enriched": True})
    cached, _, _ = cache.load()
    assert cache.count() == 1 and cached[0]["description"] == "شرح کامل"


def test_cache_from_another_model_is_ignored(jobs, embedder):
    client = QdrantClient(":memory:")
    index = JobIndex.build(jobs, embedder)
    CrawlCache(client, "other-model", int(index.meta["dim"])).put([jobs[0]], index.embeddings[:1])
    loaded, vectors, _ = _cache(client, embedder, index).load()
    assert loaded == [] and len(vectors) == 0


def test_unreachable_qdrant_does_not_break_search(jobs, embedder, synonyms):
    class Down:
        def __getattr__(self, name):
            raise ConnectionError("qdrant down")

    index = JobIndex.build(jobs, embedder)
    service = JobSearchService(index, embedder, synonyms, now=lambda: NOW,
                               crawl_cache=CrawlCache(Down(), embedder.model_name, int(index.meta["dim"])))
    assert service.cached_jobs_loaded == 0
    assert service.add_jobs([_new_job(jobs[0], "live-1", "برنامه نویس")]) == 1


def test_each_search_drops_expired_and_too_old_cached_ads(jobs, embedder, synonyms):
    from datetime import timedelta

    client = QdrantClient(":memory:")
    index = JobIndex.build(jobs, embedder)
    cache = _cache(client, embedder, index)
    clock = {"now": NOW}
    service = JobSearchService(index, embedder, synonyms, now=lambda: clock["now"], crawl_cache=cache,
                               min_relative_score=0.0, cache_max_age_days=14)
    expired = {**_new_job(jobs[0], "live-exp", "برنامه نویس"), "expires": (NOW - timedelta(days=1)).isoformat()}
    fresh = {**_new_job(jobs[1], "live-ok", "مهندس داده"), "expires": (NOW + timedelta(days=30)).isoformat()}
    service.add_jobs([expired, fresh])
    base = len(jobs)

    first = service.search("برنامه نویس")["cache_check"]
    assert first["removed"] == 1 and first["reasons"] == {"expired": 1}
    assert "live-exp" not in service.index.id_to_pos and "live-ok" in service.index.id_to_pos
    assert cache.count() == 1

    clock["now"] = NOW + timedelta(days=15)  # fresh ad has now been cached longer than 14 days
    second = service.search("داده")["cache_check"]
    assert second["reasons"] == {"too_old": 1}
    assert len(service.index) == base and cache.count() == 0  # only the original index is left


def test_stale_cache_entries_are_not_loaded_after_restart(jobs, embedder, synonyms):
    from datetime import timedelta

    client = QdrantClient(":memory:")
    index = JobIndex.build(jobs, embedder)
    expired = {**_new_job(jobs[0], "live-exp", "برنامه نویس"), "expires": (NOW - timedelta(days=1)).isoformat()}
    _cache(client, embedder, index).put([expired], index.embeddings[:1])
    index2 = JobIndex.build(jobs, embedder)
    service = JobSearchService(index2, embedder, synonyms, now=lambda: NOW, crawl_cache=_cache(client, embedder, index2))
    assert service.cached_jobs_loaded == 0 and "live-exp" not in service.index.id_to_pos
