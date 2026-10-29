import json

from agent.job_search.jobvision_crawler import JobVisionListClient
from agent.job_search.live import LiveCrawler

from .fixtures import make_raw


class FakeClient:
    def __init__(self, raws, fail=False):
        self.raws, self.fail, self.calls = raws, fail, []

    def search(self, keywords, pages=1):
        self.calls.append(list(keywords))
        if self.fail:
            raise RuntimeError("site down")
        return self.raws


def test_live_crawl_adds_new_ads_for_user_keywords(service, tmp_path):
    fresh = make_raw(900, "مهندس یادگیری ماشین (LLM)", categories=("علوم داده / هوش مصنوعی",))
    already = make_raw(101, "کارشناس هوش مصنوعی")
    client = FakeClient([fresh, already])
    service.live_crawler = LiveCrawler(client, tmp_path / "live.jsonl", max_keywords=3)

    res = service.search("کارشناس هوش مصنوعی با Python و LLM", live=True)

    assert res["live"]["new_jobs"] == 1
    assert len(client.calls[0]) <= 3 and "هوش مصنوعی" in client.calls[0]
    assert "900" in [r["job"]["id"] for r in res["results"]]
    assert service.get_job("900")["url"] == "https://jobvision.ir/jobs/900"
    saved = [json.loads(l) for l in (tmp_path / "live.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["id"] for r in saved] == [900]  # already indexed ads are not stored again


def test_live_crawl_failure_does_not_break_search(service, tmp_path):
    service.live_crawler = LiveCrawler(FakeClient([], fail=True), tmp_path / "live.jsonl")
    res = service.search("حسابدار", live=True)
    assert res["live"]["new_jobs"] == 0
    assert res["results"]


def test_search_without_live_flag_does_not_crawl(service, tmp_path):
    client = FakeClient([])
    service.live_crawler = LiveCrawler(client, tmp_path / "live.jsonl")
    service.search("حسابدار")
    assert client.calls == []


def test_enriched_ads_replace_bare_ones(service):
    job = dict(service.get_job("101"), description="توسعه مدل‌های RAG با Python", enriched=True)
    service.update_job(job)
    res = service.search("RAG", top_k=1)
    assert res["results"][0]["job"]["id"] == "101"
    assert res["results"][0]["explanation"]["matched"][0]["field"] == "description"


class FakeResponse:
    def __init__(self, posts):
        self.posts = posts

    def raise_for_status(self):
        pass

    def json(self):
        return {"data": {"jobPostCount": len(self.posts), "jobPosts": self.posts}}


class FakeSession:
    def __init__(self):
        self.headers, self.bodies = {}, []

    def post(self, url, json=None, timeout=None):
        self.bodies.append(json)
        return FakeResponse([{"id": hash(json["keyWord"]) % 1000, "title": json["keyWord"]}, {"id": 1, "title": "shared"}])


def test_list_client_searches_keywords_in_parallel_and_dedupes():
    session = FakeSession()
    client = JobVisionListClient(delay=0, session=session)
    posts = client.search(["python", "هوش مصنوعی", "python"], pages=1)
    assert sorted(b["keyWord"] for b in session.bodies) == sorted(["python", "هوش مصنوعی"])
    assert len([p for p in posts if p["id"] == 1]) == 1
    assert "RahnamaHackathonJobSearchBot" in session.headers["User-Agent"]
