import os
import sys
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Literal, Optional

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from yaml.loader import SafeLoader

from agent.job_search.search import SearchFilters
from agent.utilities.persian_text import normalize_persian

app_graph = None
job_search = None
job_search_error: Optional[str] = None


def load_api_config() -> Dict[str, Any]:
    with open("configs/api_config.yaml", "rb") as config_file:
        return yaml.load(config_file, Loader=SafeLoader) or {}


def find_repo_root(start_file: Path) -> Path:
    pythonpath = os.environ.get("PYTHONPATH", "")
    for p in pythonpath.split(":"):
        if not p.strip():
            continue
        candidate = Path(p).resolve()
        if (candidate / "agent" / "graphs").is_dir():
            return candidate

    for p in [start_file.parent, *start_file.parents]:
        if (p / "agent" / "graphs").is_dir():
            return p

    raise RuntimeError(
        f"Could not locate repo root containing 'agent/graphs'. Started from: {start_file}"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global app_graph

    REPO_ROOT = find_repo_root(Path(__file__).resolve())
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    print("Starting API...")
    api_args = load_api_config()

    if api_args.get("trace_enabled", False):
        try:
            from . import tracer  # noqa: F401
        except Exception as e:
            print(f"Tracing disabled: {e}")

    # Job search is the primary feature; a missing index must not crash the API.
    global job_search, job_search_error
    if job_search is None:
        try:
            from agent.job_search.service import create_search_service

            job_search = create_search_service()
            print(f"Job search ready ({len(job_search.index)} jobs)")
        except Exception as e:
            job_search_error = str(e)
            print(f"Job search unavailable: {e}")
            traceback.print_exc()

    # Conversational agent (/chat); LLM settings come from the graph config and .env.
    if api_args.get("chat_enabled", False):
        try:
            from agent.graphs.job_agent_graph import JobAgentGraph

            graph_args = None
            graph_config = api_args.get("chat_graph_config", "configs/job_agent_graph.yaml")
            with open(graph_config, "rb") as config_file:
                graph_args = yaml.load(config_file, Loader=SafeLoader)
            app_graph = JobAgentGraph(graph_args, job_search=job_search)
            print("Graph Initialized")
        except Exception as e:
            print(f"Graph startup failed: {e}")
            traceback.print_exc()

    yield

    app_graph = None
    print("Shutting down API...")


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None


class SourceDoc(BaseModel):
    content: str
    metadata: Dict[str, Any] = {}


class ChatResponse(BaseModel):
    response: Any
    thread_id: str
    selected_node: str = "N/A"
    reformulated_question: str = "N/A"
    raw_response_keys: list[str] = []
    sources: list[SourceDoc] = []
    debug_info: list[Any] = []


class JobSearchFilters(BaseModel):
    provinces: list[str] = []
    cities: list[str] = []
    work_types: list[str] = []
    seniority: list[str] = []
    categories: list[str] = []
    industries: list[str] = []
    remote_only: bool = False
    internship_only: bool = False
    salary_disclosed_only: bool = False
    max_experience_years: Optional[int] = Field(default=None, ge=0, le=50)
    min_salary: Optional[int] = Field(default=None, ge=0)
    include_expired: bool = False
    posted_within_days: Optional[int] = Field(default=None, ge=0, le=365)


class JobSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    filters: JobSearchFilters = JobSearchFilters()
    top_k: int = Field(default=10, ge=1, le=50)
    method: Literal["hybrid", "semantic", "bm25", "keyword"] = "hybrid"
    live: bool = True  # also crawl jobvision.ir for the user's keywords
    sort: Literal["relevance", "newest"] = "relevance"


app = FastAPI(
    title="Descriptive Job Search API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def serialize_docs(docs, k=5, max_chars=1200):
    out = []
    for d in (docs or [])[:k]:
        out.append(
            {
                "content": getattr(d, "page_content", str(d))[:max_chars],
                "metadata": getattr(d, "metadata", {}) or {},
            }
        )
    return out


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "graph_ready": app_graph is not None,
        "job_search_ready": job_search is not None,
        "job_search_error": job_search_error,
        "jobs_indexed": len(job_search.index) if job_search is not None else 0,
    }


def _require_job_search():
    if job_search is None:
        raise HTTPException(
            status_code=503,
            detail=f"Job search not ready: {job_search_error or 'initializing'}",
        )
    return job_search


@app.post("/jobs/search")
def search_jobs(request: JobSearchRequest):
    service = _require_job_search()
    try:
        return service.search(
            request.query,
            SearchFilters(**request.filters.model_dump()),
            top_k=request.top_k,
            method=request.method,
            live=request.live,
            sort=request.sort,
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


@app.get("/jobs/filters")
def job_filters():
    return _require_job_search().filter_options()


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = _require_job_search().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _process(query: str, thread_id: str) -> Dict[str, Any]:
    assert app_graph is not None
    return app_graph.process_message(query, thread_id, thread_id)


# chat_attempts = {}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if app_graph is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    thread_id = request.thread_id or "1"

    # TODO: re-enable or remove per-thread message limit
    # if chat_attempts.get(thread_id) is None:
    #     chat_attempts[thread_id] = 0
    # chat_attempts[thread_id] += 1

    # if chat_attempts[thread_id] > 5:
    #     return ChatResponse(
    #         response="یک چت جدیدی ایجاد کنید!",
    #         thread_id=thread_id,
    #         selected_node="N/A",
    #         reformulated_question="N/A",
    #         raw_response_keys=[],
    #         debug_info=[],
    #     )

    try:
        result = _process(normalize_persian(request.message), thread_id)

        return ChatResponse(
            response=result["content"],
            thread_id=thread_id,
            selected_node="N/A",
            reformulated_question="N/A",
            raw_response_keys=[],
            sources=serialize_docs(result.get("documents", [])),
            debug_info=result.get("debug_info", []),
        )

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")


@app.post("/reset/{thread_id}")
async def reset_thread(thread_id: str):
    return {"status": "reset", "thread_id": thread_id}


def main():
    api_args = None
    with open("configs/api_config.yaml", "rb") as config_file:
        api_args = yaml.load(config_file, Loader=SafeLoader)

    uvicorn.run("api:app", host="0.0.0.0", port=api_args["port"])


if __name__ == "__main__":
    main()
