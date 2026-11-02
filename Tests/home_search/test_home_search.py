from agent.home_search.divar_crawler import DivarListClient, parse_row, parse_toman
from agent.home_search.listings import HomeFilters, search_listings
from agent.home_search.loans import LoanOverride, PlanRequest, build_plan, monthly_installment
from agent.home_search.roadmap import purchase_roadmap


def _widget(token, title, price, district="ونک"):
    return {
        "widget_type": "POST_ROW",
        "data": {
            "title": title,
            "middle_description_text": price,
            "token": token,
            "action": {"payload": {"web_info": {"district_persian": district, "city_persian": "تهران"}}},
        },
    }


def test_parse_toman():
    assert parse_toman("۴,۶۸۰,۰۰۰,۰۰۰ تومان") == 4_680_000_000
    assert parse_toman("۲.۵ میلیارد") == 2_500_000_000
    assert parse_toman("توافقی") is None


def test_parse_row_extracts_area_rooms():
    row = parse_row(_widget("abc", "۸۵ متر دوخوابه نوساز", "۸,۰۰۰,۰۰۰,۰۰۰ تومان"), "تهران", "apartment-sell", "t")
    assert row["area_m2"] == 85 and row["rooms"] == 2 and row["price_toman"] == 8_000_000_000
    assert row["url"] == "https://divar.ir/v/abc"
    assert parse_row({"widget_type": "TITLE_ROW", "data": {}}, "تهران", "x", "t") is None


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class FakeSession:
    def __init__(self, pages):
        self.pages, self.headers, self.bodies = pages, {}, []

    def post(self, url, json, timeout):
        self.bodies.append(json)
        return FakeResponse(self.pages[len(self.bodies) - 1])


def test_crawl_paginates_and_dedupes():
    pages = [
        {"list_widgets": [_widget("a", "۶۰ متری", "۱ میلیارد")], "pagination": {"has_next_page": True, "data": {"page": 1}}},
        {"list_widgets": [_widget("a", "۶۰ متری", "۱ میلیارد"), _widget("b", "۹۰ متری", "۲ میلیارد")],
         "pagination": {"has_next_page": False}},
    ]
    session = FakeSession(pages)
    rows = DivarListClient(delay=0, session=session).crawl("tehran", pages=5)
    assert [r["id"] for r in rows] == ["a", "b"]
    assert session.bodies[1]["pagination_data"] == {"page": 1}


def test_search_filters_and_sort():
    rows = [
        {"id": "1", "title": "آپارتمان نوساز", "city": "تهران", "district": "ونک", "price_toman": 9_000, "area_m2": 90, "price_per_m2": 100},
        {"id": "2", "title": "آپارتمان", "city": "تهران", "district": "پونک", "price_toman": 5_000, "area_m2": 50, "price_per_m2": 100},
        {"id": "3", "title": "ویلا", "city": "کرج", "district": "", "price_toman": 1_000, "area_m2": None, "price_per_m2": None},
    ]
    out = search_listings(rows, HomeFilters(city="تهران"), sort="price_asc")
    assert [r["id"] for r in out["results"]] == ["2", "1"]
    assert search_listings(rows, HomeFilters(q="ونک"))["total"] == 1
    assert search_listings(rows, HomeFilters(min_area=60))["total"] == 1


def test_installment_math():
    assert monthly_installment(120, 0, 1) == 10
    # 100M at 18% over 12 years ≈ 1.70M/month
    assert 1_690_000 < monthly_installment(100_000_000, 18, 12) < 1_710_000


def test_plan_eligibility_and_gap():
    plan = build_plan(PlanRequest(
        price=10_000_000_000, savings=6_000_000_000, monthly_income=100_000_000, first_home=False,
        loans=[LoanOverride(id="maskan-yekom"), LoanOverride(id="taseh", amount=1_000_000_000)],
    ))
    by_id = {l["id"]: l for l in plan["loans"]}
    assert not by_id["maskan-yekom"]["selected"] and by_id["maskan-yekom"]["issues"]
    assert by_id["taseh"]["selected"] and plan["total_loan"] == 1_000_000_000
    assert plan["bond_cost"] == 250_000_000
    assert plan["gap"] == 10_000_000_000 - 1_000_000_000 - (6_000_000_000 - 250_000_000)
    assert plan["debt_to_income_pct"] is not None


def test_roadmap_has_unique_steps():
    r = purchase_roadmap()
    ids = [s["id"] for p in r["phases"] for s in p["steps"]]
    assert len(ids) == len(set(ids)) == r["total_steps"] == 38  # 2 finance + 36 inquiries
    conditions = {c["id"] for c in r["conditions"]}
    for p in r["phases"]:
        for s in p["steps"]:
            assert s["level"] in r["levels"]
            assert s["condition"] is None or s["condition"] in conditions
            assert all(src["url"].startswith("https://") for src in s["sources"])


from agent.home_search.assistant import converse, parse_request

ROWS = [
    {"id": "1", "title": "۸۰ متری دوخواب پارکینگ نوساز", "city": "تهران", "district": "ونک", "subtitle": "",
     "price_toman": 7_000_000_000, "area_m2": 80, "rooms": 2, "price_per_m2": 87_500_000},
    {"id": "2", "title": "۸۵ متر دو خواب", "city": "تهران", "district": "پونک", "subtitle": "",
     "price_toman": 6_000_000_000, "area_m2": 85, "rooms": 2, "price_per_m2": 70_000_000},
    {"id": "3", "title": "۱۲۰ متری", "city": "کرج", "district": "گوهردشت", "subtitle": "",
     "price_toman": 4_000_000_000, "area_m2": 120, "rooms": 3, "price_per_m2": 33_000_000},
]


def test_parse_descriptive_request():
    p = parse_request("یه آپارتمان دو خواب حدود ۸۰ متر در تهران تا ۸ میلیارد با پارکینگ", ["تهران", "کرج"], ["ونک"])
    f = p.filters
    assert f.city == "تهران" and f.rooms == 2 and f.max_price == 8_000_000_000
    assert f.min_area <= 80 <= f.max_area and "پارکینگ" in p.features


def test_parse_price_range_respects_each_unit():
    p = parse_request("از ۲ میلیارد تا ۵۰۰ میلیون", ["تهران"], [])
    assert p.filters.min_price == 2_000_000_000
    assert p.filters.max_price == 500_000_000


def test_converse_ranks_features_and_keeps_context():
    out = converse(ROWS, "دو خواب در تهران تا ۸ میلیارد با پارکینگ")
    assert [r["id"] for r in out["results"]] == ["1", "2"] and out["reply"]
    # Follow-up turn keeps the city and only changes the budget.
    from agent.home_search.listings import HomeFilters
    out2 = converse(ROWS, "تا ۶ میلیارد چی؟", base=HomeFilters(**out["filters"]))
    assert [r["id"] for r in out2["results"]] == ["2"]


def test_converse_relaxes_when_empty():
    out = converse(ROWS, "۳۰۰ متر در تهران")
    assert out["relaxed"] == ["متراژ"] and out["results"]
