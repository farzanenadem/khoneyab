import json

from agent.job_search.crawler import JobVisionEnricher, RobotsRules, parse_job_page

# Copy of https://jobvision.ir/robots.txt as of 2026-10-29.
JOBVISION_ROBOTS = """user-agent: *
disallow: *?*
disallow: *utm_*
disallow: */Login/*
Allow: *.js
Allow: *.css

Sitemap: https://jobvision.ir/sitemap.xml
"""

DETAIL = {
    "id": 555,
    "title": "Data Scientist",
    "description": "<div><p>وظایف:</p><ul><li>توسعه مدل&zwnj;های LLM</li></ul></div>",
    "skills": [{"titleFa": "یادگیری ماشین"}],
    "softwareRequirements": [{"software": {"titleFa": "Python"}, "skill": {"titleFa": "پیشرفته"}}],
    "languageRequirements": [{"language": {"titleFa": "انگلیسی"}, "skill": {"titleFa": "متوسط"}}],
    "academicRequirements": [{"degreeLevel": {"titleFa": "کارشناسی"}, "field": {"titleFa": "کامپیوتر"}}],
    "workDays": "شنبه تا چهارشنبه",
    "isRemote": True,
    "shouldDoneMilitaryService": False,
    "requiredAgeMin": 22,
    "requiredAgeMax": 35,
    "company": {"description": {"titleFa": "should not be stored"}},
}


def page(detail=DETAIL, ld=None):
    state = {"https://candidateapi.jobvision.ir/api/v1/JobPost/Detail?jobPostId=555": detail}
    ld_tag = f'<script type="application/ld+json">{json.dumps(ld)}</script>' if ld else ""
    return f'<html><head>{ld_tag}</head><body><script id="ng-state" type="application/json">{json.dumps(state)}</script></body></html>'


def test_robots_rules_follow_wildcards_like_google():
    rules = RobotsRules(JOBVISION_ROBOTS)
    assert rules.can_fetch("https://jobvision.ir/jobs/1566052")
    assert rules.can_fetch("https://jobvision.ir/jobs/1566052/استخدام-دستیار")
    assert not rules.can_fetch("https://jobvision.ir/jobs?page=2")
    assert not rules.can_fetch("https://jobvision.ir/jobs/1/x-utm_source")
    assert not rules.can_fetch("https://jobvision.ir/account/Login/")


def test_parse_job_page_keeps_only_matching_fields():
    rec = parse_job_page(page(), 555, "https://jobvision.ir/jobs/555/slug")
    assert rec["description"].splitlines() == ["وظایف:", "• توسعه مدل‌های LLM"]
    assert rec["skills"] == ["یادگیری ماشین"]
    assert rec["software"] == [{"name": "Python", "level": "پیشرفته"}]
    assert rec["languages"] == [{"name": "انگلیسی", "level": "متوسط"}]
    assert rec["academic"] == ["کارشناسی - کامپیوتر"]
    assert rec["is_remote"] is True
    assert rec["url"] == "https://jobvision.ir/jobs/555/slug"
    assert "company" not in rec


def test_parse_job_page_falls_back_to_json_ld():
    html = f'<script type="application/ld+json">{json.dumps({"@type": "JobPosting", "description": "شرح", "workHours": "8-17"})}</script>'
    rec = parse_job_page(html, 7)
    assert rec["description"] == "شرح" and rec["work_days"] == "8-17"
    assert parse_job_page("<html></html>", 7) is None


class FakeResponse:
    def __init__(self, status, text="", url=""):
        self.status_code, self.text, self.url, self.headers = status, text, url, {}

    @property
    def ok(self):
        return self.status_code < 400


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}

    def get(self, url, timeout=None):
        self.calls.append(url)
        return self.responses.pop(0)


def make_enricher(tmp_path, responses, robots=JOBVISION_ROBOTS):
    sleeps = []
    session = FakeSession(responses)
    enricher = JobVisionEnricher(
        tmp_path, delay=1.0, session=session, sleep=sleeps.append, robots=RobotsRules(robots)
    )
    return enricher, session, sleeps


def test_enricher_fetches_caches_and_identifies_itself(tmp_path):
    enricher, session, _ = make_enricher(tmp_path, [FakeResponse(200, page(), "https://jobvision.ir/jobs/555/slug")])
    assert "RahnamaHackathonJobSearchBot" in session.headers["User-Agent"]

    stats = enricher.enrich_many([555, 555])
    assert (stats.fetched, stats.cached, stats.failed) == (1, 1, 0)
    assert len(session.calls) == 1  # second time served from cache
    assert json.loads((tmp_path / "555.json").read_text(encoding="utf-8"))["software"][0]["name"] == "Python"


def test_enricher_respects_robots_and_retries_on_429(tmp_path):
    enricher, session, _ = make_enricher(tmp_path, [], robots="user-agent: *\ndisallow: /jobs/")
    stats = enricher.enrich_many([1])
    assert stats.disallowed == 1 and session.calls == []

    enricher, session, sleeps = make_enricher(
        tmp_path / "b", [FakeResponse(429), FakeResponse(200, page(), "u")]
    )
    assert enricher.enrich_one(555) is not None
    assert len(session.calls) == 2 and sleeps  # backed off before retrying


def test_enricher_records_failures_without_crashing(tmp_path):
    enricher, _, _ = make_enricher(tmp_path, [FakeResponse(404), FakeResponse(200, "<html/>")])
    stats = enricher.enrich_many([1, 2])
    assert stats.failed == 2 and stats.errors == [(1, 404), (2, "unparseable")]
