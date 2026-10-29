FROM nvidia/cuda:13.0.0-cudnn-runtime-ubuntu24.04

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY .python-version .python-version
COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock

RUN uv python install
RUN uv venv
RUN uv sync --frozen --no-cache

CMD ["uv", "run", "uvicorn", "ui.src.api:app", "--host", "0.0.0.0", "--port", "8000"]
