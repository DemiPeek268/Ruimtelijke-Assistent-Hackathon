from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig

from app.models.dictionary import DataDictionary
from app.models.state import ConversationState, Intent, IntentAnalysis
from app.models.validation import InvalidFilter
from app.services.helpers.db import connect_delta
from app.services.helpers.filter_candidates import build_fallback_question
from app.services.helpers.filter_validation import collect_invalid_filters
from app.services.helpers.prompt_helpers import format_intent_section, load_prompt
from app.services.helpers.tables import register_tables
from app.services.llm import make_llm
from app.services.nodes.base import BaseNode


class ValidateFiltersNode(BaseNode):
    """Validate categorical filter values against the database.

    Validates filters in hierarchy order (gemeente → wijk → buurt → other).
    Each filter is scoped to already-validated parent filters so candidates
    and existence checks are contextually accurate.
    """

    _CORRECTION_PROMPT = ChatPromptTemplate.from_messages(
        [("system", load_prompt("02_filter_correction.md"))],
        template_format="jinja2",
    )

    def __init__(self):
        super().__init__("validatie")

    async def run(self, state: ConversationState, config: RunnableConfig) -> dict:
        """Validate categorical filter values and attempt automatic correction.

        Validates both regular filters and spatial_query.origin_filters.
        The two sets are validated independently so that combination checks
        don't fail across unrelated areas (e.g. origin=Delft, filter=Rotterdam).
        """
        intent_analysis = state["intent_analysis"]
        intent = intent_analysis.intent
        categorical_pairs = self._get_categorical_columns(state["dictionary"])

        def is_categorical(f) -> bool:
            return (f.table, f.column) in categorical_pairs or (
                # Tolerate missing table from the LLM: match on column only.
                f.table is None and any(c == f.column for _, c in categorical_pairs)
            )

        categorical_filters = [f for f in intent.filters if is_categorical(f)]
        origin_filters = self._get_origin_categorical_filters(intent, is_categorical)

        if not categorical_filters and not origin_filters:
            await self.dispatch(
                "step_thinking_summary",
                {
                    "step_id": "validatie",
                    "summary": "Geen filterwaarden om te controleren.",
                },
                config,
            )
            return {}

        invalid = self._validate_all(categorical_filters, origin_filters)
        if not invalid:
            await self.dispatch(
                "step_thinking_summary",
                {"step_id": "validatie", "summary": "Alle filterwaarden zijn correct."},
                config,
            )
            return {}

        corrected = await self._correct_filters(
            state["model"], intent, invalid, is_final_attempt=False, config=config
        )

        if not corrected.is_clear:
            await self.dispatch(
                "follow_up_text", {"content": corrected.follow_up_question}, config
            )
            return {"intent_analysis": corrected}

        corrected_categorical = [
            f for f in corrected.intent.filters if is_categorical(f)
        ]
        corrected_origin = self._get_origin_categorical_filters(
            corrected.intent, is_categorical
        )
        still_invalid = self._validate_all(corrected_categorical, corrected_origin)

        if not still_invalid:
            return {"intent_analysis": corrected}

        final = await self._correct_filters(
            state["model"],
            corrected.intent,
            still_invalid,
            is_final_attempt=True,
            config=config,
        )

        if final.is_clear:
            final.is_clear = False
            if not final.follow_up_question:
                final.follow_up_question = build_fallback_question(still_invalid)

        await self.dispatch(
            "follow_up_text", {"content": final.follow_up_question}, config
        )
        return {"intent_analysis": final}

    # ------------------------------------------------------------------
    # DB validation
    # ------------------------------------------------------------------

    def _validate_all(
        self,
        categorical_filters: list,
        origin_filters: list,
    ) -> list[InvalidFilter]:
        """Validate regular and origin filters independently, then combine results.

        The two sets are validated separately so that combination checks
        don't cross-contaminate (e.g. origin=Delft + filter=Rotterdam).
        Origin invalids are tagged with source="spatial_origin".
        """
        with connect_delta() as con:
            register_tables(con)
            invalid_regular = (
                collect_invalid_filters(con, categorical_filters)
                if categorical_filters
                else []
            )
            invalid_origin = (
                collect_invalid_filters(con, origin_filters) if origin_filters else []
            )

        for inv in invalid_origin:
            inv.source = "spatial_origin"

        return invalid_regular + invalid_origin

    # ------------------------------------------------------------------
    # LLM correction
    # ------------------------------------------------------------------

    async def _correct_filters(
        self,
        model: str,
        intent: Intent,
        invalid_filters: list[InvalidFilter],
        *,
        is_final_attempt: bool,
        config: RunnableConfig,
    ) -> IntentAnalysis:
        """Call the correction LLM to resolve invalid filter values."""
        chain = self._CORRECTION_PROMPT | make_llm(
            model, streaming=False
        ).with_structured_output(IntentAnalysis)
        result: IntentAnalysis = await chain.ainvoke(
            {
                "intent_text": format_intent_section(intent),
                "invalid_filters": [f.model_dump() for f in invalid_filters],
                "is_final_attempt": is_final_attempt,
            },
        )

        await self.dispatch(
            "step_thinking_summary",
            {"step_id": "validatie", "summary": result.thinking_summary},
            config,
        )

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def fallback(self) -> dict:
        """Return an empty state update so an unexpected error leaves intent unchanged."""
        return {}

    @staticmethod
    def _get_origin_categorical_filters(intent: Intent, is_categorical) -> list:
        """Extract categorical filters from spatial_query.origin_filters."""
        if not intent.spatial_query:
            return []
        return [f for f in intent.spatial_query.origin_filters if is_categorical(f)]

    @staticmethod
    def _get_categorical_columns(dictionary: DataDictionary) -> set[tuple[str, str]]:
        """Return the set of (table, column) pairs marked as categorical."""
        return {
            (col.table, col.name) for col in dictionary.all_columns() if col.categorical
        }
