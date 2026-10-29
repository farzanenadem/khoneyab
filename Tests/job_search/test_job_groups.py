import json

import pytest

from agent.job_search.job_groups import (
    DATASET_COLUMNS,
    EXCLUDED_COLUMNS,
    JobGroups,
    build_groups,
    parse_software,
    read_dataset,
    sample_records,
    to_record,
)
from agent.job_search.search import JobSearchService

qdrant_client = pytest.importorskip("qdrant_client")

ACCOUNTING = "مالی و حسابداری"
SOFTWARE = "توسعه نرم افزار و برنامه نویسی"
LABOUR = "کارگر ساده / نیروی خدماتی"


def sw(*pairs):
    return json.dumps([{"TitleFa": fa, "TitleEn": en, "Level": "متوسط"} for fa, en in pairs], ensure_ascii=False)


def row(title, category, software="", experience=1, month="2024-01", remote=False):
    return {
        "Jobpost_RawTitle": title,
        "Jobpost_MainJobCategory": category,
        "Jobpost_SoftwareSkills": software,
        "Jobpost_AcademicFields": json.dumps([{"FieldType": "حسابداری", "DegreeLevel": "کارشناسی"}], ensure_ascii=False),
        "Jobpost_RequiredExperienceYears": str(experience),
        "Jobpost_IsRemote": str(remote),
        "Jobpost_ProvinceFa": "تهران",
        "Jobpost_ActivationTime_YEAR_MONTH": month,
    }


def dataset_rows():
    rows = []
    for i in range(30):
        rows.append(row("حسابدار", ACCOUNTING, sw(("اکسل", "Excel"), ("سپیدار", "Sepidar")), experience=i % 3))
        rows.append(row("کارشناس مالیات و دارایی", ACCOUNTING, sw(("اکسل", "Excel")), experience=4))
        rows.append(row("برنامه نویس بک اند", SOFTWARE, sw(("پایتون", "Python"), ("جنگو", "Django")), experience=3))
        rows.append(row("برنامه نویس فرانت اند", SOFTWARE, sw(("ری اکت", "React"), ("جاوا اسکریپت", "JavaScript"))))
    rows += [row("نیروی خدماتی", LABOUR) for _ in range(5)]
    return rows


@pytest.fixture
def records():
    return [to_record(r) for r in dataset_rows()]


@pytest.fixture
def built(records, embedder):
    return build_groups(records, embedder, log=lambda *_: None)


@pytest.fixture
def job_groups(built, synonyms):
    groups, centroids, titles = built
    return JobGroups.create(
        qdrant_client.QdrantClient(":memory:"), groups, centroids, titles, {"model": "fake"}, synonym_groups=synonyms
    )


def by_category(groups, category):
    return [g for g in groups if g["category"] == category]


def test_parse_software_keeps_persian_variants_as_aliases():
    skills = parse_software('[{"TitleFa":"فتوشاپ,فوتوشاپ","TitleEn":"Adobe Photoshop","Level":"پیشرفته"}]')
    assert skills == [{"name": "Adobe Photoshop", "aliases": ["Adobe Photoshop", "فتوشاپ", "فوتوشاپ"], "level": "پیشرفته"}]
    assert parse_software("") == [] and parse_software("not json") == []


def test_sensitive_columns_are_never_read(tmp_path):
    pa, pq = pytest.importorskip("pyarrow"), pytest.importorskip("pyarrow.parquet")
    rows = dataset_rows()[:4]
    for r in rows:
        r.update({"Jobpost_PreferredGender": "ترجیحاً آقا", "Jobpost_RequiredMinAge": "25"})
    path = tmp_path / "jv.parquet"
    pq.write_table(pa.Table.from_pylist(rows), path)
    records = read_dataset(path)
    assert len(records) == 4
    assert not set(EXCLUDED_COLUMNS) & set(DATASET_COLUMNS)
    assert all("gender" not in r and "age" not in r for r in records)


def test_sample_is_capped_per_category_and_newest_first(records):
    records[0]["month"] = "2024-03"
    sample = sample_records(records, per_category=10, since_month="2023-04")
    accounting = [r for r in sample if r["category"] == ACCOUNTING]
    assert len(accounting) == 10 and accounting[0]["month"] == "2024-03"
    assert sample_records(records, 10, since_month="2025-01") == []


def test_kmeans_splits_categories_into_coherent_groups(built):
    groups, centroids, titles = built
    assert len(groups) == len(centroids)
    accounting = by_category(groups, ACCOUNTING)
    assert sorted(g["name"] for g in accounting) == ["حسابدار", "کارشناس مالیات و دارایی"]
    assert {g["name"] for g in by_category(groups, SOFTWARE)} == {"برنامه نویس بک اند", "برنامه نویس فرانت اند"}
    labour = by_category(groups, LABOUR)
    assert len(labour) == 1 and labour[0]["skills_sparse"] and labour[0]["key_skills"] == []
    accountant = next(g for g in accounting if g["name"] == "حسابدار")
    assert [s["name"] for s in accountant["key_skills"]] == ["Excel", "Sepidar"]
    assert accountant["key_skills"][0]["share"] == 1.0 and accountant["experience"]["junior"] == 1.0
    assert titles["حسابدار"] == accountant["id"]


def test_clustering_is_deterministic(records, embedder):
    first, _, _ = build_groups(records, embedder, log=lambda *_: None)
    second, _, _ = build_groups(records, embedder, log=lambda *_: None)
    assert [(g["id"], g["name"], g["size"]) for g in first] == [(g["id"], g["name"], g["size"]) for g in second]


def test_place_puts_an_accountant_in_the_accounting_group(job_groups, embedder):
    query = "دنبال کار حسابداری هستم، با اکسل و سپیدار کار کرده‌ام"
    placed = job_groups.place(embedder.embed_query(query), query, top_k=3)
    top = placed[0]
    assert top["group"]["name"] == "حسابدار"
    assert top["matched_skills"] == ["Excel", "Sepidar"] and top["missing_skills"] == []
    assert [p["fit"] for p in placed] == sorted((p["fit"] for p in placed), reverse=True)


def test_skill_score_prefers_the_group_that_needs_all_mentioned_skills(job_groups, embedder):
    # Both accounting groups ask for Excel; only «حسابدار» also asks for Sepidar.
    query = "اکسل و سپیدار"
    placed = {p["group"]["name"]: p for p in job_groups.place(embedder.embed_query(query), query, top_k=5)}
    assert placed["حسابدار"]["skill"] == 1.0
    assert placed["کارشناس مالیات و دارایی"]["skill"] < placed["حسابدار"]["skill"]


def test_gender_markers_are_removed_from_group_names_and_titles(embedder):
    from agent.job_search.job_groups import clean_title

    assert clean_title("حسابدار - خانم") == "حسابدار" and clean_title("منشی (خانم)") == "منشی"
    assert clean_title("مدیر بازاریابی") == "مدیر بازاریابی"
    rows = [to_record(row("راننده - آقا", "راننده")) for _ in range(5)]
    groups, _, titles = build_groups(rows, embedder, log=lambda *_: None)
    assert groups[0]["name"] == "راننده" and "راننده" in titles and groups[0]["search_keywords"] == ["راننده"]


def test_generic_skills_weigh_less_than_specific_ones(built):
    groups, _, _ = built
    idf = {s["name"]: s["idf"] for g in groups for s in g["key_skills"]}
    assert idf["Excel"] < idf["Sepidar"]  # Excel is a key skill of two groups, Sepidar of one


def test_longest_title_match_wins(job_groups):
    # «برنامه نویس بک اند» must not also pull in groups that only match a shorter title.
    assert job_groups._title_hits("برنامه نویس بک اند با پایتون") == {job_groups.titles["برنامه نویس بک اند"]}


def test_title_match_brings_its_group_into_the_results(job_groups, embedder):
    query = "برنامه نویس فرانت اند"
    placed = job_groups.place(embedder.embed_query(query), query, top_k=1)
    assert placed[0]["group"]["name"] == "برنامه نویس فرانت اند" and placed[0]["title"] == 1.0


def test_groups_reload_from_qdrant_and_local_files(built, tmp_path, embedder):
    groups, centroids, titles = built
    client = qdrant_client.QdrantClient(":memory:")
    JobGroups.create(client, groups, centroids, titles, {"model": "fake"}).save_local(tmp_path)
    loaded = JobGroups.load(client, tmp_path)
    assert loaded.meta["groups"] == len(groups) and loaded.titles == titles
    assert loaded.get(groups[0]["id"])["name"] == groups[0]["name"] and loaded.get("nope") is None


@pytest.fixture
def grouped_service(jobs, embedder, synonyms, job_groups):
    from datetime import datetime, timezone

    from agent.job_search.index import JobIndex

    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    return JobSearchService(
        JobIndex.build(jobs, embedder), embedder, synonyms, min_relative_score=0.0, now=lambda: now, job_groups=job_groups
    )


def test_search_returns_only_current_ads_with_their_closest_group(grouped_service):
    result = grouped_service.search("حسابدار با اکسل و سپیدار", top_k=6)
    assert result["groups"][0]["group"]["category"] == ACCOUNTING
    assert "centroid" not in result["groups"][0]
    indexed = set(grouped_service.index.id_to_pos)
    assert result["results"] and all(r["job"]["id"] in indexed for r in result["results"])
    assert all("group" in r and "group" in r["score_breakdown"] for r in result["results"])
    assert result["results"][0]["job"]["id"] in {"103", "106"}  # the accounting ads


def test_search_without_groups_is_unchanged(service):
    result = service.search("حسابدار", top_k=3)
    assert result["groups"] == [] and "group" not in result["results"][0]["score_breakdown"]


class FakeLiveCrawler:
    max_keywords = 4

    def __init__(self):
        self.keywords = None

    def on_enriched(self, _):
        pass

    def fetch(self, keywords, known_ids, variants=None):
        self.keywords = list(keywords)
        return []


def test_live_crawl_adds_typical_titles_of_the_top_group(grouped_service):
    crawler = FakeLiveCrawler()
    grouped_service.live_crawler = crawler
    grouped_service.search("یه کار با اکسل و سپیدار می‌خوام", live=True)
    assert "حسابدار" in crawler.keywords


def test_groups_api(grouped_service, monkeypatch):
    from fastapi.testclient import TestClient

    from ui.src import api

    monkeypatch.setattr(api, "load_api_config", lambda: {"chat_enabled": False})
    monkeypatch.setattr(api, "job_search", grouped_service)
    with TestClient(api.app) as c:
        r = c.post("/jobs/groups", json={"text": "حسابدار با اکسل و سپیدار", "top_k": 2})
        assert r.status_code == 200
        groups = r.json()["groups"]
        assert len(groups) == 2 and groups[0]["group"]["category"] == ACCOUNTING
        gid = groups[0]["group"]["id"]
        assert c.get(f"/jobs/groups/{gid}").json()["id"] == gid
        assert c.get("/jobs/groups/99-9").status_code == 404
        assert c.post("/jobs/groups", json={"text": ""}).status_code == 422


def test_groups_api_503_without_groups(service, monkeypatch):
    from fastapi.testclient import TestClient

    from ui.src import api

    monkeypatch.setattr(api, "load_api_config", lambda: {"chat_enabled": False})
    monkeypatch.setattr(api, "job_search", service)
    with TestClient(api.app) as c:
        assert c.post("/jobs/groups", json={"text": "حسابدار"}).status_code == 503


def test_ambiguous_titles_are_left_out_of_the_title_index(embedder):
    # «کارشناس» appears in two groups equally: it must not point at either.
    rows = [to_record(row("کارشناس", ACCOUNTING, sw(("اکسل", "Excel")))) for _ in range(25)]
    rows += [to_record(row("کارشناس", SOFTWARE, sw(("پایتون", "Python")))) for _ in range(25)]
    rows += [to_record(row("حسابدار", ACCOUNTING, sw(("اکسل", "Excel")))) for _ in range(25)]
    _, _, titles = build_groups(rows, embedder, log=lambda *_: None)
    assert "کارشناس" not in titles and "حسابدار" in titles


def test_title_lookup_uses_bilingual_synonyms(synonyms):
    titles = {"برنامه نویس": "01-0", "برنامه نویس back-end": "01-1"}
    jg = JobGroups(None, titles, {}, synonym_groups=synonyms)
    # «بک اند» is a synonym of «back-end»: the specific title wins over the generic one.
    assert jg._title_hits("برنامه نویس بک اند با پایتون") == {"01-1"}


# ---------- optional feature: disabled by default ----------

def test_job_groups_are_disabled_by_default(embedder):
    from agent.job_search.service import create_job_groups, load_config

    config = load_config()
    assert config["job_groups"]["enabled"] is False
    assert create_job_groups(config, embedder) is None  # disabled: Qdrant is not even contacted


def test_enabled_but_not_built_falls_back_to_no_groups(embedder, tmp_path, monkeypatch):
    from agent.job_search.service import create_job_groups, load_config

    monkeypatch.delenv("QDRANT_URL", raising=False)
    config = load_config()
    config["job_groups"] = {**config["job_groups"], "enabled": True, "dir": str(tmp_path), "qdrant_url": ""}
    assert create_job_groups(config, embedder) is None  # search keeps working without groups


def test_lexical_search_without_groups_never_embeds_the_query(service, monkeypatch):
    def boom(_):
        raise AssertionError("the query was embedded")

    monkeypatch.setattr(service.embedder, "embed_query", boom)
    for method in ("bm25", "keyword"):
        assert "results" in service.search("حسابدار", method=method, top_k=3)
