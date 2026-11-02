"""Load crawled Divar listings and filter/sort them deterministically (no LLM)."""
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agent.home_search.divar_crawler import DEFAULT_OUT
from agent.utilities.persian_text import normalize_for_search, tokenize


@dataclass
class HomeFilters:
    city: Optional[str] = None
    q: Optional[str] = None
    min_price: Optional[int] = None  # toman
    max_price: Optional[int] = None
    min_area: Optional[int] = None
    max_area: Optional[int] = None
    rooms: Optional[int] = None


SORTS = ("newest", "price_asc", "price_desc", "price_per_m2")


def load_listings(path: Path = DEFAULT_OUT) -> list[dict]:
    if not Path(path).exists():
        return []
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                # One malformed scraped row must not take down the entire search API.
                continue
            if not isinstance(r, dict) or not r.get("id") or not r.get("title"):
                continue
            r.setdefault("city", "نامشخص")
            r.setdefault("district", "")
            r.setdefault("url", "")
            p, a = r.get("price_toman"), r.get("area_m2")
            r["price_per_m2"] = int(p / a) if p and a else None
            rows.append(r)
    return rows


def _matches(r: dict, f: HomeFilters, terms: list[str]) -> bool:
    p, a = r.get("price_toman"), r.get("area_m2")
    if f.city and r.get("city") != f.city:
        return False
    if f.min_price and (p is None or p < f.min_price):
        return False
    if f.max_price and (p is None or p > f.max_price):
        return False
    if f.min_area and (a is None or a < f.min_area):
        return False
    if f.max_area and (a is None or a > f.max_area):
        return False
    if f.rooms and r.get("rooms") != f.rooms:
        return False
    if terms:
        text = normalize_for_search(" ".join([r.get("title", ""), r.get("district", ""), r.get("subtitle", "")]))
        return all(f" {t} " in f" {text} " for t in terms)
    return True


def search_listings(rows: list[dict], f: HomeFilters, sort: str = "newest", limit: int = 60, offset: int = 0) -> dict:
    terms = tokenize(f.q or "")
    hits = [r for r in rows if _matches(r, f, terms)]
    missing = float("inf")
    if sort == "newest":
        def date_key(r):
            value = r.get("posted_at") or r.get("updated_at") or r.get("crawled_at") or ""
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp()
            except (TypeError, ValueError):
                return float("-inf")
        hits.sort(key=date_key, reverse=True)
    elif sort == "price_asc":
        hits.sort(key=lambda r: r.get("price_toman") or missing)
    elif sort == "price_desc":
        hits.sort(key=lambda r: -(r.get("price_toman") or 0))
    elif sort == "price_per_m2":
        hits.sort(key=lambda r: r.get("price_per_m2") or missing)
    priced = [r["price_per_m2"] for r in hits if r.get("price_per_m2")]
    return {
        "total": len(hits),
        "results": hits[offset : offset + limit],
        "limit": limit,
        "offset": offset,
        "next_offset": offset + limit if offset + limit < len(hits) else None,
        "median_price_per_m2": sorted(priced)[len(priced) // 2] if priced else None,
    }


def city_options(rows: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for r in rows:
        city = r.get("city") or "نامشخص"
        counts[city] = counts.get(city, 0) + 1
    return [{"city": c, "count": n} for c, n in sorted(counts.items(), key=lambda x: -x[1])]
