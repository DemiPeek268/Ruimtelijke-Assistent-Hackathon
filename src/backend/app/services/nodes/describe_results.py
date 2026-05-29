from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig

from app.models.dictionary import DataDictionary
from app.models.state import ConversationState
from app.services.helpers.prompt_helpers import format_results_section, load_prompt
from app.services.llm import make_llm
from app.services.nodes.base import BaseNode


def _columns_block(dictionary: DataDictionary, names: list[str]) -> str:
    """Render description blocks (table-grouped) for the named columns.

    Used by describe_results and plan_visualization to give the LLM context on
    just the columns present in the query result, without re-using the
    legacy `build_columns_text` helper.
    """
    wanted = set(names)
    sections: list[str] = []
    for table in dictionary.all_tables():
        cols = [c for c in table.columns if c.name in wanted]
        if not cols:
            continue
        lines = [f"### {table.name}"]
        for c in cols:
            parts = [f"- {c.name} ({c.type})"]
            if c.unit:
                parts.append(f"[{c.unit}]")
            if c.description:
                parts.append(f": {c.description}")
            if c.min is not None and c.max is not None:
                parts.append(f". Range: {c.min}-{c.max}")
            lines.append(" ".join(parts))
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


class DescribeResultsNode(BaseNode):
    """Generate a data-aware Dutch description using actual query results.

    Always runs — on errors or empty results the LLM explains what happened.
    Streams the response so the user sees text arriving in real-time.
    """

    _PROMPT = ChatPromptTemplate.from_messages(
        [("system", load_prompt("05_result_describer.md"))],
        template_format="jinja2",
    )

    def __init__(self):
        super().__init__("beschrijving", auto_activate=True)

    def _build_context(self, state: ConversationState) -> dict:
        qr = state.get("query_result")
        sample = qr.sample if qr else None
        return {
            "description": state["intent_analysis"].intent.description,
            "sql_query": state.get("sql_query"),
            "map_plan": state.get("map_plan"),
            "limit": state["intent_analysis"].intent.limit,
            "year_comparison": state["intent_analysis"].intent.year_comparison,
            "col_metadata": _columns_block(
                state["dictionary"],
                list(sample[0].keys()) if sample else [],
            ),
            "results_section": format_results_section(
                sample,
                qr.count if qr else None,
                qr.summary if qr else None,
                qr.error if qr else None,
            ),
        }

    async def run(self, state: ConversationState, config: RunnableConfig) -> dict:
        chain = self._PROMPT | make_llm(state["model"], streaming=True)
        response = await chain.ainvoke(self._build_context(state))
        return {"explanation": response.content}

    def fallback(self) -> dict:
        return {"explanation": None}
