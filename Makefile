PY ?= python3
NPM ?= npm

.PHONY: help crawl enrich_jobs build_job_index jobs_index api web web_install test eval_jobs clean

help:
	@echo "Targets:"
	@echo "  make crawl ARGS='-k python -p 2'  (jobvision list API crawler -> jobs.jsonl/csv)"
	@echo "  make enrich_jobs                  (job pages -> descriptions, cached)"
	@echo "  make build_job_index              (normalize + embed + save index)"
	@echo "  make api                          (FastAPI backend on :8000)"
	@echo "  make web_install / web            (Next.js UI on :3000)"
	@echo "  make test                         (unit tests)"
	@echo "  make eval_jobs                    (P@5 / nDCG@10 vs keyword baseline)"

crawl:
	$(PY) -m agent.job_search.jobvision_crawler $(ARGS)

enrich_jobs:
	$(PY) -m agent.job_search.enrich_jobs_cli $(ARGS)

build_job_index:
	$(PY) -m agent.job_search.build_job_index_cli $(ARGS)

jobs_index: enrich_jobs build_job_index

api:
	$(PY) -m uvicorn ui.src.api:app --host 0.0.0.0 --port 8000

web_install:
	cd ui/web && $(NPM) install

web:
	cd ui/web && $(NPM) run dev

test:
	$(PY) -m pytest

eval_jobs:
	$(PY) -m agent.job_search.evaluate_cli $(ARGS)

clean:
	rm -rf .pytest_cache
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
