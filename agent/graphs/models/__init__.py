import os

from agent._core.settings import ROOT_DIR

ENV_MARKER = "env"
ENV_FAST_MARKER = "env_fast"  # LLM_FAST_MODEL: cheaper model for routing/filtering steps


def _load_env():
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT_DIR / ".env")
    except ImportError:
        pass


def create_llm(model, base_url, temperature=0.0, format=None):
    """`base_url: env` uses the OpenAI-compatible gateway from .env (e.g. Metis DeepSeek);
    any other URL is an Ollama server. `model: env` takes the model name from LLM_MODEL,
    `model: env_fast` from LLM_FAST_MODEL (falls back to LLM_MODEL)."""
    if base_url == ENV_MARKER or model in (ENV_MARKER, ENV_FAST_MARKER):
        _load_env()
        from langchain_openai import ChatOpenAI

        api_key = os.environ.get("LLM_API_KEY")
        if not api_key:
            raise RuntimeError("LLM_API_KEY is not set (see .env.example)")
        kwargs = {}
        if format == "json":
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        if model == ENV_FAST_MARKER:
            model = os.environ.get("LLM_FAST_MODEL") or os.environ.get("LLM_MODEL", "deepseek-v4-flash")
        elif model == ENV_MARKER:
            model = os.environ.get("LLM_MODEL", "deepseek-v4-flash")
        return ChatOpenAI(
            model=model,
            base_url=os.environ.get("LLM_BASE_URL") if base_url == ENV_MARKER else base_url,
            api_key=api_key,
            temperature=temperature,
            timeout=float(os.environ.get("LLM_TIMEOUT", "150")),
            max_retries=1,
            **kwargs,
        )

    from langchain_ollama import ChatOllama

    llm = ChatOllama(
        model=model,
        base_url=base_url,
        temperature=temperature,
        format=format
    )

    return llm
