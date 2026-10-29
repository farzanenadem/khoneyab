# syntax=docker/dockerfile:1
# Job search API (FastAPI + embeddings). CPU-only image; the embedding model and the
# job index are mounted from ./model and ./data at runtime (see docker-compose.yaml).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    HF_HUB_OFFLINE=1

WORKDIR /app

# CPU build of torch first (the default wheel pulls several GB of CUDA libraries).
# The pip cache mount keeps downloads between builds, so a network hiccup does not restart from zero.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --index-url https://download.pytorch.org/whl/cpu torch

# Dependencies only (the repo is run from /app, not installed as a package); this layer is
# cached until pyproject.toml changes.
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip \
    python -c "import tomllib; p = tomllib.load(open('pyproject.toml', 'rb'))['project']; \
print('\n'.join(p['dependencies'] + p['optional-dependencies']['job-groups']))" > /tmp/requirements.txt \
    && pip install -r /tmp/requirements.txt

COPY agent ./agent
COPY ui/__init__.py ./ui/__init__.py
COPY ui/src ./ui/src
COPY configs ./configs

RUN useradd --create-home --uid 1000 app && chown -R app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)"

CMD ["uvicorn", "ui.src.api:app", "--host", "0.0.0.0", "--port", "8000"]
