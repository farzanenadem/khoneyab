import json
from datetime import datetime, timezone

from agent.job_search.crawler import RobotsRules
from agent.job_search.live import LiveCrawler
from agent.job_search.sources import IranTalentClient, JobinjaClient

TODAY = datetime(2026, 10, 29, tzinfo=timezone.utc)

JOBINJA_LIST = """
<li class="o-listView__item o-listView__item--hasIndicator c-jobListView__item">
  <h2 class="o-listView__itemTitle c-jobListView__title">
    <a class="c-jobListView__titleLink" target="_blank" href="https://jobinja.ir/companies/faraz-17/jobs/tMEn/%D8%A7%D8%B3%D8%AA%D8%AE%D8%AF%D8%A7%D9%85-frontend?_ref=16&amp;_t=x">
        Frontend Engineer (React.js-Next.js)
    </a>
    <span class="c-jobListView__passedDays">(۲ روز پیش)</span>
  </h2>
  <ul class="o-listView__itemComplementInfo c-jobListView__meta">
    <li class="c-jobListView__metaItem"><i></i><span>فراز | Faraz</span></li>
    <li class="c-jobListView__metaItem"><i></i><span> تهران، تهران </span></li>
    <li class="c-jobListView__metaItem"><i></i><span><span>قرارداد تمام&zwnj;وقت</span><a href="#">(برای مشاهده حقوق وارد شوید)</a></span></li>
  </ul>
</li>
"""

JOBINJA_JOB = '<script type="application/ld+json">' + json.dumps({
    "@type": "JobPosting", "datePosted": "2026-10-27", "validThrough": "2026-11-26",
    "description": "<div>Employment Type: remote</div><ul><li>React.js and Next.js</li></ul>",
}) + "</script>"


def irantalent_page(items):
    state = {"serverSideSearchResult": {"data": {"data": items}}}
    return f'<script id="ng-state" type="application/json">{json.dumps(state)}</script>'


IT_ITEM = {
    "id": 186062, "title": "python developer", "title_farsi": "برنامه نویس پایتون", "slug": "python-developer",
    "role_description_farsi": "توسعه API با Python و Django<br>کار با PostgreSQL",
    "location": {"title_farsi": "تهران"}, "location_text_farsi": "تهران",
    "employer": {"name_farsi": "شرکت نمونه"}, "is_show_salary": True, "salary_from": 40, "salary_to": 60,
    "employment_type": {"title_farsi": "تمام وقت"}, "seniority": [{"title_farsi": "کارشناس"}],
    "job_category": [{"title_farsi": "توسعه نرم افزار"}], "work_type": "hybrid",
    "lived_at": "2026-10-28 10:00:00", "expired_at": None,
}


def test_jobinja_list_parsing():
    jobs = JobinjaClient.parse_list(JOBINJA_LIST, today=TODAY)
    assert len(jobs) == 1
    j = jobs[0]
    assert j["id"] == "jobinja-tMEn" and j["source"] == "jobinja.ir"
    assert j["url"].startswith("https://jobinja.ir/companies/faraz-17/jobs/tMEn/") and "?" not in j["url"]
    assert j["title"] == "Frontend Engineer (React.js-Next.js)"
    assert (j["company"], j["province"], j["city"]) == ("فراز", "تهران", "تهران")
    assert j["work_type"] == "تمام وقت"
    assert j["date_posted"].startswith("2026-10-27")
    assert j["salary_text"] == ""  # salary hidden behind login: never guessed


class FakeSession:
    def __init__(self, pages):
        self.pages, self.headers, self.calls = pages, {}, []

    def get(self, url, timeout=None):
        self.calls.append(url)
        body = next((v for k, v in self.pages.items() if k in url), "")
        return type("R", (), {"ok": bool(body), "status_code": 200 if body else 404, "text": body})()


def test_jobinja_enrich_from_json_ld():
    client = JobinjaClient(delay=0, session=FakeSession({"/jobs/tMEn/": JOBINJA_JOB}), robots=RobotsRules(""))
    job = client.enrich(JobinjaClient.parse_list(JOBINJA_LIST, today=TODAY)[0])
    assert job["enriched"] and "React.js and Next.js" in job["description"]
    assert job["expires"] == "2026-11-26" and job["is_remote"] is True


def test_irantalent_page_parsing_and_salary_only_when_shown():
    jobs = IranTalentClient.parse_page(irantalent_page([IT_ITEM, dict(IT_ITEM, id=2, is_show_salary=False)]))
    j = jobs[0]
    assert j["id"] == "irantalent-186062"
    assert j["url"] == "https://www.irantalent.com/job/python-developer/186062"
    assert j["title"] == "برنامه نویس پایتون" and j["company"] == "شرکت نمونه"
    assert "Django" in j["description"] and j["enriched"]
    assert j["salary_text"] == "40 تا 60 میلیون تومان" and j["is_remote"] is True
    assert jobs[1]["salary_text"] == "" and jobs[1]["salary_max"] is None


def test_irantalent_maps_keywords_to_allowed_category_pages(tmp_path):
    robots = RobotsRules("User-agent: *\nDisallow: *?*\nDisallow: /jobs-search*\n")
    client = IranTalentClient(delay=0, robots=robots, session=FakeSession({}))
    client._slugs = ["python-developer", "senior-python-developer", "react-developer", "accountant"]
    assert client.slugs_for(["پایتون", "python"]) == ["python-developer", "senior-python-developer"]
    assert client.slugs_for(["حسابداری"]) == []
    assert not robots.can_fetch("https://www.irantalent.com/jobs-search?keyword=python")
    assert robots.can_fetch("https://www.irantalent.com/jobs/python-developer")


def test_live_crawl_queries_all_boards_in_parallel(tmp_path):
    jobinja = JobinjaClient(delay=0, robots=RobotsRules(""), session=FakeSession({"jobinja.ir/jobs?": JOBINJA_LIST}))
    irantalent = IranTalentClient(delay=0, robots=RobotsRules(""), session=FakeSession({"/jobs/python-developer": irantalent_page([IT_ITEM])}))
    irantalent._slugs = ["python-developer"]
    crawler = LiveCrawler(None, tmp_path / "jobs.jsonl", jobinja=jobinja, irantalent=irantalent)
    crawler._queue.put = lambda item: None  # no background enrichment in the test
    jobs = crawler.fetch(["پایتون"], known_ids=set(), variants={"پایتون": ["پایتون", "python", "django"]})
    assert {j["source"] for j in jobs} == {"jobinja.ir", "irantalent.com"}
    saved = (tmp_path / "other_sources.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(saved) == 2
    assert crawler.fetch(["پایتون"], known_ids={j["id"] for j in jobs}, variants={"پایتون": ["python"]}) == []
