# LLM Agent — Descriptive Job Search (جستجوی توصیفی شغل)

Users describe the job they want in natural Persian (skills, experience,
responsibilities, city, remote work, …) and get **real JobVision job ads**
ranked by relevance, each with an explanation quoted from the ad itself.

> «دنبال یک موقعیت شغلی در حوزه هوش مصنوعی هستم که به Python، مدل‌های زبانی بزرگ و RAG مرتبط باشد و ترجیحاً در تهران یا به‌صورت دورکاری باشد.»

This is the Module B ("job matching") part of the Rahnama hackathon RFP
(`rfp/Rahnama_Hackathon_RFP.docx`), built on the existing LLM-agent codebase
(FastAPI + LangGraph). Two ways to use it:

* **Descriptive search** (`/jobs/search`): deterministic hybrid ranking, no LLM, every explanation quoted from the ad.
* **Job assistant chat** (`/chat`): LangGraph agent with DeepSeek (via Metis) that answers only from retrieved ads.

Both crawl jobvision.ir **live** for the user's keywords on every request, in parallel, and add new ads to the index.

The legacy military-service RAG code was removed; a copy is in `data/backup_before_cleanup.zip`.

## Architecture

```
rfp/jobs.jsonl ──► dataset.py (normalize, dedupe) ──┐
                                                    ├─► build_job_index_cli ─► data/index/
jobvision.ir ──► crawler.py (robots-aware, cached) ─┘      (jobs.jsonl, embeddings.npy, meta.json)
 job pages        data/jobvision/details/<id>.json
                                                              │
Next.js UI (ui/web, :3000) ──/api/*──► FastAPI (ui/src/api.py, :8000) ──► JobSearchService
                                                              query_parser → hybrid ranking → explanations
```

| Path | Role |
|------|------|
| `agent/utilities/persian_text.py` | Persian normalization (Arabic letters, diacritics, digits, ZWNJ, punctuation), tokenization, HTML→text. `normalize_persian` is also applied to `/chat` messages. |
| `agent/job_search/dataset.py` | Maps listing records (+ cached detail pages) to a flat job schema; removes duplicates. Never fills in missing values. |
| `agent/job_search/jobvision_crawler.py` | JobVision public list API client (`/api/v1/JobPost/List`, the only path its robots.txt allows) + CLI; parallel keyword search, shared rate limit. |
| `agent/job_search/live.py` | Live crawl per request: user keywords → list API (parallel) → new ads normalized, indexed, saved to `data/live/jobs.jsonl`, enriched in a background thread. |
| `agent/job_search/crawler.py` | Polite enrichment crawler for public job pages (description, skills, software, languages). |
| `agent/job_search/query_parser.py` | Rule-based understanding of the description: locations, remote, work type, seniority, internship, years of experience, salary floor, skill/role concepts with bilingual synonyms (`configs/job_search_synonyms.yaml`). |
| `agent/job_search/index.py` | Persistent hybrid index: normalized dense vectors (numpy) + field-weighted BM25. |
| `agent/job_search/search.py` | Filtering, ranking, grounded explanations, filter facets. |
| `agent/job_search/evaluation.py` | Precision@5 / nDCG@10 (RFP §10.2). |
| `agent/graphs/job_agent_graph.py` | Chat agent: rewrite follow-up → route → retrieve (job index + live crawl) → LLM relevance filter → grounded answer, or fallback. |
| `agent/graphs/models/__init__.py` | `create_llm`: `url: env` = OpenAI-compatible gateway from `.env` (Metis DeepSeek), otherwise Ollama. |
| `agent/agent_jobs/prompts/` | Agent prompts (router, follow-up rewrite, ad filtering, answer, fallback, domain rules); every prompt forbids inventing jobs, companies, salaries or links. `agent/agent_jobs/snap/arguments.py` loads `configs/*.yaml` CLI arguments. |
| `ui/src/api.py` | FastAPI: `/jobs/search`, `/jobs/filters`, `/jobs/{id}`, `/health`, `/chat` (agent). |
| `ui/web/` | Next.js 16 (App Router, TypeScript), RTL Persian UI. |

## Data

### Primary source: `rfp/jobs.jsonl`

> `rfp/` is **not** committed (scraped JobVision data and the organiser's RFP). Recreate the
> listing file with the crawler, e.g. `python -m agent.job_search.jobvision_crawler -p 50 -o rfp/jobs`
> (50 pages × 30 ads, list API only).

1,470 current JobVision listings (activation dates in October 2026). Fields used:
`id, title, company{nameFa,nameEn,pageUrl,logoUrl}, location{province,city,region},
jobCategories, industry, workType, seniorityLevel, salary{titleFa,min,max},
properties{isRemote,isInternship,requiredRelatedExperienceYears,salaryCanBeShown,…},
benefits, gender, labels, activationTime, expireTime`.

* The original link is `https://jobvision.ir/jobs/<id>` (redirects to the full ad page).
* Salary is shown **only** when `salaryCanBeShown` is true and a salary object exists (~52%).
* The listing has **no description or skill list**, hence the enrichment below.

### Enrichment: public job pages (crawler)
`python -m agent.job_search.enrich_jobs_cli` fetches `https://jobvision.ir/jobs/<id>`
for every listed job and reads the server-rendered detail JSON (with schema.org
`JobPosting` JSON-LD as fallback). It keeps only: description (plain text), skills,
software + level, languages, academic requirements, work days, remote flag, URL.

Responsible collection (RFP NF-08):
* robots.txt is honoured with wildcard semantics (`disallow: *?*`, `*utm_*`, `*/Login/*`; job pages are allowed);
* one request per 1.5 s by default, retries with back-off on 429/5xx;
* identifying User-Agent (`RahnamaHackathonJobSearchBot/1.0 …`);
* per-job cache in `data/jobvision/details/` (git-ignored) so the crawl is resumable and the demo works offline.

⚠️ JobVision's terms of use forbid extracting a substantial portion of the site's
data for display/publication/commercial use or for multi-user storage without
written permission. Keep this cache local and the scope small (the 1,470 ads are
≈2% of the ~64k ads in the site's sitemap), do not redistribute it, and ask
JobVision for permission before any public deployment.

### Hugging Face dataset `JobVision/JobVision_Jobposts_Dataset`
Inspected (365k rows, 2022–2024, CC BY-NC 4.0). It is anonymized: no job id, URL,
company name or description, so results could not link to a real ad. It is
therefore **not** indexed; it could be used later for salary statistics.

## Search and ranking

1. **Query understanding** (deterministic): soft preferences, plus concepts.
   «ترجیحاً» means a preference (ranking boost); «فقط در …» or UI filters are hard constraints.
2. **Hybrid scoring** over all jobs that pass the filters:

   `score = 0.45·semantic + 0.25·BM25 + 0.15·concept coverage + 0.15·preferences`

   * semantic: cosine similarity with `intfloat/multilingual-e5-base` (multilingual, strong on Persian; `query:` / `passage:` prefixes), min-max scaled;
   * BM25: field-weighted (title ×3, categories/skills ×2), query expanded with bilingual synonyms (هوش مصنوعی ↔ AI/machine learning, پایتون ↔ Python, …);
   * concept coverage: share of the user's concepts found literally in the ad;
   * preferences: location-or-remote, work type, seniority, internship, experience, salary.

   Weights of components that do not apply to a query are redistributed (`configs/job_search.yaml`).
3. **Explanations**: for each concept, the first field that contains it (title,
   skills, software, category, industry, description line) is quoted **verbatim**;
   preference checks state the ad's actual values; concepts that the ad does not
   mention are listed as missing. If nothing matches literally, the card says the
   result is only semantically similar. Ads without a crawled description say so.

No LLM is used in the search path, so there is nothing to hallucinate and no API key is needed.

### Live crawl
On each search/chat request the user's concepts (e.g. «هوش مصنوعی», «python», «rag»; at most 4)
are sent to the JobVision list API in parallel threads (one page = 30 ads per keyword,
requests spaced ≥0.3 s overall). Ads not yet indexed are normalized, embedded and added
before ranking; their public pages are fetched later in a background thread (1.5 s apart)
so descriptions and skills appear in subsequent searches. If the site is unreachable the
search still answers from the local index. Settings: `live_crawl` in `configs/job_search.yaml`;
the response field `live` reports keywords and new ads. Rebuilding the index merges `data/live/jobs.jsonl`.

## Chat agent (DeepSeek via Metis)

Create `.env` from `.env.example` (never commit it; it is git-ignored):

```env
LLM_BASE_URL=https://api.metisai.ir/deepseek/v1
LLM_API_KEY=tpsg-...
LLM_MODEL=deepseek-v4-pro
```

The key stays on the server; the Next.js UI only calls `/api/chat`. Graph settings are in
`configs/job_agent_graph.yaml` (`url: env` for every node; a real URL selects an Ollama server).

## Running

Requirements: Python 3.12, Node 20+ (22 recommended).

```bash
# 1. Python environment (the uv index in pyproject points to an internal mirror;
#    use PyPI if you are outside that network)
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe --default-index https://pypi.org/simple \
    fastapi uvicorn sentence-transformers langchain-huggingface langchain-openai langchain-ollama     langgraph python-dotenv pyyaml requests pytest
#   (Linux/macOS: .venv/bin/python)

# 2. Embedding model (≈1.1 GB) into ./model
python -c "from huggingface_hub import snapshot_download; snapshot_download('intfloat/multilingual-e5-base', local_dir='model/multilingual-e5-base')"

# 3. Optional: collect more ads with the list API, and enrich ads with their pages (~40 min, resumable)
python -m agent.job_search.jobvision_crawler -k python -k "هوش مصنوعی" -p 3 -o data/live/extra
python -m agent.job_search.enrich_jobs_cli            # --limit 100 --delay 2

# 4. Build the index (ads without a cached page are indexed from listing fields)
python -m agent.job_search.build_job_index_cli        # --device cuda to use a GPU

# 5. Backend
python -m uvicorn ui.src.api:app --port 8000      # needs .env for the chat tab

# 6. Frontend (another terminal)
cd ui/web && npm install && npm run dev               # http://localhost:3000
#   JOB_API_URL=http://host:8000 if the backend runs elsewhere
```

Make targets (Linux/macOS): `make enrich_jobs build_job_index api web test eval_jobs`.
Docker: `docker compose up` runs the API (`llm`) and the Next.js UI (`web`) on ports 8000/3000; build the index first (step 4) because `./data` is mounted.

### API

```http
POST /jobs/search
{"query": "…", "top_k": 10, "method": "hybrid",          # hybrid | semantic | bm25 | keyword
 "filters": {"provinces": ["تهران"], "work_types": [], "seniority": [], "categories": [],
             "cities": [], "industries": [], "remote_only": false, "internship_only": false,
             "salary_disclosed_only": false, "max_experience_years": null, "min_salary": null}}
     # optional "live": false disables the live crawl for this request
POST /chat              {"message": "...", "thread_id": "..."}  -> grounded answer + source ads
GET  /jobs/filters      facet values with counts
GET  /jobs/{id}         one normalized job
GET  /health
```

## Tests and evaluation

```bash
python -m pytest                                  # Tests/job_search (unit + API tests)
python -m agent.job_search.evaluate_cli           # P@5 / nDCG@10, labels in data/eval/labels.json
```

Tests cover Persian normalization and phrase matching, robots.txt rules, page
parsing, the crawler (caching, robots, retry, failures, using a fake HTTP
session), ingestion of fixtures and of the real `rfp/jobs.jsonl` (no invented
salaries, valid links), query parsing (the example query above, Persian digits,
synonyms, «ری اکت» vs the city «ری»), ranking, hard filters, grounded
explanations, index persistence, metrics and the HTTP API. The tests use a
deterministic fake embedder, so they run in about a second without the model.

EVALUATION_PLACEHOLDER

## Known issues

* `uv.lock` predates the dependency changes in `pyproject.toml` and points to an internal
  mirror; run `uv lock` (with access to that mirror or `--default-index https://pypi.org/simple`)
  before `docker build`, which uses `uv sync --frozen`.
* Chat answers take roughly 25–35 s (router + filter + answer = several LLM calls), above
  the 10 s target in RFP NF-02; `filter_docs.enable: false` saves one round trip.
* The live crawl adds ~1–3 s per search (network to jobvision.ir).

## Third-party components

FastAPI, Uvicorn, sentence-transformers / Hugging Face Transformers,
`intfloat/multilingual-e5-base` (MIT), NumPy, Next.js / React (MIT),
Vazirmatn font (OFL). Job data © JobVision (jobvision.ir). Parts of this
code were written with an AI coding assistant (Claude Code).
