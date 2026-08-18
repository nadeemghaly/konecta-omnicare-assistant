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
    # gemini-embedding-001 returns 3072 dimensions by default. A document this
    # small does not need that; 768 keeps the index small at no measurable
    # recall cost. Changing this changes the collection name -- see rag/store.py,
    # and invalidates the measured relevance_margin below.
    embedding_dimensions: int = 768
    retrieval_k: int = 3

    # Retrieval returns the k nearest chunks whether or not they are relevant --
    # unfiltered, a burst-pipe question cites the Theft clause, which makes
    # citations decorative. These two filters keep `sources` to text the answer
    # was actually grounded in.
    #
    # Relative, not absolute, because the two embedders live on different scales:
    # the lexical test embedder puts unrelated text at 1.0, while Gemini compresses
    # everything into a narrower band. A margin from the best hit travels between them.
    #
    # 0.13 is measured, not guessed, and re-measured whenever the corpus changes.
    # Against gemini-embedding-001 at 768 dims over the 14-chunk document, the
    # reference query "Is a burst pipe covered, and what is the deductible?" ranks:
    #
    #     0.1903  Section 1  "...covered up to $25,000 with a $500 deductible."
    #     0.2960  Section 1  "Gradual leaks or flood damage are strictly excluded."
    #     0.3497  Section 4  "Theft of insured belongings is covered up to..."
    #
    # So the margin must be >= 0.1057 to keep Section 1's exclusion clause and
    # < 0.1594 to keep Section 4 out. 0.13 is the midpoint of that window, which
    # leaves roughly equal headroom on both sides rather than sitting on an edge.
    # The earlier 0.10 was correct for the original 4-sentence corpus but became
    # marginally too tight once the document grew -- it dropped the exclusion
    # clause from every burst-pipe answer. Re-measure rather than adjust by feel;
    # scratch measurement lives in the commit that introduced this value.
    #
    # Known limitation, unchanged by the expansion: on a genuinely out-of-scope
    # question -- "does my policy cover a trip to Mars?" -- the nearest chunks sit
    # within 0.036 of each other, so no *relative* rule can tell "nothing is
    # relevant" from "everything is". The prompt handles that case by instructing
    # the model to say the policy does not address it; citations then read as
    # "what I checked" rather than "what supports this".
    relevance_margin: float = 0.13
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
