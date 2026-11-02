# AGENTS.md

Guidance for AI coding agents working in this repository.

## What this is

خونه‌یاب is a Persian, RTL home-listing assistant built on real Divar ads. It provides deterministic
listing search (`/homes/search`), loan planning, purchase due-diligence guidance and a grounded
LangGraph chat assistant (`/homes/chat`). The legacy JobVision job-search surface remains under
`/jobs/*` for compatibility.

## Layout

- `agent/home_search/` — home domain: listings, Divar crawler, filters, loans and purchase roadmap.
- `agent/graphs/home_agent_graph.py` and `agent/graphs/nodes/` — chat graph and small testable nodes.
- `agent/agent_homes/prompts/` — Persian home-assistant prompts.
- `agent/job_search/` — retained JobVision search, ranking and optional Qdrant job groups.
- `agent/utilities/` — Persian normalization/tokenization, embeddings and usage ledger.
- `ui/src/api.py` — FastAPI routes, Pydantic request/response contracts and middleware.
- `ui/web/` — Next.js 16 RTL UI (read `ui/web/AGENTS.md` before editing).
- `configs/` — YAML configuration without secrets.
- `Tests/home_search/` and `Tests/job_search/` — offline pytest suites.

## Commands

```bash
python -m pytest
python -m uvicorn ui.src.api:app --port 8000
cd ui/web && npx tsc --noEmit && npm run dev
docker compose up -d --build
```

On Windows use `.venv/Scripts/python.exe`. Keep `agent/__init__.py` and `ui/__init__.py` because
another project on `sys.path` also has an `agent` package.

## Rules

- Never fabricate homes, prices, companies, links or features. Explanations must quote source text;
  show a value only when it exists in the listing. Prompts must keep this constraint.
- Secrets belong only in `.env` (git-ignored). Never commit `.env`, `rfp/`, `data/`, `model/` or logs.
- Divar crawling must use the identifying User-Agent, obey rate limits and store only needed fields.
- Home search stays deterministic and LLM-free; LLM use belongs to `/homes/chat` and `/chat`.
- Tests use fake HTTP/embedding sessions and no network or model downloads.
- Job groups are optional and disabled by default; they provide background knowledge only and never
  return dataset rows as jobs. Never read excluded demographic columns from the dataset.
- Match existing style: config-driven factories, small modules and Persian user-facing text.
