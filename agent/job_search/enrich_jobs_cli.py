from __future__ import annotations

from pathlib import Path

from agent._core.settings import get_logger
from agent.agent_jobs.snap.arguments import get_args
from agent.job_search.crawler import JobVisionEnricher
from agent.job_search.dataset import read_jsonl

logger = get_logger("enrich_jobs")


def main() -> None:
    args = get_args("enrich_jobs")

    ids = [r["id"] for r in read_jsonl(Path(args.jobs)) if r.get("id") is not None]
    limit = int(args.limit)
    if limit > 0:
        ids = ids[:limit]

    enricher = JobVisionEnricher(
        Path(args.cache_dir), delay=float(args.delay), user_agent=args.user_agent
    )

    def progress(i, total, stats):
        if i % 25 == 0 or i == total:
            logger.info(
                f"{i}/{total} fetched={stats.fetched} cached={stats.cached} "
                f"disallowed={stats.disallowed} failed={stats.failed}"
            )

    stats = enricher.enrich_many(ids, progress)
    logger.info(f"Enrichment done: {stats.fetched} fetched, {stats.cached} from cache, "
                f"{stats.disallowed} disallowed by robots.txt, {stats.failed} failed")
    if stats.errors:
        logger.info(f"First errors: {stats.errors[:10]}")


if __name__ == "__main__":
    main()
