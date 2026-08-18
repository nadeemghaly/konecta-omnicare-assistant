"""A scripted chat model, for tests that must not touch the network.

`gemini-3.6-flash` ignores `temperature`, so there is no way to make the real
model deterministic. Asserting "did the agent call get_claim_status?" against a
live thinking model is therefore inherently flaky. This model makes the graph's
control flow exactly testable; the `live`-marked tests cover the real thing.
"""

from __future__ import annotations

from typing import Any, Sequence

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ScriptedChatModel(BaseChatModel):
    """Replays a fixed list of AIMessages, one per invocation.

    Pass `responses` to script a tool-calling sequence, e.g. an AIMessage with
    `tool_calls` followed by an AIMessage with the final prose. Once the script
    is exhausted the last entry repeats, so a graph that loops more than
    expected fails on assertions rather than on IndexError.
    """

    responses: list[AIMessage] = []
    calls: list[list[BaseMessage]] = []

    def __init__(self, responses: Sequence[AIMessage] | None = None, **kwargs: Any):
        super().__init__(**kwargs)
        self.responses = list(responses) if responses else [AIMessage(content="ok")]
        self.calls = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return ChatResult(generations=[ChatGeneration(message=self.responses[index])])

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedChatModel":
        # Tool schemas are irrelevant to a scripted model, but the graph binds
        # them unconditionally -- so accept and ignore.
        return self
