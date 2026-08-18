"""Model-provider seam.

One factory returns a LangChain chat model, so the agent graph is written once
and never learns which vendor is behind it. This is the same seam the hermetic
test suite injects a scripted model into -- the abstraction that gives us a
backup provider is the abstraction that makes tests offline-capable.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel

from ..config import Settings, get_settings


def build_chat_model(settings: Settings | None = None) -> BaseChatModel:
    """Construct the configured chat model.

    Providers are imported lazily so that running with one vendor does not
    require the other's SDK to be installed or its key to be present.
    """
    settings = settings or get_settings()

    if settings.llm_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not settings.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Get a free key at "
                "https://aistudio.google.com/apikey, or set LLM_PROVIDER=openai_compat "
                "to use the backup provider."
            )
        # Note: gemini-3.x models use fixed sampling defaults and ignore
        # `temperature` -- passing it emits a warning and changes nothing, so we
        # do not pretend to control determinism here. Tests use the fake model.
        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
        )

    if settings.llm_provider == "openai_compat":
        from langchain_openai import ChatOpenAI

        if not settings.openai_api_key:
            raise RuntimeError(
                "LLM_PROVIDER=openai_compat but OPENAI_API_KEY is not set. "
                "This adapter also serves Groq and Ollama -- set OPENAI_BASE_URL "
                "accordingly (Ollama: http://localhost:11434/v1, any key value)."
            )
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
            temperature=0,
        )

    from .fake import ScriptedChatModel

    return ScriptedChatModel()


def message_text(content: Any) -> str:
    """Flatten LangChain message content to a plain string.

    Gemini 3.x returns a list of content blocks rather than a string --
    ``[{"type": "text", "text": "...", "extras": {"signature": "..."}}]``.
    Serialising that straight into our ``{"response": str}`` contract would leak
    Python reprs (and thought signatures) to the client, so every path out of the
    graph goes through here.
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                # Reasoning blocks carry no user-facing prose; skip them.
                if block.get("type") in {"thinking", "reasoning"}:
                    continue
                text = block.get("text")
                if isinstance(text, str) and text:
                    parts.append(text)
        return "\n".join(parts).strip()

    return str(content)
