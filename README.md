# Descriptive Job Search (جستجوی توصیفی شغل)

Describe the job you want in plain Persian — skills, experience, city, remote work — and get
**real JobVision ads**, ranked by relevance and freshness, each with an explanation quoted from the ad.

> «دنبال کار در حوزه هوش مصنوعی با Python، مدل‌های زبانی بزرگ و RAG هستم، ترجیحاً تهران یا دورکاری»

Built for the Rahnama College ML Bootcamp hackathon (Module B: job matching).

## Features
- **Hybrid ranking**: `multilingual-e5-base` embeddings + BM25 + skill coverage + location/remote/seniority preferences + recency. Weakly related and expired ads are dropped.
- **Grounded explanations**: matched skills are quoted verbatim from the ad; missing skills are listed; salary is shown only if the ad states it.
- **Live crawl**: every request also searches the JobVision list API for the user's keywords (parallel, rate-limited, robots.txt-compliant); new ads join the index immediately.
- **Chat assistant**: LangGraph agent on DeepSeek (via Metis) that answers only from retrieved ads.
- **Job groups (KMeans + Qdrant) — optional, off by default** (`job_groups.enabled` in `configs/job_search.yaml`):
  a request is placed into its closest job groups, learned from the
  [JobVision Jobposts Dataset](https://huggingface.co/datasets/JobVision/JobVision_Jobposts_Dataset)
  (2022–2024) by two-level KMeans (77 job categories → KMeans inside each, k by silhouette). The groups'
  typical titles widen the live crawl and a `group` component re-ranks **current** ads; dataset rows are
  never returned as jobs. Disabled because its effect on ranking accuracy is not measured yet.
- **Persian-first**: normalization of Arabic letters, digits, ZWNJ; bilingual synonyms (پایتون ↔ Python); RTL Next.js UI.

## Stack
FastAPI · LangGraph · sentence-transformers · NumPy (file-based index) · Next.js 16

## Quick start
```bash
# Python 3.12
uv venv .venv && uv pip install --python .venv/Scripts/python.exe --default-index https://pypi.org/simple \
  fastapi uvicorn sentence-transformers langchain-huggingface langchain-openai langchain-ollama langgraph python-dotenv pyyaml requests pytest

cp .env.example .env            # set LLM_API_KEY (Metis) for the chat tab

python -c "from huggingface_hub import snapshot_download; snapshot_download('intfloat/multilingual-e5-base', local_dir='model/multilingual-e5-base')"
python -m agent.job_search.jobvision_crawler -p 50 -o rfp/jobs     # collect ads (list API)
python -m agent.job_search.enrich_jobs_cli                          # optional: descriptions
python -m agent.job_search.build_job_index_cli                      # build the index

# optional job groups (off by default; then set job_groups.enabled: true and restart the API)
pip install ".[job-groups]" && docker compose --profile job-groups up -d qdrant
python -m agent.job_search.build_job_groups_cli                      # dataset → KMeans job groups → Qdrant

python -m uvicorn ui.src.api:app --port 8000                        # backend
cd ui/web && npm install && npm run dev                             # UI → http://localhost:3000
```

## API
| Endpoint | Purpose |
|---|---|
| `POST /jobs/search` | `{query, filters, top_k, sort: relevance\|newest, live}` → ranked ads + explanations |
| `GET /jobs/filters` | filter values with counts |
| `POST /jobs/groups` | optional: `{text, top_k}` → closest job groups (fit, matched/missing key skills); 503 while job groups are disabled |
| `GET /jobs/groups/{id}` | optional: one job group's profile |
| `POST /chat` | `{message, thread_id}` → grounded answer + source ads |

## Tests
```bash
python -m pytest        # 98 tests, offline (fake embedder, in-memory Qdrant, no network)
```

## Data & responsibility
Ads come from public JobVision pages/APIs, collected at a low rate with an identifying User-Agent and
only the fields needed for matching. Scraped data is not committed. API keys live only in `.env`.
Job groups are built from the JobVision Jobposts Dataset (© JobVision, CC BY-NC 4.0, non-commercial use);
the dataset is not committed, and its gender, age, military-service and disability columns are never read.
