import os
import sys
import time
import logging
from collections import defaultdict, deque
from threading import Lock
from uuid import uuid4
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Literal, Optional

import uvicorn
import yaml
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from yaml.loader import SafeLoader

from agent.job_search.search import SearchFilters
from agent.utilities.persian_text import normalize_persian
from agent.utilities.usage import USAGE, begin_request, create_ledger, request_usage, track_feature

logger = logging.getLogger("khoneyab.api")

app_graph = None
resume_llm = None
job_search = None
job_search_error: Optional[str] = None


def load_api_config() -> Dict[str, Any]:
    config_path = Path(__file__).resolve().parents[2] / "configs" / "api_config.yaml"
    with config_path.open("rb") as config_file:
        return yaml.load(config_file, Loader=SafeLoader) or {}


def find_repo_root(start_file: Path) -> Path:
    pythonpath = os.environ.get("PYTHONPATH", "")
    for p in pythonpath.split(os.pathsep):
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

    logger.info("Starting API")
    api_args = load_api_config()

    if api_args.get("trace_enabled", False):
        try:
            from . import tracer  # noqa: F401
        except Exception as e:
            logger.warning("Tracing disabled: %s", e)

    # The legacy jobs index is optional; missing data must not crash home search.
    # Persistent request log for the monitoring tab (MONITORING_DB_PATH=off disables it).
    if USAGE.ledger is None:
        USAGE.ledger = create_ledger()
        if USAGE.ledger is not None:
            logger.info("Monitoring ledger: %s", USAGE.ledger.path)

    global job_search, job_search_error
    if job_search is None:
        try:
            from agent.job_search.service import create_search_service

            job_search = create_search_service()
            logger.info("Legacy jobs index ready (%s records)", len(job_search.index))
        except Exception as e:
            job_search_error = str(e)
            logger.exception("Legacy jobs index unavailable: %s", e)

    # LLM for resume profile extraction (optional; rules are used without it).
    global resume_llm
    if api_args.get("resume_llm_enabled", True):
        try:
            from agent.graphs.models import create_llm

            resume_llm = create_llm("env_fast", "env")
        except Exception as e:
            logger.warning("Resume LLM unavailable; using rule-based extraction: %s", e)

    # Conversational agent (/chat); LLM settings come from the graph config and .env.
    if api_args.get("chat_enabled", False):
        try:
            from agent.graphs.home_agent_graph import HomeAgentGraph

            graph_args = None
            graph_config = Path(api_args.get("chat_graph_config", "configs/home_agent_graph.yaml"))
            if not graph_config.is_absolute():
                graph_config = REPO_ROOT / graph_config
            with graph_config.open("rb") as config_file:
                graph_args = yaml.load(config_file, Loader=SafeLoader)
            app_graph = HomeAgentGraph(graph_args, load_listings=_listings)
            logger.info("Home graph initialized")
        except Exception as e:
            logger.exception("Graph startup failed: %s", e)

    yield

    app_graph = None
    logger.info("Shutting down API")


class APIModel(BaseModel):
    """Shared HTTP contract policy: reject typos and normalize user-entered text."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ChatRequest(APIModel):
    message: str = Field(min_length=2, max_length=2000)
    thread_id: Optional[str] = Field(default=None, min_length=1, max_length=120, pattern=r"^[\w.-]+$")


class SourceDoc(APIModel):
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChatResponse(APIModel):
    response: Any
    thread_id: str
    selected_node: str = "N/A"
    reformulated_question: str = "N/A"
    raw_response_keys: list[str] = Field(default_factory=list)
    sources: list[SourceDoc] = Field(default_factory=list)
    debug_info: list[Any] = Field(default_factory=list)
    usage: Dict[str, Any] = Field(default_factory=dict)  # tokens of this request (see agent/utilities/usage.py)


class JobSearchFilters(APIModel):
    provinces: list[str] = Field(default_factory=list, max_length=30)
    cities: list[str] = Field(default_factory=list, max_length=30)
    work_types: list[str] = Field(default_factory=list, max_length=30)
    seniority: list[str] = Field(default_factory=list, max_length=30)
    categories: list[str] = Field(default_factory=list, max_length=30)
    industries: list[str] = Field(default_factory=list, max_length=30)
    remote_only: bool = False
    internship_only: bool = False
    salary_disclosed_only: bool = False
    max_experience_years: Optional[int] = Field(default=None, ge=0, le=50)
    min_salary: Optional[int] = Field(default=None, ge=0)
    include_expired: bool = False
    posted_within_days: Optional[int] = Field(default=None, ge=0, le=365)
    sources: list[str] = Field(default_factory=list, max_length=30)


class JobSearchRequest(APIModel):
    query: str = Field(min_length=2, max_length=2000)
    filters: JobSearchFilters = Field(default_factory=JobSearchFilters)
    top_k: int = Field(default=10, ge=1, le=50)
    method: Literal["hybrid", "semantic", "bm25", "keyword"] = "hybrid"
    live: bool = True  # also crawl jobvision.ir for the user's keywords
    sort: Literal["relevance", "newest"] = "relevance"


app = FastAPI(
    title="خونه‌یاب API",
    description="جست‌وجوی آگهی خانه، برنامه‌ریزی وام و نقشه راه بررسی پیش از خرید.",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def time_requests(request, call_next):
    """Per-request latency and LLM usage for the monitoring tab (monitoring routes themselves are skipped)."""
    started = time.perf_counter()
    req = begin_request(request.url.path)
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = req["request_id"]
        return response
    finally:
        route = request.scope.get("route")
        path = getattr(route, "path", None)
        if path and not path.startswith(("/usage", "/health")):
            USAGE.record_request(f"{request.method} {path}", time.perf_counter() - started, req, status_code)


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
    try:
        home_count = len(_listings())
    except Exception:
        home_count = 0
    home_ready = home_count > 0
    status = "healthy" if job_search is not None or home_ready else "degraded"
    return {
        "status": status,
        "home_search_ready": home_ready,
        "homes_indexed": home_count,
        "graph_ready": app_graph is not None,
        "job_search_ready": job_search is not None,
        # Do not expose startup exception text (paths, dependency details or secrets) publicly.
        "job_search_error": bool(job_search_error),
        "job_search_status": "ready" if job_search is not None else "unavailable",
        "jobs_indexed": len(job_search.index) if job_search is not None else 0,
        "crawl_cache": None if job_search is None or job_search.crawl_cache is None else {
            "loaded_on_start": job_search.cached_jobs_loaded,
            "cached": job_search.crawl_cache.count(),
        },
    }


@app.get("/usage")
def llm_usage():
    """LLM observability: token/latency/call counters since the API started (no prompts stored)."""
    return USAGE.summary()


@app.post("/usage/reset")
def reset_llm_usage(history: bool = False):
    """Reset the live counters; `?history=true` also clears the persistent request log."""
    USAGE.reset()
    if history and USAGE.ledger is not None:
        USAGE.ledger.clear()
    return {"status": "reset"}


def _require_job_search():
    if job_search is None:
        raise HTTPException(
            status_code=503,
            detail="Legacy jobs index is not ready; try again after startup completes",
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
    except Exception:
        logger.exception("Job search failed")
        raise HTTPException(status_code=500, detail="Search service error")


@app.post("/resume/search")
def search_by_resume(
    file: UploadFile = File(...),
    top_k: int = Form(10),
    live: bool = Form(True),
):
    """Upload a PDF/DOCX/TXT resume; it is processed in memory and never stored or logged."""
    from agent.job_search.resume import ResumeError, extract_text, search_with_resume

    service = _require_job_search()
    if not 1 <= top_k <= 50:
        raise HTTPException(status_code=422, detail="top_k must be between 1 and 50")
    try:
        text = extract_text(file.filename or "", file.file.read())
        with track_feature("resume"):
            return search_with_resume(service, text, llm=resume_llm, top_k=top_k, live=live)
    except ResumeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Do not include resume content in logs or errors.
        logger.warning("Resume search failed: %s", type(e).__name__)
        raise HTTPException(status_code=500, detail="Resume processing error")


class RoadmapRequest(APIModel):
    known_skills: list[str] = Field(default_factory=list, max_length=60)


class HomeFilterPayload(APIModel):
    city: Optional[str] = Field(default=None, max_length=100)
    q: Optional[str] = Field(default=None, max_length=500)
    min_price: Optional[int] = Field(default=None, ge=0)
    max_price: Optional[int] = Field(default=None, ge=0)
    min_area: Optional[int] = Field(default=None, ge=0, le=10000)
    max_area: Optional[int] = Field(default=None, ge=0, le=10000)
    rooms: Optional[int] = Field(default=None, ge=1, le=20)

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min_price cannot exceed max_price")
        if self.min_area is not None and self.max_area is not None and self.min_area > self.max_area:
            raise ValueError("min_area cannot exceed max_area")
        return self


class HomeChatRequest(APIModel):
    message: str = Field(min_length=2, max_length=2000)
    thread_id: Optional[str] = Field(default=None, min_length=1, max_length=120, pattern=r"^[\w.-]+$")
    filters: Optional[HomeFilterPayload] = None
    top_k: int = Field(default=8, ge=1, le=20)


class HomeListingResponse(APIModel):
    id: str
    source: str = "divar"
    url: str
    title: str
    category: Optional[str] = None
    city: str
    district: str = ""
    price_text: str = ""
    price_toman: Optional[int] = None
    area_m2: Optional[int] = None
    rooms: Optional[int] = None
    price_per_m2: Optional[int] = None
    subtitle: str = ""
    tag: str = ""
    image_url: str = ""
    image_count: int = 0
    crawled_at: Optional[str] = None
    posted_at: Optional[str] = None
    matched_features: list[str] = Field(default_factory=list)


class HomeSearchResponse(APIModel):
    total: int
    results: list[HomeListingResponse]
    median_price_per_m2: Optional[int] = None
    limit: int = 60
    offset: int = 0
    next_offset: Optional[int] = None


class HomeCityOption(APIModel):
    city: str
    count: int = Field(ge=0)


class HomeOptionsResponse(APIModel):
    total: int = Field(ge=0)
    cities: list[HomeCityOption] = Field(default_factory=list)


class HomeChatResponse(APIModel):
    thread_id: str
    reply: str
    filters: Optional[dict[str, Any]] = None
    understood: list[str] = Field(default_factory=list)
    relaxed: list[str] = Field(default_factory=list)
    results: list[HomeListingResponse] = Field(default_factory=list)


@app.post("/jobs/{job_id}/roadmap")
def job_roadmap(job_id: str, request: RoadmapRequest):
    from agent.job_search.roadmap import build_roadmap

    job = _require_job_search().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    with track_feature("roadmap"):
        return build_roadmap(job, request.known_skills, llm=resume_llm)


_home_listings: Optional[list] = None
_home_listings_mtime: Optional[int] = None
_home_listings_lock = Lock()
_rate_lock = Lock()
_rate_windows: dict[str, deque[float]] = defaultdict(deque)


def _listings() -> list:
    """Load Divar listings lazily and refresh when the crawler replaces the file."""
    global _home_listings, _home_listings_mtime
    from agent.home_search.divar_crawler import DEFAULT_OUT
    from agent.home_search.listings import load_listings

    try:
        mtime = DEFAULT_OUT.stat().st_mtime_ns
    except FileNotFoundError:
        mtime = None
    if _home_listings is None or mtime != _home_listings_mtime:
        with _home_listings_lock:
            if _home_listings is None or mtime != _home_listings_mtime:
                _home_listings = load_listings(DEFAULT_OUT)
                _home_listings_mtime = mtime
    return _home_listings


@app.middleware("http")
async def protect_llm_routes(request, call_next):
    """Small in-process guard against accidental LLM cost spikes.

    Set LLM_REQUESTS_PER_MINUTE=0 to disable it. Production deployments should put a
    distributed gateway limit in front of multiple API workers as well.
    """
    if request.url.path not in {"/chat", "/homes/chat"}:
        return await call_next(request)
    try:
        limit = int(os.getenv("LLM_REQUESTS_PER_MINUTE", "60"))
    except ValueError:
        limit = 60
    if limit > 0:
        now = time.monotonic()
        client = request.client.host if request.client else "unknown"
        with _rate_lock:
            window = _rate_windows[client]
            while window and now - window[0] >= 60:
                window.popleft()
            if len(window) >= limit:
                return JSONResponse(status_code=429, content={"detail": "Too many chat requests"})
            window.append(now)
    return await call_next(request)


@app.get("/homes/search", response_model=HomeSearchResponse)
def home_search(
    city: Optional[str] = Query(default=None, max_length=100),
    q: Optional[str] = Query(default=None, max_length=500),
    min_price: Optional[int] = Query(default=None, ge=0),
    max_price: Optional[int] = Query(default=None, ge=0),
    min_area: Optional[int] = Query(default=None, ge=0, le=10000),
    max_area: Optional[int] = Query(default=None, ge=0, le=10000),
    rooms: Optional[int] = Query(default=None, ge=1, le=20),
    sort: Literal["newest", "price_asc", "price_desc", "price_per_m2"] = "newest",
    limit: int = Query(default=60, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    from agent.home_search.listings import HomeFilters, search_listings

    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=422, detail="min_price cannot exceed max_price")
    if min_area is not None and max_area is not None and min_area > max_area:
        raise HTTPException(status_code=422, detail="min_area cannot exceed max_area")
    f = HomeFilters(city, q, min_price, max_price, min_area, max_area, rooms)
    return search_listings(_listings(), f, sort=sort, limit=limit, offset=offset)


@app.get("/homes/options", response_model=HomeOptionsResponse)
def home_options():
    from agent.home_search.listings import city_options

    rows = _listings()
    return {"total": len(rows), "cities": city_options(rows)}


@app.post("/homes/chat", response_model=HomeChatResponse)
def home_chat(request: HomeChatRequest):
    """Descriptive home search. The «خونه‌یاب» agent (HomeAgentGraph) answers when it is up and keeps
    the filters per thread; otherwise a deterministic reply is built from the same ranking."""
    from agent.home_search.assistant import converse
    from agent.home_search.listings import HomeFilters

    message = normalize_persian(request.message)
    thread_id = request.thread_id or f"home-{uuid4().hex}"
    if app_graph is not None:
        try:
            with track_feature("home_chat"):
                out = app_graph.process_message(message, "home", thread_id)
            reply = out.get("content", "")
            if not isinstance(reply, str):
                reply = str(reply)
            return {"thread_id": thread_id, **{k: out.get(k) for k in ("filters", "understood", "relaxed", "results")}, "reply": reply}
        except Exception:
            logger.exception("Home graph request failed; using deterministic fallback")
    base = None
    if request.filters:
        base = HomeFilters(**request.filters.model_dump(exclude_none=True))
    with track_feature("home_chat"):
        return {"thread_id": thread_id, **converse(_listings(), message, base, llm=resume_llm, top_k=request.top_k)}


@app.get("/homes/roadmap")
def home_roadmap():
    from agent.home_search.roadmap import purchase_roadmap

    return purchase_roadmap()


class LoanCatalogItem(APIModel):
    id: str
    bank: str
    name: str
    caps: dict[str, int]
    couple_multiplier: float = Field(ge=0)
    rate: float = Field(ge=0, le=60)
    years: int = Field(ge=1, le=50)
    first_home_only: bool = False
    child_required: bool = False
    requirement: str
    bond_cost_ratio: float = Field(ge=0, le=1)
    default_amount: int = Field(ge=0)
    tier: str


class LoanCatalogResponse(APIModel):
    loans: list[LoanCatalogItem] = Field(default_factory=list)
    as_of: str
    disclaimer: str


@app.get("/homes/loans", response_model=LoanCatalogResponse)
def home_loans(city: str = Query(default="تهران", max_length=100), married: bool = False):
    from agent.home_search.loans import loan_catalog

    return loan_catalog(city, married)


class LoanOverrideModel(APIModel):
    id: str
    selected: bool = True
    amount: Optional[int] = Field(default=None, ge=0)
    rate: Optional[float] = Field(default=None, ge=0, le=60)
    years: Optional[int] = Field(default=None, ge=1, le=30)


class LoanPlanRequest(APIModel):
    price: int = Field(gt=0)
    savings: int = Field(default=0, ge=0)
    monthly_income: int = Field(default=0, ge=0)
    city: str = "تهران"
    married: bool = False
    has_child: bool = False
    first_home: bool = True
    loans: list[LoanOverrideModel] = Field(default_factory=list, max_length=20)


class LoanPlanItem(APIModel):
    id: str
    name: str
    bank: str
    selected: bool
    eligible: bool
    issues: list[str] = Field(default_factory=list)
    amount: int = Field(ge=0)
    rate: float = Field(ge=0, le=60)
    years: int = Field(ge=1, le=50)
    monthly_installment: int = Field(ge=0)
    total_repayment: int = Field(ge=0)
    total_interest: int
    bond_cost: int = Field(ge=0)
    cap_warning: bool = False


class LoanPlanResponse(APIModel):
    loans: list[LoanPlanItem] = Field(default_factory=list)
    total_loan: int
    total_monthly_installment: int
    bond_cost: int
    loan_share_pct: float
    gap: int
    debt_to_income_pct: Optional[float]
    advice: str
    as_of: str
    warnings: list[str] = Field(default_factory=list)


@app.post("/homes/loans/plan", response_model=LoanPlanResponse)
def home_loan_plan(request: LoanPlanRequest):
    from agent.home_search.loans import LoanOverride, PlanRequest, build_plan

    from agent.home_search.loans import LOANS

    known_ids = {loan["id"] for loan in LOANS}
    requested_ids = [override.id for override in request.loans]
    unknown = sorted(set(requested_ids) - known_ids)
    if unknown:
        raise HTTPException(status_code=422, detail={"unknown_loan_ids": unknown})
    if len(requested_ids) != len(set(requested_ids)):
        raise HTTPException(status_code=422, detail="Duplicate loan ids are not allowed")
    data = request.model_dump()
    data["loans"] = [LoanOverride(**o) for o in data["loans"]]
    return build_plan(PlanRequest(**data))


@app.get("/jobs/filters")
def job_filters():
    return _require_job_search().filter_options()


class JobGroupsRequest(APIModel):
    text: str = Field(min_length=2, max_length=4000)  # the user's description and/or resume text
    top_k: int = Field(default=3, ge=1, le=10)


def _require_job_groups():
    service = _require_job_search()
    if service.job_groups is None:
        raise HTTPException(status_code=503, detail="Job groups not available: build them with build_job_groups_cli")
    return service


@app.post("/jobs/groups")
def job_groups(request: JobGroupsRequest):
    """Closest job groups for a request. Groups are background knowledge learned from
    the JobVision dataset (2022-2024); job recommendations come only from /jobs/search."""
    service = _require_job_groups()
    from agent.job_search.job_groups import public_group

    placements = service.place_groups(normalize_persian(request.text), top_k=request.top_k)
    return {"groups": [public_group(p) for p in placements], "meta": service.job_groups.meta}


@app.get("/jobs/groups/{group_id}")
def job_group(group_id: str):
    group = _require_job_groups().job_groups.get(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Job group not found")
    return group


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = _require_job_search().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _process(query: str, thread_id: str) -> Dict[str, Any]:
    assert app_graph is not None
    return app_graph.process_message(query, thread_id, thread_id)


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    if app_graph is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    thread_id = request.thread_id or f"chat-{uuid4().hex}"

    try:
        with track_feature("chat"):
            result = _process(normalize_persian(request.message), thread_id)

        return ChatResponse(
            response=result["content"],
            thread_id=thread_id,
            selected_node="N/A",
            reformulated_question="N/A",
            raw_response_keys=[],
            sources=serialize_docs(result.get("documents", [])),
            debug_info=result.get("debug_info", []),
            usage=request_usage(),
        )

    except Exception:
        logger.exception("Chat request failed")
        raise HTTPException(status_code=500, detail="Chat service error")


@app.post("/reset/{thread_id}")
def reset_thread(thread_id: str):
    if app_graph is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    app_graph.reset_thread(thread_id)
    return {"status": "reset", "thread_id": thread_id}


def main():
    api_args = None
    config_path = Path(__file__).resolve().parents[2] / "configs" / "api_config.yaml"
    with config_path.open("rb") as config_file:
        api_args = yaml.load(config_file, Loader=SafeLoader)

    uvicorn.run("ui.src.api:app", host="0.0.0.0", port=api_args["port"])


if __name__ == "__main__":
    main()
