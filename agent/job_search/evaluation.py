"""Ranking quality (RFP 10.2): Precision@k and nDCG@k against labelled judgements.

Labels file (JSON list):
  [{"query": "...", "relevant": ["<job id>", ...], "judged": ["<job id>", ...]}]
Unjudged results count as not relevant.
"""

import json
import math
from pathlib import Path
from typing import Sequence


def precision_at_k(ranked_ids: Sequence[str], relevant: set, k: int) -> float:
    if k <= 0:
        return 0.0
    return sum(1 for i in ranked_ids[:k] if i in relevant) / k


def ndcg_at_k(ranked_ids: Sequence[str], relevant: set, k: int) -> float:
    dcg = sum(1.0 / math.log2(rank + 2) for rank, i in enumerate(ranked_ids[:k]) if i in relevant)
    ideal = sum(1.0 / math.log2(rank + 2) for rank in range(min(len(relevant), k)))
    return dcg / ideal if ideal > 0 else 0.0


def load_labels(path: Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate(service, labels: list[dict], methods: Sequence[str] = ("hybrid", "keyword"), k_p: int = 5, k_ndcg: int = 10) -> dict:
    report = {}
    for method in methods:
        per_query = []
        for item in labels:
            relevant = {str(x) for x in item["relevant"]}
            res = service.search(item["query"], top_k=max(k_p, k_ndcg), method=method)
            ranked = [r["job"]["id"] for r in res["results"]]
            per_query.append({
                "query": item["query"],
                f"P@{k_p}": precision_at_k(ranked, relevant, k_p),
                f"nDCG@{k_ndcg}": ndcg_at_k(ranked, relevant, k_ndcg),
            })
        n = len(per_query) or 1
        report[method] = {
            f"P@{k_p}": sum(q[f"P@{k_p}"] for q in per_query) / n,
            f"nDCG@{k_ndcg}": sum(q[f"nDCG@{k_ndcg}"] for q in per_query) / n,
            "queries": per_query,
        }
    return report
