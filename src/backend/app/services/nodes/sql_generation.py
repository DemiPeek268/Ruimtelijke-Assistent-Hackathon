from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig

from app.models.state import ConversationState, SqlGenerationOutput
from app.services.helpers.prompt_helpers import format_intent_section, load_prompt
from app.services.llm import make_llm
from app.services.nodes.base import BaseNode


class SqlGenerationNode(BaseNode):
    """Generate a SQL query from the structured intent."""

    _PROMPT_DUCKDB = ChatPromptTemplate.from_messages(
        [("system", load_prompt("03_sql_generator.md"))],
        template_format="jinja2",
    )

    def __init__(self):
        super().__init__("sql")

    def _build_context(self, state: ConversationState) -> dict:
        intent = state["intent_analysis"].intent
        dictionary = state["dictionary"]
        return {
            "themes": dictionary.themes,
            "intent_section": format_intent_section(intent, for_sql=True),
        }

    async def run(self, state: ConversationState, config: RunnableConfig) -> dict:
        chain = self._PROMPT_DUCKDB | make_llm(
            state["model"], streaming=False
        ).with_structured_output(SqlGenerationOutput)
        parsed: SqlGenerationOutput = await chain.ainvoke(self._build_context(state))

        await self.dispatch(
            "step_thinking_summary",
            {"step_id": "sql", "summary": parsed.thinking_summary if parsed else ""},
            config,
        )

        sql_query = parsed.sql_query if parsed else None
        if sql_query:
            await self.dispatch("sql_block", {"query": sql_query}, config)

        return {"sql_query": sql_query}

    def fallback(self) -> dict:
        return {"sql_query": None}
