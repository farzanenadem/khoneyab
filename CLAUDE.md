# CLAUDE.md

See **AGENTS.md** for the project overview, layout, commands and rules — they apply to Claude Code too.

Quick reminders:
- Run `python -m pytest` (offline, ~1 s) after changes; run `npx tsc --noEmit` in `ui/web` after UI changes.
- Ranking lives in `agent/job_search/search.py`; tunables in `configs/job_search.yaml` (`ranking`, `live_crawl`).
- Chat models come from `.env` (`LLM_MODEL` for answers, `LLM_FAST_MODEL` for routing/filtering).
- Never print, log or commit the contents of `.env`.
- Rebuild the index (`python -m agent.job_search.build_job_index_cli`) after changing data, embedding model
  or `passage_text`; restart the API afterwards.
