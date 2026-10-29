from pathlib import Path

import yaml
from yaml.loader import SafeLoader
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from agent.graphs.models import create_llm
import re


def create_rewrite_followup_node(model_conf):
    yaml_path = (
        Path(__file__).resolve().parent.parent.parent
        / "agent_jobs"
        / "prompts"
        / "rewrite_followup.yaml"
    )
    with open(yaml_path, "r", encoding="utf-8") as f:
        prompt_data = yaml.load(f, Loader=SafeLoader)

    rewrite_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", prompt_data["system"]),
            MessagesPlaceholder("messages"),
        ]
    )

    llm = create_llm(model_conf["name"], model_conf["url"])

    chain = rewrite_prompt | llm | StrOutputParser()

    def rewrite_node(state: dict):
        query = state.get("query", "")
        messages = state.get("messages", [])

        rewritten = chain.invoke({"query": query, "messages": messages})

        return {"query": rewritten}

    return rewrite_node
