from datetime import datetime, timezone

import pytest

from agent.job_search.dataset import deduplicate, normalize_listing
from agent.job_search.index import Embedder, JobIndex
from agent.job_search.query_parser import load_synonym_groups
from agent.job_search.search import JobSearchService
from agent._core.settings import ROOT_DIR

from .fixtures import DETAILS, RAW_JOBS, FakeEmbeddings


@pytest.fixture
def jobs():
    return deduplicate([normalize_listing(r, DETAILS.get(r["id"])) for r in RAW_JOBS])


@pytest.fixture
def embedder():
    return Embedder(FakeEmbeddings(), model_name="fake", query_prefix="query: ", passage_prefix="passage: ")


@pytest.fixture
def synonyms():
    return load_synonym_groups(ROOT_DIR / "configs" / "job_search_synonyms.yaml")


NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def service(jobs, embedder, synonyms):
    # Fixed clock so recency/expiry are deterministic; no relevance floor so small
    # fixtures keep every candidate (the floor has its own tests).
    return JobSearchService(
        JobIndex.build(jobs, embedder), embedder, synonyms, min_relative_score=0.0, now=lambda: NOW
    )
