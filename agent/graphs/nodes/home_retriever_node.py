from langchain_core.documents import Document

from agent.home_search.assistant import parse_request, rank
from agent.home_search.listings import HomeFilters


def _price(p) -> str:
    return f"{p / 1e9:g} میلیارد تومان" if p else "توافقی"


def listing_to_document(i: int, r: dict) -> Document:
    """Render one listing as grounded context for the LLM (only fields present in the ad)."""
    lines = [
        f"شماره: {i}",
        f"عنوان: {r['title']}",
        f"محل: {r['city']}" + (f"، {r['district']}" if r.get("district") else ""),
        f"قیمت: {_price(r.get('price_toman'))}",
        f"متراژ: {r.get('area_m2') or 'نامشخص'}",
        f"تعداد خواب: {r.get('rooms') or 'نامشخص'}",
        f"لینک آگهی: {r['url']}",
    ]
    if r.get("price_per_m2"):
        lines.append(f"قیمت هر متر: {r['price_per_m2'] / 1e6:.0f} میلیون تومان")
    if r.get("subtitle"):
        lines.append(f"آگهی‌دهنده/زمان: {r['subtitle']}")
    if r.get("matched_features"):
        lines.append(f"ویژگی‌های منطبق با درخواست: {'، '.join(r['matched_features'])}")
    return Document(page_content="\n".join(lines), metadata={"listing_id": r["id"], "title": r["title"], "url": r["url"]})


def create_home_retrieve_node(load_listings, top_k: int = 8):
    """Parse the request (keeping filters from earlier turns of the thread) and rank Divar listings."""

    def home_retrieve_node(state: dict):
        rows = load_listings()
        cities = sorted({r["city"] for r in rows})
        districts = sorted({r["district"] for r in rows if r.get("district")})
        base = HomeFilters(**state["filters"]) if state.get("filters") else None
        parsed = parse_request(state.get("query", ""), cities, districts, base)
        results, relaxed = rank(rows, parsed, top_k)
        docs = [listing_to_document(i, r) for i, r in enumerate(results, 1)]
        retrieval_note = "درخواست فهمیده‌شده: " + ("، ".join(parsed.understood) or "-")
        if relaxed:
            retrieval_note += " | فیلترهای آسان‌شده چون نتیجه دقیقی نبود: " + "، ".join(relaxed)
        return {
            "documents": docs,
            "results": results,
            "filters": vars(parsed.filters),
            "understood": parsed.understood,
            "relaxed": relaxed,
            "retrieval_note": retrieval_note,
            "attempts": 0,
            "debug_info": [
                {
                    "node_name": "home_retrieve_node",
                    "output": [d.metadata for d in docs],
                    "metadata": [{"key": "filters", "value": vars(parsed.filters)}, {"key": "relaxed", "value": relaxed}],
                }
            ],
        }

    return home_retrieve_node
