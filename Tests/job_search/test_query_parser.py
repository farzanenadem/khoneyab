import pytest

from agent.job_search.query_parser import QueryParser

EXAMPLE = (
    "دنبال یک موقعیت شغلی در حوزه هوش مصنوعی هستم که به Python، مدل‌های زبانی بزرگ و RAG "
    "مرتبط باشد و ترجیحاً در تهران یا به‌صورت دورکاری باشد."
)


@pytest.fixture
def parser(synonyms):
    return QueryParser(["تهران", "کرج", "البرز", "اصفهان", "ری"], synonyms)


def test_example_query_from_requirements(parser):
    pq = parser.parse(EXAMPLE)
    labels = {c.label for c in pq.concepts}
    assert pq.locations == ["تهران"]
    assert pq.wants_remote is True
    assert pq.location_strict is False  # «ترجیحاً» is a preference, not a filter
    assert {"هوش مصنوعی", "python", "rag", "مدل زبانی بزرگ"} <= labels
    # Generic words are not treated as skills.
    assert not labels & {"دنبال", "موقعیت", "شغلی", "مرتبط", "باشد"}


def test_synonyms_expand_across_languages(parser):
    pq = parser.parse("برنامه نویس پایتون")
    python = next(c for c in pq.concepts if "python" in c.variants)
    assert "django" in python.variants
    ai = next(c for c in parser.parse("machine learning engineer").concepts if "هوش مصنوعی" in c.variants)
    assert ai.from_synonyms


def test_numbers_work_type_and_salary_with_persian_digits(parser):
    pq = parser.parse("برنامه نویس ری اکت با ۳ سال سابقه، پاره وقت در کرج، حقوق بالای ۴۰ میلیون")
    assert pq.experience_years == 3
    assert pq.min_salary == 40
    assert pq.work_types == ["پاره وقت"]
    assert pq.locations == ["کرج"]
    labels = {c.label for c in pq.concepts}
    assert "ری اکت" in labels  # not mistaken for the city «ری»
    assert not any("،" in label for label in labels)


def test_seniority_internship_and_no_experience(parser):
    pq = parser.parse("کارآموزی حسابداری بدون سابقه")
    assert pq.wants_internship and "کارآموز" in pq.seniority
    assert pq.experience_years == 0
    senior = parser.parse("مدیر محصول ارشد در اصفهان")
    assert "کارشناس ارشد" in senior.seniority
    assert any(c.label == "مدیر محصول" for c in senior.concepts)
    assert "مدیر میانی" not in senior.seniority  # «مدیر» belonged to «مدیر محصول»


def test_strict_location(parser):
    assert parser.parse("فقط در اصفهان حسابدار").location_strict is True


def test_arabic_letter_variants_are_understood(parser):
    pq = parser.parse("كارشناس هوش مصنوعي در تهران")
    assert pq.locations == ["تهران"]
    assert any(c.label == "هوش مصنوعی" for c in pq.concepts)
