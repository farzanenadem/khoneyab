import json

import pytest

from agent._core.settings import ROOT_DIR
from agent.job_search.dataset import deduplicate, load_jobs, normalize_listing, read_jsonl

from .fixtures import DETAILS, RAW_JOBS, make_raw, write_jsonl


def test_normalize_listing_maps_real_fields():
    job = normalize_listing(RAW_JOBS[0])
    assert job["id"] == "101"
    assert job["url"] == "https://jobvision.ir/jobs/101"
    assert job["title"] == "کارشناس هوش مصنوعی"
    assert job["company"] == "شرکت نمونه"
    assert (job["province"], job["city"]) == ("تهران", "تهران")
    assert job["categories"] == ["علوم داده / هوش مصنوعی"]
    assert job["salary_text"] == "40 - 60 میلیون تومان" and job["salary_max"] == 60
    assert job["enriched"] is False and job["description"] == ""


def test_salary_is_never_shown_when_source_hides_it():
    raw = make_raw(1, "x", salary=(10, 20))
    raw["properties"]["salaryCanBeShown"] = False
    job = normalize_listing(raw)
    assert job["salary_text"] == "" and job["salary_min"] is None and job["salary_max"] is None


def test_enrichment_adds_description_and_remote_flag():
    job = normalize_listing(RAW_JOBS[4], DETAILS[105])
    assert job["enriched"] and "RAG" in job["description"]
    assert job["software"][0]["name"] == "Python"
    assert job["is_remote"] is True
    assert job["url"].startswith("https://jobvision.ir/jobs/105/")


def test_records_without_id_or_title_are_skipped():
    assert normalize_listing({"id": None, "title": "x"}) is None
    assert normalize_listing({"id": 1, "title": "  "}) is None


def test_deduplicate_by_id_and_by_title_company_city():
    a = normalize_listing(make_raw(1, "حسابدار"))
    a_again = normalize_listing(make_raw(1, "حسابدار"))
    repost = normalize_listing(make_raw(2, "حسابدار"))
    other_city = normalize_listing(make_raw(3, "حسابدار", province="فارس", city="شیراز"))
    assert [j["id"] for j in deduplicate([a, a_again, repost, other_city])] == ["1", "3"]


def test_deduplicate_prefers_enriched_copy():
    bare = normalize_listing(make_raw(1, "Data Scientist"))
    rich = normalize_listing(make_raw(2, "Data Scientist"), DETAILS[105])
    assert deduplicate([bare, rich])[0]["enriched"] is True


def test_load_jobs_merges_cached_details(tmp_path):
    write_jsonl(tmp_path / "jobs.jsonl", RAW_JOBS)
    details = tmp_path / "details"
    details.mkdir()
    (details / "105.json").write_text(json.dumps(DETAILS[105], ensure_ascii=False), encoding="utf-8")
    jobs = load_jobs(tmp_path / "jobs.jsonl", details)
    assert len(jobs) == len(RAW_JOBS)
    assert [j["id"] for j in jobs if j["enriched"]] == ["105"]


def test_invalid_jsonl_line_reports_location(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text('{"id": 1}\n{oops\n', encoding="utf-8")
    with pytest.raises(ValueError, match="bad.jsonl:2"):
        read_jsonl(p)


REAL_DATASET = ROOT_DIR / "rfp" / "jobs.jsonl"


@pytest.mark.skipif(not REAL_DATASET.exists(), reason="rfp/jobs.jsonl not present")
def test_real_dataset_ingests_cleanly():
    raw = read_jsonl(REAL_DATASET)
    jobs = load_jobs(REAL_DATASET)
    assert len(jobs) >= 50
    assert len({j["id"] for j in jobs}) == len(jobs)
    raw_by_id = {str(r["id"]): r for r in raw}
    for job in jobs:
        src = raw_by_id[job["id"]]
        assert job["title"] == src["title"].strip()
        assert job["url"] == f"https://jobvision.ir/jobs/{job['id']}"
        if job["salary_text"]:
            assert src["properties"]["salaryCanBeShown"] and src["salary"]["titleFa"] == job["salary_text"]
