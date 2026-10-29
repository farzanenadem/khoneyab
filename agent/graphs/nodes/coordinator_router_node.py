from pathlib import Path
import yaml
from yaml.loader import SafeLoader
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from agent.graphs.models import create_llm
from agent.utilities.chosentool import ChosenTool
from agent.graphs.nodes.context_rules import create_general_context_prompt 


def create_coordinator_router_node(model_conf):
    yaml_path = (
        Path(__file__).resolve().parent.parent.parent
        / "agent_jobs"
        / "prompts"
        / "coordinator_router.yaml"
    )
    with open(yaml_path, "r", encoding="utf-8") as f:
        prompt_data = yaml.load(f, Loader=SafeLoader)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                prompt_data["system"],
            ),
            ("human", prompt_data["human"]),
        ]
    )

    question_router_parser = PydanticOutputParser(pydantic_object=ChosenTool)

    llm = create_llm(model_conf["name"], model_conf["url"])

    question_router = prompt | llm | question_router_parser
    general_context = create_general_context_prompt()

    def coordinator_router_node(state: dict):
        query = state["query"]
        messages = state.get("messages", [])
        try:
            response = question_router.invoke(
                {
                    "query": query,
                    "messages": messages,
                    "general_context": general_context,
                    "output_instructions": question_router_parser.get_format_instructions(),
                }
            )
        except Exception:
            return {"route": "VectorStore"}
        try:
            chosen_tool = response.tool_name.lower()
        except Exception:
            return {"route": "VectorStore"}

        # Unrelated messages get the fallback; anything else (including parse errors) searches.
        if chosen_tool == "none":
            return {"route": "LLMFallback"}

        return {"route": "VectorStore"}

    return coordinator_router_node
