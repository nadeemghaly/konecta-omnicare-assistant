"""The agent as an explicit LangGraph state machine.

Written out rather than assembled by `create_agent`, for three reasons that all
matter here: the tool node records every invocation so `tool_calls` in the API
response is observed fact rather than a reconstruction; the loop is bounded, so a
model that keeps calling tools cannot spin forever; and the control flow is
readable, which is the whole argument for choosing LangGraph over an opaque
executor.

    START -> agent -> (tool_calls? ) -> tools -> agent -> ... -> END
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from ..rag.store import PolicyIndex
from ..schemas import Source, ToolCallRecord
from ..tools.claims import build_claim_tools
from ..tools.repository import ClaimsRepository, UserRepository
from .prompts import SYSTEM_PROMPT
from .safety import wrap_untrusted

logger = logging.getLogger(__name__)

# A coverage question plus a claim lookup is two tool rounds; four leaves room for
# a multi-step submission without letting a confused model loop indefinitely.
MAX_TOOL_ROUNDS = 4


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    rounds: int


@dataclass
class TurnContext:
    """Per-request accumulator for what the agent did.

    Sources and tool calls belong to *this* turn, not the conversation, so they
    live here rather than in checkpointed graph state -- which would otherwise
    replay a previous turn's citations onto a new answer.
    """

    sources: list[Source] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)

    def rendered_sources(self) -> list[str]:
        """Deduplicated, order-preserving citation strings for the API."""
        seen: set[str] = set()
        out: list[str] = []
        for source in self.sources:
            rendered = source.render()
            if rendered not in seen:
                seen.add(rendered)
                out.append(rendered)
        return out


def build_policy_search_tool(index: PolicyIndex, ctx: TurnContext) -> BaseTool:
    """The RAG tool.

    Retrieval is a tool rather than an always-on node so that `sources` is empty
    when no coverage question was asked -- attaching policy citations to "what's
    my claim status?" would be noise masquerading as rigour.
    """

    def search_policy(query: str) -> str:
        """Search the OmniCare policy document for coverage terms.

        Args:
            query: What to look for, e.g. "burst pipe water damage limit".
        """
        hits = index.search(query)
        if not hits:
            return "No matching policy text found."
        # Recorded here, at the moment of retrieval: the citation is therefore
        # exactly the text the answer was grounded in, not the model's account of it.
        ctx.sources.extend(hit.source for hit in hits)
        excerpts = "\n\n".join(
            f"[{hit.source.section}] {hit.source.quote}" for hit in hits
        )
        return wrap_untrusted(excerpts)

    return StructuredTool.from_function(
        func=search_policy,
        name="search_policy",
        description=(
            "Search the OmniCare policy document for coverage rules, limits, "
            "deductibles, and exclusions. Call this before answering any question "
            "about what is covered."
        ),
    )


def build_graph(
    model: BaseChatModel,
    tools: list[BaseTool],
    ctx: TurnContext,
    checkpointer: BaseCheckpointSaver,
):
    """Compile the agent graph for one request's toolset.

    The graph is rebuilt per request because tools close over the caller's
    identity, but the `checkpointer` is owned by the service and shared across
    requests -- a per-request saver would discard the conversation it exists to keep.
    """
    by_name = {tool.name: tool for tool in tools}
    model_with_tools = model.bind_tools(tools)

    async def agent_node(state: AgentState) -> dict[str, Any]:
        # Async, not sync: a blocking multi-second model call inside an async
        # graph would stall the event loop and serialise every other request.
        response = await model_with_tools.ainvoke(state["messages"])
        return {"messages": [response]}

    async def tools_node(state: AgentState) -> dict[str, Any]:
        last = state["messages"][-1]
        messages: list[BaseMessage] = []

        for call in getattr(last, "tool_calls", []) or []:
            tool = by_name.get(call["name"])
            if tool is None:
                result, ok = f"Unknown tool {call['name']!r}.", False
            else:
                try:
                    result, ok = await tool.ainvoke(call["args"]), True
                except Exception as exc:  # noqa: BLE001 - surfaced to the model as text
                    logger.exception("tool %s failed", call["name"])
                    result, ok = f"That tool failed: {exc}", False

            ctx.tool_calls.append(
                ToolCallRecord(
                    name=call["name"], args=dict(call["args"]), ok=ok, result=str(result)
                )
            )
            messages.append(
                ToolMessage(
                    content=str(result), tool_call_id=call["id"], name=call["name"]
                )
            )

        return {"messages": messages, "rounds": state.get("rounds", 0) + 1}

    def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
        last = state["messages"][-1]
        wants_tools = isinstance(last, AIMessage) and bool(last.tool_calls)
        if wants_tools and state.get("rounds", 0) >= MAX_TOOL_ROUNDS:
            logger.warning("tool round limit reached; ending turn")
            return END
        return "tools" if wants_tools else END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    # Conversation continuity is per-Policyholder: the service passes
    # thread_id=user_id, so "my other claim" resolves across turns and never
    # leaks between users.
    return graph.compile(checkpointer=checkpointer)


def build_system_message(user_id: str, display_name: str | None) -> SystemMessage:
    return SystemMessage(
        content=SYSTEM_PROMPT.format(
            user_id=user_id, display_name=display_name or "a valued policyholder"
        )
    )


def build_tools(
    user_id: str,
    index: PolicyIndex,
    claims: ClaimsRepository,
    users: UserRepository,
    ctx: TurnContext,
) -> list[BaseTool]:
    return [
        build_policy_search_tool(index, ctx),
        *build_claim_tools(user_id, claims, users),
    ]
