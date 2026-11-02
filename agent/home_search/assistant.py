"""Conversational home search: descriptive Persian request → filters → listings → grounded reply.

Parsing and ranking are deterministic; the LLM (optional) only phrases the reply from the
returned listings and must not invent listings, prices or features.
"""
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Optional

from agent.home_search.listings import HomeFilters
from agent.utilities.persian_text import DIGITS, normalize_for_search

WORD_NUMS = {"یک": 1, "یه": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5, "شش": 6, "هفت": 7, "هشت": 8, "نه": 9,
             "ده": 10, "نیم": 0.5}
UNITS = {"میلیارد": 10**9, "میلیون": 10**6}
FEATURES = ["پارکینگ", "اسانسور", "انباری", "نوساز", "تک برگ", "سند", "بالکن", "استخر", "مبله", "فول",
            "نورگیر", "غرق نور", "شخصی", "ویو", "لابی", "کلید نخورده", "بازسازی", "همکف", "پنت هاوس"]
NUM = r"(?:\d+(?:\.\d+)?|" + "|".join(WORD_NUMS) + r")"
MAX_WORDS = r"(?:تا|زیر|حداکثر|کمتر از|نهایتا|سقف|بودجه(?:م| من)?(?: حدود)?)"
MIN_WORDS = r"(?:بالای|بیشتر از|حداقل|از)"


def _num(s: str) -> float:
    return WORD_NUMS[s] if s in WORD_NUMS else float(s)


@dataclass
class ParsedRequest:
    filters: HomeFilters
    features: list[str] = field(default_factory=list)
    understood: list[str] = field(default_factory=list)


def parse_request(text: str, cities: list[str], districts: list[str], base: Optional[HomeFilters] = None) -> ParsedRequest:
    """Extract filters from a Persian description; values from `base` (earlier turns) are kept unless overridden."""
    t = normalize_for_search(text).translate(DIGITS)
    f = HomeFilters(**asdict(base)) if base else HomeFilters()
    f.q = None
    understood = []

    for c in cities:
        if normalize_for_search(c) in t:
            f.city = c
            understood.append(f"شهر: {c}")
            break

    money = rf"({NUM})\s*(میلیارد|میلیون)"
    if m := re.search(rf"(?:بین|از)\s*({NUM})\s*(میلیارد|میلیون)?\s*تا\s*({NUM})\s*(میلیارد|میلیون)", t):
        min_unit = m.group(2) or m.group(4)
        f.min_price = int(_num(m.group(1)) * UNITS[min_unit])
        f.max_price = int(_num(m.group(3)) * UNITS[m.group(4)])
    else:
        if m := re.search(rf"{MAX_WORDS}\s*{money}", t):
            f.max_price = int(_num(m.group(1)) * UNITS[m.group(2)])
        elif m := re.search(rf"(?:حدود|حدودا|در حد)\s*{money}", t):
            v = _num(m.group(1)) * UNITS[m.group(2)]
            f.min_price, f.max_price = int(v * 0.85), int(v * 1.15)
        if m := re.search(rf"{MIN_WORDS}\s*{money}", t):
            f.min_price = int(_num(m.group(1)) * UNITS[m.group(2)])
    if f.max_price or f.min_price:
        understood.append("بازه قیمت")

    area = r"(\d{2,4})\s*(?:متر|متری|m)"
    if m := re.search(rf"(?:بین|از)\s*(\d{{2,4}})\s*تا\s*{area}", t):
        f.min_area, f.max_area = int(m.group(1)), int(m.group(2))
    elif m := re.search(rf"{MIN_WORDS}\s*{area}", t):
        f.min_area = int(m.group(1))
    elif m := re.search(rf"{MAX_WORDS}\s*{area}", t):
        f.max_area = int(m.group(1))
    elif m := re.search(area, t):
        v = int(m.group(1))
        f.min_area, f.max_area = int(v * 0.85), int(v * 1.15)
    if f.min_area or f.max_area:
        understood.append("متراژ")

    if m := re.search(r"(تک|یک|دو|سه|چهار|[1-4])\s*خواب", t):
        f.rooms = 1 if m.group(1) == "تک" else int(_num(m.group(1)))
        understood.append(f"{str(f.rooms).translate(str.maketrans('01234', '۰۱۲۳۴'))} خواب")

    district = next((d for d in sorted(districts, key=len, reverse=True)
                     if len(d) > 2 and f" {normalize_for_search(d)} " in f" {t} "), None)
    features = [x for x in FEATURES if f" {x} " in f" {t} "]
    if district:
        features.insert(0, normalize_for_search(district))
        understood.append(f"محله: {district}")
    understood += [f"ویژگی: {x}" for x in features if x != normalize_for_search(district or "")]
    return ParsedRequest(f, features, understood)


def _hard_ok(r: dict, f: HomeFilters) -> bool:
    p, a = r.get("price_toman"), r.get("area_m2")
    return not (
        (f.city and r.get("city") != f.city)
        or (f.min_price and (p is None or p < f.min_price))
        or (f.max_price and (p is None or p > f.max_price))
        or (f.min_area and a is not None and a < f.min_area)
        or (f.max_area and a is not None and a > f.max_area)
        or (f.rooms and r.get("rooms") is not None and r["rooms"] != f.rooms)
    )


def rank(rows: list[dict], parsed: ParsedRequest, top_k: int = 8) -> tuple[list[dict], list[str]]:
    """Hard filters (city/price; area and rooms only when known), soft feature matching.
    If nothing matches, area then rooms then price (+20%) are relaxed, and that is reported."""
    f = HomeFilters(**asdict(parsed.filters))
    relaxed: list[str] = []
    steps = [("متراژ", ("min_area", "max_area")), ("تعداد خواب", ("rooms",)), ("سقف قیمت", ("max_price",))]
    while True:
        hits = [r for r in rows if _hard_ok(r, f)]
        if hits or not steps:
            break
        label, attrs = steps.pop(0)
        if not any(getattr(f, a) for a in attrs):
            continue
        for a in attrs:
            setattr(f, a, int(f.max_price * 1.2) if a == "max_price" else None)
        relaxed.append(label)

    def score(r):
        text = normalize_for_search(" ".join([r.get("title", ""), r.get("district", ""), r.get("subtitle", "")]))
        matched = [x for x in parsed.features if f" {x} " in f" {text} "]
        known = sum(r.get(k) is not None for k in ("area_m2", "rooms", "price_toman"))
        return len(matched) * 10 + known, matched

    scored = []
    for r in hits:
        s, matched = score(r)
        scored.append({**r, "matched_features": matched, "_s": s})
    scored.sort(key=lambda r: (-r["_s"], r.get("price_per_m2") or float("inf")))
    return [{k: v for k, v in r.items() if k != "_s"} for r in scored[:top_k]], relaxed


REPLY_PROMPT = """تو دستیار خرید خانه هستی. به زبان فارسی، کوتاه و دوستانه (حداکثر ۶ جمله) به کاربر جواب بده.
فقط از آگهی‌های فهرست زیر استفاده کن؛ آگهی، قیمت، متراژ یا ویژگی‌ای که در فهرست نیست نساز.
۲ یا ۳ گزینه مناسب‌تر را با شماره‌شان نام ببر و دلیلش را از عنوان آگهی بگو.
اگر فیلتری آسان‌تر شده، به کاربر بگو. اگر اطلاعاتی مثل شهر یا بودجه نگفته، یک سؤال کوتاه بپرس.
یادآوری کن قبل از پرداخت، استعلام‌های تب «نقشه راه» را انجام دهد فقط اگر کاربر جدی به خرید نزدیک است.

پیام کاربر: {message}
فیلترهای فهمیده‌شده: {understood}
فیلترهای آسان‌شده: {relaxed}
آگهی‌ها:
{listings}"""


def _fmt_price(p: Optional[int]) -> str:
    if not p:
        return "توافقی"
    return f"{p / 1e9:.2f} میلیارد تومان".replace(".00", "")


def _fallback_reply(results: list[dict], parsed: ParsedRequest, relaxed: list[str]) -> str:
    if not results:
        return "آگهی‌ای با این مشخصات پیدا نکردم. لطفاً بودجه یا شهر را تغییر دهید."
    parts = []
    if parsed.understood:
        parts.append("متوجه شدم: " + "، ".join(parsed.understood) + ".")
    if relaxed:
        parts.append("نتیجه دقیقی نبود، پس " + " و ".join(relaxed) + " را کمی آسان‌تر گرفتم.")
    top = results[0]
    parts.append(f"{len(results)} آگهی پیدا شد؛ مثلاً «{top['title']}» در {top.get('district') or top['city']} با قیمت {_fmt_price(top.get('price_toman'))}.")
    if not parsed.filters.city:
        parts.append("در کدام شهر دنبال خانه هستید؟")
    elif not parsed.filters.max_price:
        parts.append("بودجه‌تان حدوداً چقدر است؟")
    return " ".join(parts)


def chat_reply(message: str, results: list[dict], parsed: ParsedRequest, relaxed: list[str], llm=None) -> str:
    if llm is None or not results:
        return _fallback_reply(results, parsed, relaxed)
    listings = "\n".join(
        f"{i}. {r['title']} | {r['city']}، {r.get('district', '')} | {_fmt_price(r.get('price_toman'))}"
        f" | متراژ: {r.get('area_m2') or 'نامشخص'} | خواب: {r.get('rooms') or 'نامشخص'}"
        for i, r in enumerate(results, 1)
    )
    prompt = REPLY_PROMPT.format(message=message, understood="، ".join(parsed.understood) or "هیچ",
                                 relaxed="، ".join(relaxed) or "هیچ", listings=listings)
    try:
        content = (getattr(llm.invoke(prompt), "content", None) or "").strip()
        return content or _fallback_reply(results, parsed, relaxed)
    except Exception:  # timeouts/gateway errors: deterministic reply
        return _fallback_reply(results, parsed, relaxed)


def converse(rows: list[dict], message: str, base: Optional[HomeFilters] = None, llm=None, top_k: int = 8) -> dict:
    cities = sorted({r["city"] for r in rows})
    districts = sorted({r["district"] for r in rows if r.get("district")})
    parsed = parse_request(message, cities, districts, base)
    results, relaxed = rank(rows, parsed, top_k)
    return {
        "reply": chat_reply(message, results, parsed, relaxed, llm),
        "filters": asdict(parsed.filters),
        "understood": parsed.understood,
        "relaxed": relaxed,
        "results": results,
    }
