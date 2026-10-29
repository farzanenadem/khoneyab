"""Persistent hybrid index: dense embeddings (numpy) + BM25 over weighted fields.

The corpus is small (thousands of ads), so exact scoring over every document is
fast and needs no external vector database. The index lives in a directory:
jobs.jsonl, embeddings.npy and meta.json.
"""

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from agent.utilities.persian_text import tokenize

# Field weights for BM25: a field's tokens are repeated this many times.
BM25_FIELD_WEIGHTS = {
    "title": 3,
    "categories": 2,
    "skills": 2,
    "software": 2,
    "industry": 1,
    "seniority": 1,
    "work_type": 1,
    "location": 1,
    "company": 1,
    "benefits": 1,
    "academic": 1,
    "description": 1,
}
MAX_DESCRIPTION_CHARS_FOR_EMBEDDING = 1500


def job_fields(job: dict) -> dict[str, str]:
    return {
        "title": job["title"],
        "categories": " ، ".join(job.get("categories") or []),
        "skills": " ، ".join(job.get("skills") or []),
        "software": " ، ".join(s["name"] for s in job.get("software") or []),
        "industry": job.get("industry") or "",
        "seniority": job.get("seniority") or "",
        "work_type": job.get("work_type") or "",
        "location": " ".join(x for x in (job.get("province"), job.get("city")) if x),
        "company": job.get("company") or "",
        "benefits": " ، ".join(job.get("benefits") or []),
        "academic": " ، ".join(job.get("academic") or []),
        "description": job.get("description") or "",
    }


def passage_text(job: dict) -> str:
    """Text embedded for a job: structured fields first, then the description."""
    f = job_fields(job)
    parts = [
        f"عنوان شغل: {f['title']}",
        f"دسته‌بندی: {f['categories']}" if f["categories"] else "",
        f"صنعت: {f['industry']}" if f["industry"] else "",
        f"سطح: {f['seniority']}" if f["seniority"] else "",
        f"مهارت‌ها: {f['skills']} {f['software']}".strip() if (f["skills"] or f["software"]) else "",
        f"شرح: {f['description'][:MAX_DESCRIPTION_CHARS_FOR_EMBEDDING]}" if f["description"] else "",
    ]
    return "\n".join(p for p in parts if p)


def bm25_tokens(job: dict) -> list[str]:
    tokens: list[str] = []
    for name, text in job_fields(job).items():
        tokens.extend(tokenize(text) * BM25_FIELD_WEIGHTS[name])
    return tokens


class BM25:
    def __init__(self, docs_tokens: Sequence[Sequence[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.n = len(docs_tokens)
        self.doc_len = np.array([len(t) for t in docs_tokens], dtype=np.float32)
        self.avgdl = float(self.doc_len.mean()) if self.n else 0.0
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for i, toks in enumerate(docs_tokens):
            for term, tf in Counter(toks).items():
                self.postings[term].append((i, tf))
        self.idf = {
            term: math.log(1 + (self.n - len(p) + 0.5) / (len(p) + 0.5))
            for term, p in self.postings.items()
        }

    def scores(self, query_tokens: Sequence[str]) -> np.ndarray:
        out = np.zeros(self.n, dtype=np.float32)
        if not self.n:
            return out
        norm = self.k1 * (1 - self.b + self.b * self.doc_len / (self.avgdl or 1.0))
        for term in set(query_tokens):
            postings = self.postings.get(term)
            if not postings:
                continue
            idx = np.fromiter((p[0] for p in postings), dtype=np.int64)
            tf = np.fromiter((p[1] for p in postings), dtype=np.float32)
            out[idx] += self.idf[term] * tf * (self.k1 + 1) / (tf + norm[idx])
        return out


class Embedder:
    """Wraps a LangChain-style embeddings object and adds model-specific prefixes (e5)."""

    def __init__(self, embeddings, model_name: str, query_prefix: str = "", passage_prefix: str = ""):
        self.embeddings = embeddings
        self.model_name = model_name
        self.query_prefix = query_prefix
        self.passage_prefix = passage_prefix

    @staticmethod
    def _normalize(vectors) -> np.ndarray:
        arr = np.asarray(vectors, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr[None, :]
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return arr / norms

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        return self._normalize(
            self.embeddings.embed_documents([self.passage_prefix + t for t in texts])
        )

    def embed_query(self, text: str) -> np.ndarray:
        return self._normalize(self.embeddings.embed_query(self.query_prefix + text))[0]


def corpus_fingerprint(jobs: list[dict]) -> str:
    h = hashlib.sha256()
    for job in jobs:
        h.update(passage_text(job).encode("utf-8"))
    return h.hexdigest()[:16]


class JobIndex:
    def __init__(self, jobs: list[dict], embeddings: np.ndarray, meta: Optional[dict] = None):
        if len(jobs) != len(embeddings):
            raise ValueError(f"{len(jobs)} jobs but {len(embeddings)} embedding rows")
        self.jobs = jobs
        self.embeddings = embeddings.astype(np.float32)
        self.meta = meta or {}
        self.bm25 = BM25([bm25_tokens(j) for j in jobs])
        self.id_to_pos = {j["id"]: i for i, j in enumerate(jobs)}

    def __len__(self):
        return len(self.jobs)

    def add_jobs(self, jobs: list[dict], embeddings: np.ndarray) -> None:
        """Append jobs at runtime (live crawl) and refresh the lexical index."""
        if not jobs:
            return
        self.jobs = self.jobs + jobs
        self.embeddings = np.vstack([self.embeddings, embeddings.astype(np.float32)])
        self.bm25 = BM25([bm25_tokens(j) for j in self.jobs])
        self.id_to_pos = {j["id"]: i for i, j in enumerate(self.jobs)}
        self.meta["count"] = len(self.jobs)

    def remove_jobs(self, ids: set) -> int:
        """Drop jobs by id (stale live/cached ads) and refresh the lexical index."""
        keep = [i for i, j in enumerate(self.jobs) if j["id"] not in ids]
        removed = len(self.jobs) - len(keep)
        if removed:
            self.jobs = [self.jobs[i] for i in keep]
            self.embeddings = self.embeddings[keep]
            self.bm25 = BM25([bm25_tokens(j) for j in self.jobs])
            self.id_to_pos = {j["id"]: i for i, j in enumerate(self.jobs)}
            self.meta["count"] = len(self.jobs)
        return removed

    def replace_job(self, job: dict, embedding: np.ndarray) -> None:
        pos = self.id_to_pos[job["id"]]
        self.jobs[pos] = job
        self.embeddings[pos] = embedding
        self.bm25 = BM25([bm25_tokens(j) for j in self.jobs])

    @classmethod
    def build(cls, jobs: list[dict], embedder: Embedder, batch_size: int = 64) -> "JobIndex":
        texts = [passage_text(j) for j in jobs]
        chunks = [
            embedder.embed_passages(texts[i : i + batch_size])
            for i in range(0, len(texts), batch_size)
        ]
        vectors = np.vstack(chunks) if chunks else np.zeros((0, 1), dtype=np.float32)
        meta = {
            "model": embedder.model_name,
            "query_prefix": embedder.query_prefix,
            "passage_prefix": embedder.passage_prefix,
            "count": len(jobs),
            "enriched": sum(1 for j in jobs if j.get("enriched")),
            "dim": int(vectors.shape[1]) if len(vectors) else 0,
            "fingerprint": corpus_fingerprint(jobs),
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        return cls(jobs, vectors, meta)

    def save(self, directory: Path) -> None:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        with open(directory / "jobs.jsonl", "w", encoding="utf-8") as f:
            for job in self.jobs:
                f.write(json.dumps(job, ensure_ascii=False) + "\n")
        np.save(directory / "embeddings.npy", self.embeddings)
        (directory / "meta.json").write_text(
            json.dumps(self.meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @classmethod
    def load(cls, directory: Path) -> "JobIndex":
        directory = Path(directory)
        with open(directory / "jobs.jsonl", encoding="utf-8") as f:
            jobs = [json.loads(line) for line in f if line.strip()]
        embeddings = np.load(directory / "embeddings.npy")
        meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
        return cls(jobs, embeddings, meta)
