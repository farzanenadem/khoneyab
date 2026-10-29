# AGENTS.md

Guidance for AI coding agents working in this repository.

## What this is
Descriptive Persian job search over real JobVision ads: hybrid retrieval + grounded explanations
(`/jobs/search`), a LangGraph chat assistant on DeepSeek via Metis (`/chat`), and a Next.js RTL UI.

## Layout
- `agent/job_search/` — core: `dataset.py` (normalize/dedupe), `crawler.py` (job pages, robots-aware),
  `jobvision_crawler.py` (list API client + CLI), `live.py` (per-request live crawl), `query_parser.py`,
  `index.py` (numpy vectors + BM25), `search.py` (ranking, filters, explanations), `service.py` (factory).
- `agent/graphs/job_agent_graph.py` + `agent/graphs/nodes/` — chat agent; prompts in `agent/agent_jobs/prompts/`.
- `agent/graphs/models/__init__.py` — `create_llm`: `url: env` → OpenAI-compatible gateway from `.env`, else Ollama.
- `agent/utilities/persian_text.py` — Persian normalization/tokenization (use it; don't re-implement).
- `ui/src/api.py` — FastAPI. `ui/web/` — Next.js 16 (read `ui/web/AGENTS.md` before editing it).
- `configs/*.yaml` — all settings; CLI args are loaded by `agent/agent_jobs/snap/arguments.py`.
- `Tests/job_search/` — pytest suite.

## Commands
```bash
python -m pytest                                   # must stay green and offline
python -m agent.job_search.build_job_index_cli     # rebuild index after data/model changes
python -m uvicorn ui.src.api:app --port 8000
cd ui/web && npx tsc --noEmit && npm run dev
```
On Windows use `.venv/Scripts/python.exe`. Another project on `sys.path` also has an `agent` package —
keep `agent/__init__.py` and `ui/__init__.py`.

## Rules
- **Never fabricate** jobs, companies, salaries, links or skills. Explanations must quote ad text; show
  salary only when `salary_text` exists. Prompts must keep this constraint.
- **Secrets**: keys only in `.env` (git-ignored). Never commit `.env`, `rfp/`, `data/`, `model/`.
- **Crawling**: respect robots.txt (`candidateapi` allows only `/api/v1/JobPost/List`; job pages on
  `jobvision.ir` are allowed), keep rate limits and the identifying User-Agent, store only needed fields.
- Search path stays LLM-free and deterministic; LLM use belongs to `/chat`.
- Tests use `FakeEmbeddings` and fake HTTP sessions — no network or model downloads in tests.
- Match existing style: config-driven factories, small modules, Persian user-facing text.
