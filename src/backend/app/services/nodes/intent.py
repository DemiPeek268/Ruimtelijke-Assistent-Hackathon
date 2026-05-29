import logging
from difflib import get_close_matches

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig

from app.models.dictionary import DataDictionary
from app.models.state import ConversationState, IntentAnalysis
from app.services.helpers.messages import to_langchain_history
from app.services.helpers.prompt_helpers import load_prompt
from app.services.llm import make_llm
from app.services.nodes.base import BaseNode

logger = logging.getLogger(__name__)


def _get_valid_column_names(dictionary: DataDictionary) -> set[str]:
    return {col.name for col in dictionary.all_columns()}


def _column_to_tables(dictionary: DataDictionary) -> dict[str, list[str]]:
    """Map column name → list of tables that contain that column."""
    out: dict[str, list[str]] = {}
    for table in dictionary.all_tables():
        for col in table.columns:
            out.setdefault(col.name, []).append(table.name)
    return out


def _correct_column_names(columns: list[str], valid_names: set[str]) -> list[str]:
    corrected = []
    for col in columns:
        if col in valid_names:
            corrected.append(col)
            continue
        matches = get_close_matches(col, valid_names, n=1, cutoff=0.6)
        if matches:
            logger.info("Corrected column name: %s -> %s", col, matches[0])
            corrected.append(matches[0])
        else:
            logger.warning("No match found for column: %s (dropped)", col)
    return corrected


class IntentNode(BaseNode):
    """Analyse the user's intent and determine if it is clear enough for SQL generation."""

    _PROMPT = ChatPromptTemplate.from_messages(
        [
            ("system", load_prompt("01_intent_analyzer.md")),
            MessagesPlaceholder("history"),
        ],
        template_format="jinja2",
    )

    def __init__(self):
        super().__init__("intentie")

    async def run(self, state: ConversationState, config: RunnableConfig) -> dict:
        chain = self._PROMPT | make_llm(
            state["model"], streaming=False
        ).with_structured_output(IntentAnalysis)
        result: IntentAnalysis = await chain.ainvoke(
            {
                "themes": state["dictionary"].themes,
                "history": to_langchain_history(state["messages"]),
            },
        )

        await self.dispatch(
            "step_thinking_summary",
            {"step_id": "intentie", "summary": result.thinking_summary},
            config,
        )

        # Correct hallucinated column names against the actual dictionary, and
        # fill in `table` on any filter where the LLM left it blank.
        if result.is_clear and result.intent:
            dictionary = state["dictionary"]
            valid_names = _get_valid_column_names(dictionary)
            col_to_tables = _column_to_tables(dictionary)
            result.intent.relevant_columns = _correct_column_names(
                result.intent.relevant_columns, valid_names
            )
            for f in result.intent.filters:
                if f.column == "h3_spatial_filter":
                    continue
                corrected = _correct_column_names([f.column], valid_names)
                if corrected:
                    f.column = corrected[0]
                if not f.table:
                    tables = col_to_tables.get(f.column, [])
                    if tables:
                        f.table = tables[0]

        if not result.is_clear:
            await self.dispatch(
                "follow_up_text", {"content": result.follow_up_question}, config
            )

        return {
            "intent_analysis": result,
            "needs_spatial_resolution": self._needs_spatial_resolution(result),
            "pdok_used": False,
        }

    @staticmethod
    def _needs_spatial_resolution(result: IntentAnalysis) -> bool:
        intent = result.intent if result.is_clear else None
        if not intent or not intent.spatial_query:
            return False
        return any(
            origin_filter.column == "h3_spatial_filter"
            and not origin_filter.value.startswith("LATLON:")
            for origin_filter in intent.spatial_query.origin_filters
        )

    def fallback(self) -> dict:
        return {
            "intent_analysis": None,
            "needs_spatial_resolution": False,
            "pdok_used": False,
        }
