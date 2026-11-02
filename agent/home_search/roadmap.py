"""Pre-purchase roadmap: the inquiries (استعلام‌ها) a buyer should complete before paying.

Content comes from `due_diligence.yaml` (generated from iran_property_due_diligence.md):
36 inquiries, each placed on the deal timeline (phase), given a practical risk level and,
when it only applies to some deals, a condition (inherited, power of attorney, mortgage, ...).
The UI asks which conditions fit the user's deal and tracks completion.
"""
from functools import lru_cache
from pathlib import Path

import yaml

DATA = Path(__file__).with_name("due_diligence.yaml")

PHASES = [
    ("finance", "بودجه و تأمین مالی", "پیش از جستجوی جدی"),
    ("negotiation", "پیش از مذاکره یا بیعانه", "بازدید، هویت، اصل سند، پلاک و نشانه‌های خطر"),
    ("agreement", "پیش از توافق مقدماتی", "مسیر ثبت، وکالت/ارث/شرکت، اجاره، تخلف و شروط"),
    ("payment", "پیش از پرداخت عمده", "پاسخ تازه ثبت، نامه بانک، مدارک شهرداری و نظر کارشناس"),
    ("notary", "پیش از دفترخانه", "کنترل دوباره بازداشت، رهن، سمت، بدهی‌ها و مالیات"),
    ("handover", "روز سند و تحویل", "مقابله متن سند، پرداخت نهایی قابل ردیابی و تحویل"),
]

LEVELS = {
    "critical": "بحرانی",
    "high": "زیاد",
    "medium": "متوسط",
    "low": "کم",
}

# Section 6 special cases → questions the user answers about their deal.
CONDITIONS = [
    ("apartment", "ملک آپارتمان است", True),
    ("mortgage", "ملک در رهن بانک است", False),
    ("poa", "فروشنده با وکالت‌نامه می‌فروشد", False),
    ("inherit", "ملک ارثی است", False),
    ("multi_owner", "ملک چند مالک دارد (مشاع)", False),
    ("tenant", "ملک مستأجر دارد", False),
    ("old_deed", "سند دفترچه‌ای، قولنامه‌ای یا ثبت ناقص است", False),
    ("under_construction", "ساختمان در حال ساخت/مشارکت در ساخت است", False),
    ("presale", "پیش‌فروش است", False),
    ("company", "فروشنده شرکت یا تعاونی است", False),
    ("guardian", "فروشنده صغیر یا محجور است (ولی/قیم)", False),
    ("waqf", "ملک وقفی است", False),
    ("land", "ویلا، زمین یا ملک روستایی/خارج شهر است", False),
]

FINANCE_STEPS = [
    {
        "id": "budget-plan", "n": None, "title": "تعیین بودجه کل و سهم وام", "phase": "finance",
        "level": "medium", "condition": None,
        "goal": "دانستن سقف خرید و قسط ماهانه قبل از بازدید",
        "detail": "با پس‌انداز، درآمد و وام‌های مسکن حساب کنید تا چه قیمتی می‌توانید بخرید. هزینه‌های جانبی (کمیسیون، مالیات و هزینه دفترخانه، اوراق تسه) را هم در نظر بگیرید.",
        "authority": "بخش «وام‌های مسکن» همین دستیار", "docs": "درآمد ماهانه، مبلغ پس‌انداز",
        "when": "پیش از جستجوی جدی", "required": "توصیه‌ای", "risk": "تعهد به خریدی که تأمین مالی ندارد",
        "notes": "", "sources": [],
    },
    {
        "id": "loan-preapproval", "n": None, "title": "استعلام شرایط روز وام از بانک", "phase": "finance",
        "level": "high", "condition": None,
        "goal": "اطمینان از سقف، نرخ و زمان پرداخت وام",
        "detail": "سقف و نرخ وام‌ها مرتب تغییر می‌کند و ممکن است ماه‌ها نوبت انتظار داشته باشد؛ پیش از قول‌وقرار با فروشنده، شرایط و زمان پرداخت را کتبی از شعبه بپرسید و زمان‌بندی پرداخت‌های قرارداد را با آن هماهنگ کنید.",
        "authority": "شعبه بانک", "docs": "کارت ملی، گواهی کسر از حقوق یا ضامن",
        "when": "پیش از بیعانه", "required": "مشروط به استفاده از وام", "risk": "نرسیدن وام در موعد پرداخت و فسخ/خسارت",
        "notes": "", "sources": [],
    },
]


@lru_cache(maxsize=1)
def _load() -> dict:
    return yaml.safe_load(DATA.read_text(encoding="utf-8"))


def purchase_roadmap() -> dict:
    data = _load()
    steps = FINANCE_STEPS + data["steps"]
    phases = [
        {"id": pid, "title": title, "subtitle": sub, "steps": [s for s in steps if s["phase"] == pid]}
        for pid, title, sub in PHASES
    ]
    return {
        "phases": phases,
        "total_steps": len(steps),
        "levels": LEVELS,
        "conditions": [{"id": c, "label": label, "default": d} for c, label, d in CONDITIONS],
        "summary": data["summary"],
        "repeat_note": data["repeat_note"],
        "misconceptions": data["misconceptions"],
        "special_cases": data["special_cases"],
        "open_questions": data["open_questions"],
        "source": data["source"],
        "disclaimer": "این فهرست راهنمای عمومی است و جایگزین مشاوره حقوقی نیست؛ پاسخ هر استعلام تاریخ‌دار است و "
                      "ممکن است تا روز سند تغییر کند. سطح‌های ریسک طبقه‌بندی عملی‌اند، نه طبقه‌بندی رسمی.",
    }
