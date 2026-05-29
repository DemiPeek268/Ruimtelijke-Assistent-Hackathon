from abc import ABC, abstractmethod

from langchain_core.callbacks import adispatch_custom_event
from langchain_core.runnables import RunnableConfig

from app.models.state import ConversationState


class BaseNode(ABC):
    """Abstract base class for all LangGraph workflow nodes.

    Handles status dispatching and error handling so that subclasses
    only need to implement their unique logic.
    """

    def __init__(self, step_name: str, *, auto_activate: bool = True):
        self.step_name = step_name
        self.auto_activate = auto_activate

    async def dispatch(self, name: str, data: dict, config: RunnableConfig) -> None:
        """Dispatch a custom event through LangGraph's event system."""
        await adispatch_custom_event(name, data, config=config)

    async def set_active(self, config: RunnableConfig) -> None:
        await self.dispatch(
            "status", {"step": self.step_name, "status": "active"}, config
        )

    async def __call__(self, state: ConversationState, config: RunnableConfig) -> dict:
        """Entry point called by LangGraph for this node."""
        if self.auto_activate:
            await self.set_active(config)
        try:
            return await self.run(state, config)
        except Exception as e:
            await self.dispatch(
                "error",
                {"message": f"Fout bij {self.step_name}: {e}"},
                config,
            )
            return self.fallback()

    @abstractmethod
    async def run(self, state: ConversationState, config: RunnableConfig) -> dict:
        """Implement the node's core logic. Returns a state update dict."""
        ...

    @abstractmethod
    def fallback(self) -> dict:
        """Return a safe default state update on error."""
        ...
