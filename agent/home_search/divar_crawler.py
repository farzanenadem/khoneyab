"""
Divar real-estate crawler (uses the site's public JSON post-list API, no HTML parsing).

    python -m agent.home_search.divar_crawler                       # sample: Tehran, 3 pages
    python -m agent.home_search.divar_crawler -c tehran -c karaj -p 2
    python -m agent.home_search.divar_crawler --category apartment-rent

Output: data/homes/divar_listings.jsonl (one normalized listing per line).

api.divar.ir/robots.txt allows everything; we still keep a low rate, an identifying
User-Agent, and store only list fields (title, price, area, district, link, thumbnail).
Contact details are never requested or stored.
"""
import argparse
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

from agent._core.settings import ROOT_DIR
from agent.utilities.persian_text import DIGITS

API = "https://api.divar.ir/v8/postlist/w/search"
POST_URL = "https://divar.ir/v/{token}"
USER_AGENT = "KhoneyabHomeSearchBot/1.0 (educational prototype; low-rate)"
DEFAULT_OUT = ROOT_DIR / "data" / "homes" / "divar_listings.jsonl"

CITIES = {
    "tehran": ("1", "تهران"),
    "karaj": ("2", "کرج"),
    "mashhad": ("3", "مشهد"),
    "isfahan": ("4", "اصفهان"),
    "tabriz": ("5", "تبریز"),
    "shiraz": ("6", "شیراز"),
}
CATEGORIES = {"apartment-sell": "فروش آپارتمان", "house-villa-sell": "فروش خانه و ویلا", "apartment-rent": "اجاره آپارتمان"}

AREA_RE = re.compile(r"(\d{2,4})\s*(?:متر|متري|متری|m)")
ROOMS_RE = re.compile(r"(تک|دو|سه|چهار|[1-4])\s*خواب")
ROOMS = {"تک": 1, "دو": 2, "سه": 3, "چهار": 4}
UNIT = {"میلیارد": 10**9, "میلیون": 10**6, "هزار": 10**3}


def parse_toman(text: str) -> Optional[int]:
    """'۴,۶۸۰,۰۰۰,۰۰۰ تومان' → 4680000000; '۲ میلیارد' → 2e9; 'توافقی' → None."""
    t = (text or "").translate(DIGITS).replace(",", "").replace("٬", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(میلیارد|میلیون|هزار)?", t)
    if not m:
        return None
    value = float(m.group(1)) * UNIT.get(m.group(2) or "", 1)
    return int(value) if value >= 1000 else None


def parse_row(widget: dict, city: str, category: str, crawled_at: str) -> Optional[dict]:
    """Normalize one POST_ROW widget; returns None for non-listing widgets."""
    if widget.get("widget_type") != "POST_ROW":
        return None
    d = widget.get("data") or {}
    payload = (d.get("action") or {}).get("payload") or {}
    token = d.get("token") or payload.get("token")
    if not token:
        return None
    info = payload.get("web_info") or {}
    title = (d.get("title") or info.get("title") or "").strip()
    plain = title.translate(DIGITS)
    area = AREA_RE.search(plain)
    rooms = ROOMS_RE.search(plain)
    price_text = d.get("middle_description_text") or ""
    posted_at = d.get("created_at") or info.get("created_at") or payload.get("created_at")
    return {
        "id": token,
        "source": "divar",
        "url": POST_URL.format(token=token),
        "title": re.sub(r"\s+", " ", title),
        "category": category,
        "city": info.get("city_persian") or city,
        "district": info.get("district_persian") or "",
        "price_text": price_text,
        "price_toman": parse_toman(price_text),
        "area_m2": int(area.group(1)) if area else None,
        "rooms": (ROOMS.get(rooms.group(1)) or int(rooms.group(1))) if rooms else None,
        "subtitle": d.get("bottom_description_text") or "",
        "tag": d.get("red_text") or "",
        "image_url": d.get("image_url") or "",
        "image_count": d.get("image_count") or 0,
        "crawled_at": crawled_at,
        # Divar does not expose this consistently across API versions. Keep it when
        # available so consumers can distinguish publication order from crawl order.
        "posted_at": str(posted_at) if posted_at is not None else None,
    }


class DivarListClient:
    """Rate-limited client for Divar's public post-list API."""

    def __init__(self, delay: float = 1.5, timeout: float = 20.0, retries: int = 3,
                 session: Optional[requests.Session] = None):
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Content-Type": "application/json"})
        self._last = 0.0

    def _throttle(self):
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def list_page(self, city_id: str, category: str, pagination: Optional[dict] = None) -> dict:
        body = {
            "city_ids": [city_id],
            "search_data": {"form_data": {"data": {"category": {"str": {"value": category}}}}},
        }
        if pagination:
            body["pagination_data"] = pagination
        for attempt in range(self.retries):
            self._throttle()
            try:
                r = self.session.post(API, json=body, timeout=self.timeout)
                r.raise_for_status()
                return r.json()
            except (requests.RequestException, ValueError):
                time.sleep(min(2 ** attempt, 4))
        raise RuntimeError(f"divar list failed: city={city_id} category={category}")

    def iter_pages(self, city: str, category: str = "apartment-sell", pages: int = 1):
        """Yield normalized, deduplicated rows page by page for resumable crawls."""
        city_id, city_fa = CITIES[city]
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        seen, pagination = set(), None
        for _ in range(pages):
            data = self.list_page(city_id, category, pagination)
            page_rows = []
            for w in data.get("list_widgets") or []:
                row = parse_row(w, city_fa, category, now)
                if row and row["id"] not in seen:
                    seen.add(row["id"])
                    page_rows.append(row)
            yield page_rows
            page = data.get("pagination") or {}
            if not page.get("has_next_page"):
                break
            pagination = page.get("data")

    def crawl(self, city: str, category: str = "apartment-sell", pages: int = 1) -> list[dict]:
        out = []
        for page_rows in self.iter_pages(city, category, pages):
            out.extend(page_rows)
        return out


def load_existing(path: Path) -> dict[str, dict]:
    """Load valid rows by id so interrupted crawls can resume safely."""
    rows: dict[str, dict] = {}
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("id"):
            rows[str(row["id"])] = row
    return rows


def save_rows(path: Path, rows: dict[str, dict]) -> None:
    """Persist a crawl checkpoint atomically, never exposing a partial JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f"{path.stem}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for row in rows.values():
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    ap = argparse.ArgumentParser(description="Crawl divar.ir real-estate listings")
    ap.add_argument("-c", "--city", action="append", choices=sorted(CITIES), help="city (repeatable)")
    ap.add_argument("--category", action="append", choices=sorted(CATEGORIES), help="category (repeatable)")
    ap.add_argument("-p", "--pages", type=int, default=3, help="maximum pages per city/category (~24 ads each)")
    ap.add_argument("--target", type=int, default=0, help="stop after this many unique listings (0 = use --pages)")
    ap.add_argument("--max-pages-per-source", type=int, default=250, help="safety cap when --target is used")
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between requests")
    ap.add_argument("-o", "--out", default=str(DEFAULT_OUT))
    a = ap.parse_args()

    if a.pages < 1:
        ap.error("--pages must be at least 1")
    if a.delay < 0:
        ap.error("--delay cannot be negative")
    if a.target < 0:
        ap.error("--target cannot be negative")
    if a.max_pages_per_source < 1:
        ap.error("--max-pages-per-source must be at least 1")
    client = DivarListClient(delay=a.delay)
    out = Path(a.out)
    rows_by_id = load_existing(out)
    cities = a.city or ["tehran"]
    categories = a.category or ["apartment-sell"]
    page_limit = a.max_pages_per_source if a.target else a.pages

    for city in cities:
        for category in categories:
            if a.target and len(rows_by_id) >= a.target:
                break
            source_total = 0
            for page_rows in client.iter_pages(city, category, page_limit):
                rows_by_id.update({str(row["id"]): row for row in page_rows})
                source_total += len(page_rows)
                save_rows(out, rows_by_id)
                print(
                    f"{city}/{category}: page +{len(page_rows)}; source={source_total}; total={len(rows_by_id)}",
                    flush=True,
                )
                if a.target and len(rows_by_id) >= a.target:
                    break
        if a.target and len(rows_by_id) >= a.target:
            break

    save_rows(out, rows_by_id)
    print(f"saved {len(rows_by_id)} listings to {out}", flush=True)


if __name__ == "__main__":
    main()
