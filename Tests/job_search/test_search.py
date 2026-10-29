import numpy as np
import pytest

from agent.job_search.index import BM25, JobIndex, job_fields
from agent.job_search.search import JobSearchService, SearchFilters

from .test_query_parser import EXAMPLE


def ids(result):
    return [r["job"]["id"] for r in result["results"]]


def test_example_query_ranks_ai_jobs_first(service):
    res = service.search(EXAMPLE, top_k=6)
    top2 = set(ids(res)[:2])
    assert top2 == {"101", "105"}  # AI title + LLM/RAG/Python description
    assert res["total_candidates"] == 6
    scores = [r["score"] for r in res["results"]]
    assert scores == sorted(scores, reverse=True)


def test_explanations_quote_only_text_from_the_ad(service):
    res = service.search(EXAMPLE, top_k=6)
    for r in res["results"]:
        fields = job_fields(r["job"])
        for m in r["explanation"]["matched"]:
            evidence = m["evidence"].strip("…")
            assert evidence in fields[m["field"]], (m, r["job"]["id"])
    ds = next(r for r in res["results"] if r["job"]["id"] == "105")
    matched = {m["concept"] for m in ds["explanation"]["matched"]}
    assert {"python", "rag", "مدل زبانی بزرگ"} <= matched
    assert any(m["field"] == "description" for m in ds["explanation"]["matched"])


def test_missing_concepts_and_preferences_are_reported(service):
    res = service.search(EXAMPLE, top_k=6)
    ai = next(r for r in res["results"] if r["job"]["id"] == "101")
    assert "rag" in ai["explanation"]["missing"]
    loc = next(p for p in ai["explanation"]["preferences"] if p["type"] == "location")
    assert loc["ok"] is True and "تهران" in loc["text"]
    sales = service.search("کارشناس فروش در تهران", top_k=6)
    karaj = next(r for r in sales["results"] if r["job"]["id"] == "104")
    assert next(p for p in karaj["explanation"]["preferences"] if p["type"] == "location")["ok"] is False


def test_remote_preference_counts_as_location_alternative(service):
    res = service.search("برنامه نویس پایتون در تهران یا دورکاری", top_k=3)
    assert ids(res)[0] == "102"  # Isfahan but remote, title matches python
    pref = next(p for p in res["results"][0]["explanation"]["preferences"] if p["type"] == "location")
    assert pref["ok"] is True and "امکان دورکاری دارد" in pref["text"]


def test_hard_filters_are_enforced(service):
    res = service.search(EXAMPLE, SearchFilters(provinces=["اصفهان"]))
    assert ids(res) == ["102"]
    assert ids(service.search("حسابدار", SearchFilters(internship_only=True))) == ["106"]
    assert set(ids(service.search("کار", SearchFilters(remote_only=True)))) == {"102", "105"}
    assert ids(service.search("کار", SearchFilters(salary_disclosed_only=True))) == ["101"]
    assert "103" not in ids(service.search("حسابدار", SearchFilters(max_experience_years=3)))
    assert ids(service.search("کار", SearchFilters(min_salary=50))) == ["101"]
    assert service.search("کار", SearchFilters(provinces=["گیلان"]))["results"] == []


def test_strict_location_from_query_filters(service):
    res = service.search("فقط در کرج کارشناس فروش")
    assert ids(res) == ["104"]


def test_seniority_and_internship_preferences_boost(service):
    res = service.search("کارآموزی حسابداری بدون سابقه", top_k=2)
    assert ids(res)[0] == "106"
    res = service.search("حسابدار ارشد با ۵ سال سابقه", top_k=2)
    assert ids(res)[0] == "103"


def test_all_methods_return_results_and_reject_unknown(service):
    for method in ("hybrid", "semantic", "bm25", "keyword"):
        res = service.search("حسابدار", top_k=3, method=method)
        assert res["method"] == method and len(res["results"]) == 3
    with pytest.raises(ValueError):
        service.search("x", method="magic")


def test_empty_query_returns_no_results(service):
    assert service.search("   ")["results"] == []


def test_works_without_embedder(jobs, synonyms):
    index = JobIndex(jobs, np.zeros((len(jobs), 4), dtype=np.float32))
    svc = JobSearchService(index, None, synonyms)
    assert ids(svc.search("حسابدار ارشد", top_k=1)) == ["103"]


def test_index_save_load_roundtrip(tmp_path, service, embedder, synonyms):
    service.index.save(tmp_path)
    loaded = JobIndex.load(tmp_path)
    assert loaded.meta["count"] == len(service.index) and loaded.meta["model"] == "fake"
    assert np.allclose(loaded.embeddings, service.index.embeddings)
    again = JobSearchService(loaded, embedder, synonyms, min_relative_score=0.0, now=service.now)
    assert ids(again.search(EXAMPLE)) == ids(service.search(EXAMPLE))


def test_bm25_prefers_rarer_and_repeated_terms():
    bm = BM25([["python", "python", "django"], ["python"], ["excel"]])
    s = bm.scores(["python", "django"])
    assert s[0] > s[1] > s[2] == 0


def test_filter_options_reflect_dataset(service):
    opts = service.filter_options()
    assert opts["total"] == 6 and opts["remote_count"] == 2 and opts["internship_count"] == 1
    assert {"value": "تهران", "count": 4} in opts["provinces"]
    assert opts["salary_disclosed_count"] == 1


def test_get_job(service):
    assert service.get_job("101")["title"] == "کارشناس هوش مصنوعی"
    assert service.get_job("999") is None


def _with_dates(service, job_id, posted=None, expires=None):
    job = dict(service.get_job(job_id))
    if posted:
        job["date_posted"] = posted
    if expires:
        job["expires"] = expires
    service.update_job(job)


def test_expired_ads_are_hidden_unless_requested(service):
    _with_dates(service, "103", expires="2026-10-01T00:00:00Z")
    assert "103" not in ids(service.search("حسابدار ارشد", top_k=6))
    assert "103" in ids(service.search("حسابدار ارشد", SearchFilters(include_expired=True), top_k=6))


def test_recent_ads_rank_above_older_equal_matches(service):
    _with_dates(service, "103", posted="2026-07-01T00:00:00Z")   # old
    _with_dates(service, "106", posted="2026-10-29T08:00:00Z")   # today
    res = service.search("حسابداری", top_k=2)
    assert ids(res)[0] == "106"
    assert res["results"][0]["score_breakdown"]["recency"] > 0.9


def test_posted_within_days_filter(service):
    _with_dates(service, "101", posted="2026-10-28T00:00:00Z")
    res = service.search("کار", SearchFilters(posted_within_days=3), top_k=6)
    assert ids(res) == ["101"]


def test_newest_sort_orders_by_date(service):
    _with_dates(service, "103", posted="2026-10-01T00:00:00Z")
    _with_dates(service, "106", posted="2026-10-28T00:00:00Z")
    res = service.search("حسابدار", top_k=2, sort="newest")
    assert ids(res) == ["106", "103"]
    with pytest.raises(ValueError):
        service.search("x", sort="random")


def test_relevance_floor_drops_unrelated_ads(service):
    service.min_relative_score = 0.6
    res = service.search("حسابدار ارشد", top_k=6)
    assert "103" in ids(res)
    assert "104" not in ids(res)  # sales job: unrelated topic, even though in a preferred-free query
