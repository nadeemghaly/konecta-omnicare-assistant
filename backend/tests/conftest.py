"""Test fixtures.

Every fixture here is offline. The suite copies `data/` into a tmpdir so that
tests which append claims cannot mutate the repository's mock data, and builds the
index with the lexical embedder so no API key is needed.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.agent.service import AssistantService
from app.config import Settings, get_settings
from app.llm.fake import ScriptedChatModel
from app.rag.store import PolicyIndex

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Isolated settings over a throwaway copy of the mock data."""
    data_dir = tmp_path / "data"
    shutil.copytree(REPO_ROOT / "data", data_dir)

    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / ".chroma"))
    get_settings.cache_clear()

    return Settings(
        llm_provider="fake", data_dir=data_dir, chroma_dir=tmp_path / ".chroma"
    )


@pytest.fixture
def index(settings: Settings) -> PolicyIndex:
    policy_index = PolicyIndex(settings)
    policy_index.ingest()
    return policy_index


@pytest.fixture
def service(settings: Settings, index: PolicyIndex) -> AssistantService:
    return AssistantService(settings, index=index)


def script(service: AssistantService, *responses: AIMessage) -> ScriptedChatModel:
    """Point a service at a scripted model. Returns it for call inspection."""
    model = ScriptedChatModel(list(responses))
    service._model = model  # noqa: SLF001 - the injection seam exists for this
    return model


def tool_call(name: str, call_id: str = "call_1", **args) -> AIMessage:
    """An AIMessage requesting one tool call."""
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """TestClient with the real lifespan, so index ingest is exercised too."""
    from app.main import app

    get_settings.cache_clear()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()
