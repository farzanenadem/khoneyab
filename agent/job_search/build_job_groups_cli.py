from __future__ import annotations

import time
from datetime import datetime, timezone

from agent._core.settings import get_logger
from agent.agent_jobs.snap.arguments import get_args
from agent.job_search.job_groups import (
    DATASET_URL,
    JobGroups,
    build_groups,
    download_dataset,
    read_dataset,
    sample_records,
)
from agent.job_search.service import create_embedder, create_qdrant, load_config, resolve

logger = get_logger("build_job_groups")


def main() -> None:
    args = get_args("build_job_groups")
    config = load_config(resolve(args.config))
    if args.device:
        config["embedding"]["args"]["device"] = args.device
    conf = config["job_groups"]

    dataset = resolve(args.dataset)
    if not dataset.exists():
        logger.info(f"Downloading the JobVision dataset to {dataset}")
        download_dataset(dataset, DATASET_URL)

    start = time.time()
    records = read_dataset(dataset)
    sample = sample_records(records, args.per_category, args.since, args.seed)
    categories = len({r["category"] for r in sample})
    logger.info(f"Read {len(records)} rows; sampled {len(sample)} rows over {categories} categories")

    embedder = create_embedder(config)
    if embedder is None:
        raise SystemExit("Job groups need the embedding model; see README (model download).")
    groups, centroids, titles = build_groups(
        sample, embedder, k_min=args.k_min, k_max=args.k_max, min_rows=args.min_rows,
        min_skill_share=args.min_skill_share, seed=args.seed,
        batch_size=config["embedding"]["args"].get("batch_size", 32), log=logger.info,
    )
    split = [g["silhouette"] for g in groups if g["silhouette"] > 0]
    meta = {
        "model": embedder.model_name,
        "dataset": "JobVision/JobVision_Jobposts_Dataset (CC BY-NC 4.0)",
        "rows_sampled": len(sample),
        "categories": categories,
        "titles": len(titles),
        "mean_silhouette_split_categories": round(sum(split) / len(split), 3) if split else None,
        "sparse_skill_groups": sum(1 for g in groups if g["skills_sparse"]),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    job_groups = JobGroups.create(create_qdrant(conf), groups, centroids, titles, meta, conf.get("collection", "job_groups"))
    job_groups.save_local(resolve(conf["dir"]))
    logger.info(
        f"{len(groups)} job groups over {categories} categories stored in Qdrant "
        f"'{conf.get('collection', 'job_groups')}' | {len(titles)} titles indexed | "
        f"mean silhouette (split categories) = {meta['mean_silhouette_split_categories']} | "
        f"{time.time() - start:.1f}s"
    )


if __name__ == "__main__":
    main()
