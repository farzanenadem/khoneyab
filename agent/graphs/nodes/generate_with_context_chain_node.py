from pathlib import Path

import yaml
from yaml.loader import SafeLoader
from langchain_core.prompts import ChatPromptTemplate

from agent.graphs.models import create_llm
from agent.graphs.nodes.context_rules import create_general_context_prompt


def create_generate_with_context_node(model_conf, interactive=False):

    yaml_path = (
        Path(__file__).resolve().parent.parent.parent
        / "agent_jobs"
        / "prompts"
        / "generate_with_context_chain_node.yaml"
    )
    with open(yaml_path, "r", encoding="utf-8") as f:
        prompt_data = yaml.load(f, Loader=SafeLoader)

    section = (
        prompt_data["interactive"] if interactive else prompt_data["non_interactive"]
    )

    messages = [
        ("system", section["system"]),
        ("user", section["user"]),
    ]

    generate_with_context_prompt = ChatPromptTemplate.from_messages(messages)
    llm = create_llm(model_conf["name"], model_conf["url"])

    generate_with_context_chain = generate_with_context_prompt | llm
    general_context = create_general_context_prompt()

    def generate_with_context_node(state: dict):
        query = state["query"]
        documents = state["documents"]
        generation = generate_with_context_chain.invoke(
            {
                "query": query,
                "general_context": general_context,
                "context": documents,
            }
        )

        return {
            "generation": generation,
            "messages": [generation],
            "debug_info": [
                {
                    "node_name": "generate_with_context_node",
                    "output": generation,
                    "metadata": [],
                }
            ],
        }

    return generate_with_context_node
