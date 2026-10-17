from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="NEURA1_", extra="ignore")

    falkordb_host: str = "localhost"
    falkordb_port: int = 6380
    falkordb_username: str | None = None
    falkordb_password: str | None = None
    graph_name: str = "flyvi"
    fixture_dir: Path = REPO_ROOT / "fixture" / "flyvi"
    # Where a company's own uploaded documents are kept (not committed).
    data_dir: Path = REPO_ROOT / "data"

    # Any OpenAI-compatible endpoint: a local DGX (vLLM / Ollama / SGLang) or a hosted provider.
    llm_base_url: str | None = None
    llm_api_key: str = "not-needed"
    llm_model: str | None = None
    llm_embed_model: str | None = None  # e.g. nomic-embed-text; enables semantic search over passages
    # Embeddings may come from a different server than chat (e.g. chat on a DGX, embeddings on local Ollama).
    llm_embed_base_url: str | None = None
    llm_embed_api_key: str | None = None
    llm_timeout: float = 900  # seconds; CPU-only local models are slow, a DGX is fast

    # Live ingestion. Slack requests are verified with the app's signing secret; Jira with a shared secret header.
    slack_signing_secret: str | None = None
    webhook_secret: str = "change-me"

    # Required in the X-Demo-Passcode header for anything that writes to the graph.
    demo_passcode: str = "change-me"


settings = Settings()
