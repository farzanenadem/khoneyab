"""Shared, validated loading for home-assistant prompt files."""

from pathlib import Path
from typing import Any

import yaml
from yaml.loader import SafeLoader


PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "agent_homes" / "prompts"


def load_prompt_file(name: str) -> dict[str, Any]:
    """Load one YAML prompt and fail early when the file is malformed."""
    path = PROMPTS_DIR / name
    with path.open("r", encoding="utf-8") as file:
        data = yaml.load(file, Loader=SafeLoader)
    if not isinstance(data, dict):
        raise ValueError(f"Prompt {name!r} must contain a YAML mapping")
    return data


def render_context_rules(data: dict[str, Any]) -> str:
    """Render policy plus bullet rules into deterministic prompt text."""
    policy = str(data.get("policy", "")).strip()
    rules = data.get("rules", [])
    if not isinstance(rules, list) or not all(isinstance(rule, str) for rule in rules):
        raise ValueError("context_rules.yaml rules must be a list of strings")
    bullets = "\n".join(f"- {rule.strip()}" for rule in rules if rule.strip())
    return "\n\n".join(part for part in (policy, bullets) if part)
