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
    # Speech to text for meeting recordings: local open-source Whisper by default; or any OpenAI-compatible
    # transcription endpoint (for example one hosted on the DGX) when stt_base_url is set.
    stt_model: str = "small.en"
    stt_base_url: str | None = None
    stt_api_key: str | None = None
    stt_remote_model: str = "whisper-1"

    # Any OpenAI-compatible endpoint: a local DGX (vLLM / Ollama / SGLang) or a hosted provider.
    llm_base_url: str | None = None
    llm_api_key: str = "not-needed"
    llm_model: str | None = None
    llm_embed_model: str | None = None  # e.g. nomic-embed-text; enables semantic search over passages
    # Embeddings may come from a different server than chat (e.g. chat on a DGX, embeddings on local Ollama).
    llm_embed_base_url: str | None = None
    llm_embed_api_key: str | None = None
    llm_timeout: float = 900  # seconds; CPU-only local models are slow, a DGX is fast
    # Shown in the app, e.g. "DGX Spark".
    llm_label: str | None = None
    # How much the model may read at once. A DGX with a long context can take far more than a laptop model.
    llm_tool_result_chars: int = 6000   # one tool result shown to the agent
    llm_doc_chars: int = 12000          # one AI edit of a document
    # Read new information automatically (decisions, meeting actions, skill tags) while the main model is reachable.
    auto_extract: bool = True
    # Used automatically when the main endpoint is unreachable (e.g. the DGX is off the network).
    llm_fallback_base_url: str | None = None
    llm_fallback_model: str | None = None
    llm_fallback_api_key: str = "not-needed"

    # Live ingestion. Slack requests are verified with the app's signing secret; Jira with a shared secret header.
    slack_signing_secret: str | None = None
    webhook_secret: str = "change-me"

    # AI requests allowed per visitor per minute (a public demo shares one model).
    ai_per_minute: int = 8

    # Background jobs: the mail-drop inbox and the 09:00 IST morning brief. Off in tests.
    background: bool = True

    # Required in the X-Demo-Passcode header for anything that writes to the graph.
    # Optional. Unset (the default), anyone with the link can make changes in the demo; set it to require a passcode.
    demo_passcode: str | None = None


settings = Settings()
