import math

from agent.job_search.evaluation import evaluate, ndcg_at_k, precision_at_k


def test_precision_at_k():
    assert precision_at_k(["a", "b", "c", "d", "e"], {"a", "c"}, 5) == 0.4
    assert precision_at_k([], {"a"}, 5) == 0.0


def test_ndcg_at_k():
    assert ndcg_at_k(["a", "b"], {"a", "b"}, 10) == 1.0
    expected = (1 / math.log2(3)) / (1 / math.log2(2))
    assert math.isclose(ndcg_at_k(["x", "a"], {"a"}, 10), expected)
    assert ndcg_at_k(["x"], set(), 10) == 0.0


def test_evaluate_compares_methods(service):
    labels = [
        {"query": "کارشناس هوش مصنوعی و مدل زبانی بزرگ", "relevant": ["101", "105"]},
        {"query": "حسابداری", "relevant": ["103", "106"]},
    ]
    report = evaluate(service, labels, methods=("hybrid", "keyword"))
    assert set(report) == {"hybrid", "keyword"}
    assert report["hybrid"]["nDCG@10"] >= report["keyword"]["nDCG@10"]
    assert 0 <= report["hybrid"]["P@5"] <= 1
