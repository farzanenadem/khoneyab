from operator import itemgetter
from langchain_core.prompts import ChatPromptTemplate

from agent.graphs.models import create_llm
from agent.graphs.nodes.prompt_loader import load_prompt_file


def create_fallback_node(model_conf, interactive=False):

    prompt_data = load_prompt_file("fallback_chain_node.yaml")

    section = (
        prompt_data["interactive"] if interactive else prompt_data["non_interactive"]
    )

    fallback_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", section["system"]),
            ("human", section["human"]),
        ]
    )

    llm = create_llm(model_conf["name"], model_conf["url"])

    fallback_chain = (
        {
            "messages": itemgetter("messages"),
            "query": itemgetter("query"),
        }
        | fallback_prompt
        | llm
    )

    def fallback_node(state: dict):
        """
        Fallback to this node when there is no tool call
        """
        query = state["query"]
        messages = state["messages"]

        generation = fallback_chain.invoke({"query": query, "messages": messages})

        return {"generation": generation, "messages": [generation]}

    return fallback_node
