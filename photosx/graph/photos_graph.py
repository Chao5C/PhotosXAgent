from langgraph.graph import END, START, StateGraph

from photosx.agents.recommend_agent import run_recommend_agent
from photosx.agents.vision_agent import run_vision_agent
from photosx.graph.state import PhotoAgentState


def build_photo_graph():
    graph = StateGraph(PhotoAgentState)
    graph.add_node("agent1_vision", run_vision_agent)
    graph.add_node("agent2_recommend", run_recommend_agent)
    graph.add_edge(START, "agent1_vision")
    graph.add_edge("agent1_vision", "agent2_recommend")
    graph.add_edge("agent2_recommend", END)
    return graph.compile()


photo_graph = build_photo_graph()
