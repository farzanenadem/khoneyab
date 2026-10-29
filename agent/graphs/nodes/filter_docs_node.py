from pathlib import Path
from typing import List

import yaml
from yaml.loader import SafeLoader
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from agent.graphs.models import create_llm

class ResultItem(BaseModel):
    isRelevant: bool = Field(
        description="True if the document is relevant to the query, else False"
    )


class Result(BaseModel):
    items: List[ResultItem]


relevancy_parser = PydanticOutputParser(pydantic_object=Result)


def chunk_items(items, chunk_size):
    for i in range(0, len(items), chunk_size):
        yield items[i : i + chunk_size]


def create_filter_docs_node(model_conf, batch_size):

    yaml_path = (
        Path(__file__).resolve().parent.parent.parent
        / "agent_jobs"
        / "prompts"
        / "filter_docs_node.yaml"
    )
    with open(yaml_path, "r", encoding="utf-8") as f:
        prompt_data = yaml.load(f, Loader=SafeLoader)

    relevancy_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", prompt_data["system"]),
            ("user", prompt_data["user"]),
        ]
    )

    llm = create_llm(model_conf["name"], model_conf["url"], 0, "json")

    relevancy_check_chain = relevancy_prompt | llm | relevancy_parser

    def filter_docs_node(state: dict):
        query = state["query"]
        documents = state["documents"]

        tasks, batches = [], []
        for batch in chunk_items(documents, batch_size):
            batches.append(batch)
            tasks.append(
                {
                    "query": query,
                    "documents": [doc.page_content for doc in batch],
                    "output_instructions": relevancy_parser.get_format_instructions(),
                }
            )

        # A malformed model reply must not fail the request: keep that batch unfiltered.
        releated_result = relevancy_check_chain.batch(tasks, return_exceptions=True)
        releated_result = [
            Result(items=[ResultItem(isRelevant=True)] * len(batches[i]))
            if isinstance(r, Exception)
            else r
            for i, r in enumerate(releated_result)
        ]
        filtered_docs = []
        for ti, task_result in enumerate(releated_result):
            # Keep the Document objects so metadata (e.g. job links) reaches the API.
            task_data = batches[ti]
            for index, item in enumerate(task_result.items):
                if index >= len(task_data):
                    break
                if item.isRelevant:
                    filtered_docs.append(task_data[index])

        return {
            "documents": filtered_docs,
            "attempts": state.get("attempts") + 1,
            "debug_info": [
                {
                    "node_name": "filter_docs_node",
                    "output": filtered_docs,
                    "metadata": [
                        {"key": "attempts", "value": state.get("attempts") + 1}
                    ],
                }
            ],
        }

    return filter_docs_node
