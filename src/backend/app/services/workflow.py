from langgraph.graph import END, StateGraph

from app.models.state import ConversationState
from app.services.nodes.describe_results import DescribeResultsNode
from app.services.nodes.execute_query import ExecuteQueryNode
from app.services.nodes.intent import IntentNode
from app.services.nodes.plan_visualization import PlanVisualizationNode
from app.services.nodes.spatial import SpatialNode
from app.services.nodes.sql_generation import SqlGenerationNode
from app.services.nodes.validate_filters import ValidateFiltersNode


def route_after_intent(state: ConversationState) -> str:
    """Route naar spatial resolution of filtervalidatie als intentie duidelijk is."""
    analysis = state.get("intent_analysis")
    if not analysis or not analysis.is_clear:
        return END
    return (
        "resolve_spatial"
        if state.get("needs_spatial_resolution")
        else "validate_filters"
    )


def route_after_validation(state: ConversationState) -> str:
    """Route naar SQL-generatie als filters geldig zijn, anders stop."""
    analysis = state.get("intent_analysis")
    return "generate_sql" if analysis and analysis.is_clear else END


def create_workflow():
    """Bouw en compileer de LangGraph workflow."""
    graph = StateGraph(ConversationState)

    graph.add_node("check_intent", IntentNode())
    graph.add_node("resolve_spatial", SpatialNode())
    graph.add_node("validate_filters", ValidateFiltersNode())
    graph.add_node("generate_sql", SqlGenerationNode())
    graph.add_node("execute_query", ExecuteQueryNode())
    graph.add_node("plan_visualization", PlanVisualizationNode())
    graph.add_node("describe_results", DescribeResultsNode())

    graph.set_entry_point("check_intent")
    graph.add_conditional_edges(
        "check_intent",
        route_after_intent,
        {
            "resolve_spatial": "resolve_spatial",
            "validate_filters": "validate_filters",
            END: END,
        },
    )
    graph.add_edge("resolve_spatial", "validate_filters")
    graph.add_conditional_edges(
        "validate_filters",
        route_after_validation,
        {"generate_sql": "generate_sql", END: END},
    )
    graph.add_edge("generate_sql", "execute_query")
    graph.add_edge("execute_query", "plan_visualization")
    graph.add_edge("plan_visualization", "describe_results")
    graph.add_edge("describe_results", END)

    return graph.compile()


workflow = create_workflow()
