from agent.graphs.nodes.prompt_loader import load_prompt_file, render_context_rules


def create_general_context_prompt():
    return render_context_rules(load_prompt_file("context_rules.yaml"))
