"""Build the search service and embedder from configs/job_search.yaml."""

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
    return JobSearchService(
        index,
        embedder,
        synonym_groups=load_synonym_groups(resolve(config["synonyms"])),
        weights=ranking_weights(config),
        live_crawler=create_live_crawler(config),
        min_relative_score=float(config.get("ranking", {}).get("min_relative_score", 0.6)),
        recency_half_life_days=float(config.get("ranking", {}).get("recency_half_life_days", 14)),
    )


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
    return LiveCrawler(
        JobVisionListClient(delay=float(conf.get("delay", 0.3)), timeout=float(conf.get("timeout", 10))),
        resolve(conf["store"]),
        pages_per_keyword=int(conf.get("pages_per_keyword", 1)),
        max_keywords=int(conf.get("max_keywords", 4)),
        enricher=enricher,
    )
