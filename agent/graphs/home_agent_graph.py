import operator

import yaml
from langchain.messages import AnyMessage, HumanMessage
from langchain_core.documents import Document
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from typing_extensions import Annotated
from yaml.loader import SafeLoader

from agent.graphs.nodes import (
    create_coordinator_router_node,
    create_fallback_node,
    create_filter_docs_node,
    create_generate_with_context_node,
    create_home_retrieve_node,
)
from agent.graphs.states import BaseAgentState

# Nodes
COORDINATOR_ROUTER = "coordinator_router"
RETRIEVE = "retrieve"
FALLBACK = "fallback"
GENERATE_WITH_CONTEXT = "generate_with_context"
FILTER_DOCS = "filter_docs"


class AgentState(BaseAgentState):
    route: str
    query: str
    messages: Annotated[list[AnyMessage], operator.add]
    generation: str
    documents: list[Document]
    attempts: int
    filters: dict
    results: list[dict]
    understood: list[str]
    relaxed: list[str]
    retrieval_note: str


class HomeAgentGraph:
    """Conversational home-buying assistant («خونه‌یاب»):

    route -> retrieve (Divar listings; filters persist per thread) -> filter listings -> answer | fallback
    """

    def __init__(self, config, load_listings=None):
        checkpointer = InMemorySaver()

        coordinator_router_node = create_coordinator_router_node(config["coordinator_router"]["model"])

        if load_listings is None:
            from agent.home_search.listings import load_listings
        retriever_conf = config["retriever"]
        retrieve_node = create_home_retrieve_node(load_listings, retriever_conf.get("top_k", 8))

        fallback_conf = config["fallback"]
        fallback_node = create_fallback_node(fallback_conf["model"], fallback_conf["interactive"])

        generate_with_context_conf = config["generate_with_context"]
        generate_with_context_node = create_generate_with_context_node(
            generate_with_context_conf["model"],
            generate_with_context_conf["interactive"],
        )

        filter_docs_conf = config["filter_docs"]
        use_filter = filter_docs_conf.get("enable", True)

        builder = StateGraph(AgentState)
        builder.add_node(COORDINATOR_ROUTER, coordinator_router_node)
        builder.add_node(RETRIEVE, retrieve_node)
        builder.add_node(FALLBACK, fallback_node)
        builder.add_node(GENERATE_WITH_CONTEXT, generate_with_context_node)

        builder.set_entry_point(COORDINATOR_ROUTER)

        builder.add_conditional_edges(
            COORDINATOR_ROUTER,
            lambda x: x["route"],
            {"LLMFallback": FALLBACK, "VectorStore": RETRIEVE},
        )

        last = RETRIEVE
        if use_filter:
            builder.add_node(
                FILTER_DOCS,
                create_filter_docs_node(filter_docs_conf["model"], filter_docs_conf["batch_size"]),
            )
            builder.add_edge(RETRIEVE, FILTER_DOCS)
            last = FILTER_DOCS

        builder.add_conditional_edges(
            last,
            self._should_continue,
            {"FallBack": FALLBACK, "Generate": GENERATE_WITH_CONTEXT},
        )

        builder.add_edge(GENERATE_WITH_CONTEXT, END)
        builder.add_edge(FALLBACK, END)

        self._agent = builder.compile(checkpointer=checkpointer)

    def _should_continue(self, state):
        if len(state.get("documents", [])) == 0:
            return "FallBack"
        return "Generate"

    def close(self):
        pass

    def reset_thread(self, thread_id: str) -> None:
        """Forget one conversation from the in-process checkpointer."""
        self._agent.checkpointer.delete_thread(thread_id)

    def process_message(self, message: str, user_id: str, thread_id: str, sp=False):
        messages = [HumanMessage(content=message)]
        state = self._agent.invoke(
            {"messages": messages, "query": message},
            {
                "configurable": {
                    "user_id": user_id,
                    "thread_id": thread_id,
                }
            },
        )

        if sp:
            for m in state.get("messages", []):
                m.pretty_print()

        generation = state.get("generation")
        content = "⚠️ No answer generated."
        if generation is not None:
            content = getattr(generation, "content", generation)

        documents = state.get("documents", [])
        debug_info = state.get("debug_info", [])
        # Listings dropped by the LLM filter are not returned as cards either.
        kept = {d.metadata.get("listing_id") for d in documents}
        results = [r for r in state.get("results", []) if r["id"] in kept]

        return {
            "content": content,
            "documents": documents,
            "debug_info": debug_info,
            "results": results,
            "filters": state.get("filters"),
            "understood": state.get("understood", []),
            "relaxed": state.get("relaxed", []),
        }


if __name__ == "__main__":
    args = None
    with open("configs/home_agent_graph.yaml", "rb") as config_file:
        args = yaml.load(config_file, Loader=SafeLoader)

    graph = HomeAgentGraph(args)

    graph.process_message("آپارتمان دو خواب در تهران تا ۸ میلیارد با پارکینگ", "1", "1", True)
