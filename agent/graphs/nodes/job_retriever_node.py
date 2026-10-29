from langchain_core.documents import Document


def job_to_document(result: dict) -> Document:
    """Render one search result as grounded context for the LLM (only fields present in the ad)."""
    job = result["job"]
    place = "، ".join(x for x in (job.get("city"), job.get("province")) if x)
    lines = [
        f"عنوان: {job['title']}",
        f"شرکت: {job.get('company') or 'ذکر نشده'}",
        f"محل کار: {place or 'ذکر نشده'}" + (" (امکان دورکاری)" if job.get("is_remote") else ""),
        f"لینک آگهی: {job['url']}",
        f"حقوق: {job.get('salary_text') or 'اعلام نشده'}",
    ]
    if job.get("work_type"):
        lines.append(f"نوع همکاری: {job['work_type']}")
    if job.get("seniority"):
        lines.append(f"سطح: {job['seniority']}")
    if job.get("required_experience_years") is not None:
        lines.append(f"سابقه موردنیاز: {job['required_experience_years']} سال")
    if job.get("categories"):
        lines.append(f"دسته‌بندی: {'، '.join(job['categories'])}")
    software = [s["name"] for s in job.get("software") or []]
    if job.get("skills") or software:
        lines.append(f"مهارت‌ها و نرم‌افزارها: {'، '.join(job.get('skills', []) + software)}")
    if job.get("academic"):
        lines.append(f"تحصیلات: {'، '.join(job['academic'])}")
    if job.get("description"):
        lines.append(f"شرح آگهی: {job['description'][:700]}")
    exp = result.get("explanation") or {}
    if exp.get("missing"):
        lines.append(f"در آگهی ذکر نشده: {'، '.join(exp['missing'])}")
    return Document(
        page_content="\n".join(lines),
        metadata={"job_id": job["id"], "title": job["title"], "url": job["url"], "score": result["score"]},
    )


def create_job_retrieve_node(job_search, top_k: int = 8):
    def job_retrieve_node(state: dict):
        query = state.get("query", "")
        # Live crawl for the user's keywords runs before ranking, in parallel per keyword.
        res = job_search.search(query, top_k=top_k, live=True)
        docs = [job_to_document(r) for r in res["results"]]
        return {
            "documents": docs,
            "attempts": 0,
            "debug_info": [
                {
                    "node_name": "job_retrieve_node",
                    "output": [d.metadata for d in docs],
                    "metadata": [
                        {"key": "parsed_query", "value": res["query"]},
                        {"key": "live_crawl", "value": res.get("live")},
                    ],
                }
            ],
        }

    return job_retrieve_node
