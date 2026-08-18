"""Application service: one turn of conversation, end to end.

Owns the objects that must outlive a request -- the policy index, the repositories,
the chat model, and the conversation checkpointer -- and assembles the per-request
pieces (identity-bound tools, turn context) around them.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from ..config import Settings, get_settings
from ..llm.base import build_chat_model, message_text
from ..llm.errors import RateLimited, classify
from ..rag.store import PolicyIndex
from ..schemas import ChatResponse
from ..tools.repository import ClaimsRepository, UserRepository
from . import safety
from .graph import TurnContext, build_graph, build_system_message, build_tools

logger = logging.getLogger(__name__)


class UnknownPolicyholder(Exception):
    """The user_id is well-formed but not on file."""


class AssistantService:
    def __init__(self, settings: Settings | None = None, index: PolicyIndex | None = None):
        self._settings = settings or get_settings()
        self.index = index or PolicyIndex(self._settings)
        self.claims = ClaimsRepository(self._settings)
        self.users = UserRepository(self._settings)
        self._model = build_chat_model(self._settings)
        # Shared across requests: this is what makes a Conversation a conversation.
        self._checkpointer = MemorySaver()

    async def answer(self, user_id: str, message: str) -> ChatResponse:
        display_name = self.users.name_for(user_id)
        if display_name is None and not self.users.policies_for(user_id):
            raise UnknownPolicyholder(user_id)

        # Screened before the model is ever called: a blatant injection costs no
        # tokens, and the refusal keeps the response contract stable (HTTP 200,
        # empty sources and tool_calls) so the UI needs no special case.
        verdict = safety.screen(message)
        if verdict.blocked:
            logger.warning(
                "injection attempt blocked: user=%s pattern=%s", user_id, verdict.pattern
            )
            return ChatResponse(
                response=safety.INJECTION_REFUSAL, sources=[], tool_calls=[]
            )

        ctx = TurnContext()
        tools = build_tools(user_id, self.index, self.claims, self.users, ctx)
        graph = build_graph(self._model, tools, ctx, self._checkpointer)
        config = {"configurable": {"thread_id": user_id}}

        # The system prompt is prepended only when the thread is new; on later
        # turns the checkpointer already holds it.
        existing = await graph.aget_state(config)
        turn: list = [] if existing.values.get("messages") else [
            build_system_message(user_id, display_name)
        ]
        turn.append(HumanMessage(content=message))

        try:
            state = await graph.ainvoke({"messages": turn, "rounds": 0}, config=config)
        except Exception as exc:  # noqa: BLE001 - re-raised after classification
            classified = classify(exc)
            if isinstance(classified, RateLimited):
                logger.warning(
                    "provider rate limited: user=%s retry_after=%ss",
                    user_id,
                    classified.retry_after,
                )
            raise classified from exc

        return ChatResponse(
            response=message_text(state["messages"][-1].content),
            sources=ctx.rendered_sources(),
            tool_calls=ctx.tool_calls,
        )
