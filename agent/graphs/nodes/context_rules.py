from pathlib import Path

import yaml
from yaml.loader import SafeLoader


def create_general_context_prompt():
    yaml_path = (
        Path(__file__).resolve().parent.parent.parent
        / "agent_jobs"
        / "prompts"
        / "context_rules.yaml"
    )

    with open(yaml_path, "r", encoding="utf-8") as f:
        general_context = yaml.load(f, Loader=SafeLoader)

    return general_context
