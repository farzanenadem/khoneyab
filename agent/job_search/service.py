"""Build the search service and embedder from configs/job_search.yaml."""

import os
from pathlib import Path
from typing import Optional

import yaml
from yaml.loader import SafeLoader

from agent._core.settings import ROOT_DIR
from agent.job_search.index import Embedder, JobIndex
from agent.job_search.query_parser import load_synonym_groups
from agent.job_search.search import JobSearchService
from agent.utilities.embeddings import create_embedding

CONFIG_PATH = ROOT_DIR / "configs" / "job_search.yaml"


def resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else (ROOT_DIR / p).resolve()


def load_config(path: Optional[Path] = None) -> dict:
    with open(path or CONFIG_PATH, "rb") as f:
        return yaml.load(f, Loader=SafeLoader)


def create_embedder(config: dict) -> Optional[Embedder]:
    """Returns None (lexical-only search) when the local model is not available."""
    conf = config["embedding"]
    args = dict(conf["args"])
    model = args["model"]
    if model.startswith(".") or model.startswith("/"):
        args["model"] = str(resolve(model))
        if not any(Path(args["model"]).glob("*.safetensors")):
            print(f"Embedding model not found at {args['model']}; using lexical-only ranking.")
            return None
    embeddings = create_embedding(conf["name"], **args)
    return Embedder(
        embeddings,
        model_name=model,
        query_prefix=conf.get("query_prefix", ""),
        passage_prefix=conf.get("passage_prefix", ""),
    )


def ranking_weights(config: dict) -> dict:
    r = config.get("ranking", {})
    return {
        "semantic": r.get("semantic_weight", 0.45),
        "lexical": r.get("lexical_weight", 0.25),
        "concept": r.get("concept_weight", 0.15),
        "preference": r.get("preference_weight", 0.15),
        "recency": r.get("recency_weight", 0.10),
    }


def create_search_service(config: Optional[dict] = None, embedder: Optional[Embedder] = None) -> JobSearchService:
    config = config or load_config()
    index_dir = resolve(config["index_dir"])
    if not (index_dir / "meta.json").exists():
        raise FileNotFoundError(
            f"No job index at {index_dir}. Build it with: python -m agent.job_search.build_job_index_cli"
        )
    index = JobIndex.load(index_dir)
    embedder = embedder or create_embedder(config)
    if index.meta.get("model") == "none":
        embedder = None
    if embedder is not None and index.meta.get("model") != embedder.model_name:
        raise ValueError(
            f"Index was built with {index.meta['model']} but config uses {embedder.model_name}; rebuild the index."
        )
    groups_conf = config.get("job_groups") or {}
    return JobSearchService(
        index,
        embedder,
        synonym_groups=load_synonym_groups(resolve(config["synonyms"])),
        weights=ranking_weights(config),
        live_crawler=create_live_crawler(config),
        min_relative_score=float(config.get("ranking", {}).get("min_relative_score", 0.6)),
        recency_half_life_days=float(config.get("ranking", {}).get("recency_half_life_days", 14)),
        job_groups=create_job_groups(config, embedder),
        group_weight=float(groups_conf.get("ranking_weight", 0.10)),
        group_top_k=int(groups_conf.get("top_k", 3)),
        group_live_keywords=int(groups_conf.get("live_keywords", 2)),
        crawl_cache=create_crawl_cache(config, embedder, index),
        cache_max_age_days=float((config.get("crawl_cache") or {}).get("max_age_days", 14)),
    )


def create_crawl_cache(config: dict, embedder: Optional[Embedder], index: JobIndex):
    """Qdrant cache for live-crawled ads, or None when disabled / Qdrant unreachable."""
    conf = config.get("crawl_cache") or {}
    if not conf.get("enabled") or embedder is None or not index.meta.get("dim"):
        return None
    try:
        from agent.job_search.crawl_cache import CrawlCache

        client = create_qdrant(conf)
        client.get_collections()  # fail fast if Qdrant is not running
        return CrawlCache(client, embedder.model_name, int(index.meta["dim"]), conf.get("collection", "crawled_jobs"))
    except Exception as e:
        print(f"Crawl cache unavailable (search works without it): {type(e).__name__}")
        return None


def create_qdrant(groups_conf: dict):
    from agent.job_search.job_groups import create_qdrant_client

    return create_qdrant_client(url=os.environ.get("QDRANT_URL") or groups_conf.get("qdrant_url", ""))


def create_job_groups(config: dict, embedder: Optional[Embedder]):
    """Job groups from Qdrant, or None (search works without them) when not built or reachable."""
    conf = config.get("job_groups") or {}
    if not conf.get("enabled") or embedder is None:
        return None
    try:
        from agent.job_search.job_groups import JobGroups

        groups = JobGroups.load(
            create_qdrant(conf), resolve(conf["dir"]), conf.get("collection", "job_groups"), weights=conf.get("weights"),
            synonym_groups=load_synonym_groups(resolve(config["synonyms"])),
        )
    except Exception as e:
        print(f"Job groups unavailable: {e}")
        return None
    if groups.meta.get("model") != embedder.model_name:
        print(f"Job groups were built with {groups.meta.get('model')}, search uses {embedder.model_name}; rebuild them.")
        return None
    return groups


def create_live_crawler(config: dict):
    conf = config.get("live_crawl") or {}
    if not conf.get("enabled"):
        return None
    from agent.job_search.crawler import JobVisionEnricher
    from agent.job_search.jobvision_crawler import JobVisionListClient
    from agent.job_search.live import LiveCrawler

    enricher = None
    if conf.get("enrich", True):
        enricher = JobVisionEnricher(resolve(conf["details_dir"]), delay=float(conf.get("enrich_delay", 1.5)))
    from agent.job_search.sources import IranTalentClient, JobinjaClient

    sources = conf.get("sources") or ["jobvision", "jobinja", "irantalent"]
    timeout = float(conf.get("timeout", 10))
    return LiveCrawler(
        JobVisionListClient(delay=float(conf.get("delay", 0.3)), timeout=timeout) if "jobvision" in sources else None,
        resolve(conf["store"]),
        jobinja=JobinjaClient(delay=float(conf.get("jobinja_delay", 1.0)), timeout=timeout) if "jobinja" in sources else None,
        irantalent=(
            IranTalentClient(slug_cache=resolve(conf["store"]).with_name("irantalent_slugs.json"),
                             delay=float(conf.get("irantalent_delay", 1.0)), timeout=timeout)
            if "irantalent" in sources else None
        ),
        pages_per_keyword=int(conf.get("pages_per_keyword", 1)),
        max_keywords=int(conf.get("max_keywords", 4)),
        enricher=enricher,
    )
