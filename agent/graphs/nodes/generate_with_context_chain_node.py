from langchain_core.prompts import ChatPromptTemplate

from agent.graphs.models import create_llm
from agent.graphs.nodes.context_rules import create_general_context_prompt
from agent.graphs.nodes.prompt_loader import load_prompt_file


def _render_documents(documents) -> str:
    """Expose only numbered source text to the model, never Python object reprs."""
    return "\n\n".join(
        f"[آگهی {index}]\n{document.page_content[:1800]}"
        for index, document in enumerate(documents, 1)
    ) or "(هیچ آگهی‌ای پیدا نشد)"


def create_generate_with_context_node(model_conf, interactive=False):

    prompt_data = load_prompt_file("generate_with_context_chain_node.yaml")

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
                "context": _render_documents(documents),
                "retrieval_note": state.get("retrieval_note", ""),
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
