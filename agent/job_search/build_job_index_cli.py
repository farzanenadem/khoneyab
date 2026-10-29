from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from agent._core.settings import get_logger
from agent.agent_jobs.snap.arguments import get_args
from agent.job_search.dataset import load_jobs
from agent.job_search.index import JobIndex
from agent.job_search.service import create_embedder, load_config, resolve

logger = get_logger("build_job_index")


def main() -> None:
    args = get_args("build_job_index")
    config = load_config(resolve(args.config))
    if args.device:
        config["embedding"]["args"]["device"] = args.device

    jobs = load_jobs([resolve(args.jobs), resolve(args.live_jobs), resolve(args.other_jobs)], resolve(args.details_dir))
    enriched = sum(1 for j in jobs if j["enriched"])
    logger.info(f"Loaded {len(jobs)} unique jobs ({enriched} with crawled description)")

    start = time.time()
    embedder = create_embedder(config)
    if embedder is None:
        index = JobIndex(jobs, np.zeros((len(jobs), 1), dtype=np.float32), {"model": "none", "count": len(jobs), "enriched": enriched, "dim": 0})
    else:
        index = JobIndex.build(jobs, embedder, batch_size=config["embedding"]["args"].get("batch_size", 32))
    index_dir = resolve(config["index_dir"])
    index.save(index_dir)
    logger.info(f"Index saved to {index_dir} | {len(index)} jobs | dim={index.meta['dim']} | "
                f"{time.time() - start:.1f}s")


if __name__ == "__main__":
    main()
