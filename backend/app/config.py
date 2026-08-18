"""Runtime configuration, sourced from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Model provider selection -------------------------------------------------
    # "gemini" is primary. "openai_compat" is the backup adapter and speaks to
    # OpenAI, Groq, and Ollama alike (they share the Chat Completions shape) --
    # point it at the right base_url. "fake" is deterministic, for tests.
    llm_provider: Literal["gemini", "openai_compat", "fake"] = "gemini"

    gemini_api_key: str = ""
    # Pinned rather than tracking `gemini-flash-latest`: an assessment should be
    # reproducible. Override here if the pin is ever retired.
    gemini_model: str = "gemini-3.6-flash"
    gemini_embedding_model: str = "gemini-embedding-001"

    # Backup provider. Defaults suit Groq's free tier; set base_url to
    # http://localhost:11434/v1 for Ollama, or drop it for OpenAI proper.
    openai_api_key: str = ""
    openai_base_url: str = "https://api.groq.com/openai/v1"
    openai_model: str = "llama-3.3-70b-versatile"

    # --- Retrieval ----------------------------------------------------------------
    # gemini-embedding-001 returns 3072 dimensions by default. A two-section
    # corpus does not need that; 768 keeps the index small at no measurable
    # recall cost. Changing this changes the collection name -- see rag/store.py.
    embedding_dimensions: int = 768
    retrieval_k: int = 3

    # Retrieval returns the k nearest chunks whether or not they are relevant. On a
    # 4-sentence corpus that means a burst-pipe question cites Personal Property,
    # which makes citations decorative. These two filters keep `sources` to text the
    # answer was actually grounded in.
    #
    # Relative, not absolute, because the two embedders live on different scales:
    # the lexical test embedder puts unrelated text at 1.0, while Gemini compresses
    # everything into a narrower band. A margin from the best hit travels between them.
    #
    # 0.10 is measured, not guessed. Against gemini-embedding-001 at 768 dims this
    # corpus produces distances of 0.198-0.429, so a wider margin (0.25 was the first
    # guess) admits the entire document on every query and filters nothing.
    # Known limitation: on a genuinely out-of-scope question -- "earthquake damage" --
    # all four chunks sit within 0.353-0.407 of each other, so no *relative* rule can
    # tell "nothing is relevant" from "everything is". The prompt handles that case by
    # instructing the model to say the policy does not address it; citations then read
    # as "what I checked" rather than "what supports this".
    relevance_margin: float = 0.10
    # Cosine distance >= 1.0 means orthogonal: no relationship at all.
    max_distance: float = 1.0

    # --- Paths --------------------------------------------------------------------
    data_dir: Path = REPO_ROOT / "data"
    chroma_dir: Path = REPO_ROOT / ".chroma"

    @property
    def policy_path(self) -> Path:
        return self.data_dir / "sample_policy.md"

    @property
    def claims_path(self) -> Path:
        return self.data_dir / "mock_claims.json"

    @property
    def users_path(self) -> Path:
        return self.data_dir / "mock_users.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
