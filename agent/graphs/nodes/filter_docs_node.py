from typing import List

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from agent.graphs.models import create_llm
from agent.graphs.nodes.prompt_loader import load_prompt_file

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

    prompt_data = load_prompt_file("filter_docs_node.yaml")

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
        related_result = relevancy_check_chain.batch(tasks, return_exceptions=True)
        normalized_results = []
        for i, result in enumerate(related_result):
            if isinstance(result, Exception):
                normalized_results.append(Result(items=[ResultItem(isRelevant=True)] * len(batches[i])))
                continue
            # A short/long model response must not silently drop or misalign documents.
            items = list(result.items[: len(batches[i])])
            items.extend(ResultItem(isRelevant=True) for _ in range(len(batches[i]) - len(items)))
            normalized_results.append(Result(items=items))
        related_result = normalized_results
        attempts = int(state.get("attempts", 0)) + 1
        filtered_docs = []
        for ti, task_result in enumerate(related_result):
            # Keep the Document objects so metadata (e.g. job links) reaches the API.
            task_data = batches[ti]
            for index, item in enumerate(task_result.items):
                if index >= len(task_data):
                    break
                if item.isRelevant:
                    filtered_docs.append(task_data[index])

        return {
            "documents": filtered_docs,
            "attempts": attempts,
            "debug_info": [
                {
                    "node_name": "filter_docs_node",
                    "output": filtered_docs,
                    "metadata": [
                        {"key": "attempts", "value": attempts}
                    ],
                }
            ],
        }

    return filter_docs_node
