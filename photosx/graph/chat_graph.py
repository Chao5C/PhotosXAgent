from photosx.agents.assistant_agent import run_assistant_agent
from photosx.graph.state import ChatAgentState
from langgraph.graph import END, START, StateGraph


def build_chat_graph():
    graph = StateGraph(ChatAgentState)
    graph.add_node("agent3_assistant", run_assistant_agent)
    graph.add_edge(START, "agent3_assistant")
    graph.add_edge("agent3_assistant", END)
    return graph.compile()


chat_graph = build_chat_graph()
