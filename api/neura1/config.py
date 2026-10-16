from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="NEURA1_", extra="ignore")

    falkordb_host: str = "localhost"
    falkordb_port: int = 6380
    falkordb_username: str | None = None
    falkordb_password: str | None = None
    graph_name: str = "voltline"
    fixture_dir: Path = REPO_ROOT / "fixture" / "voltline"
    # Where a company's own uploaded documents are kept (not committed).
    data_dir: Path = REPO_ROOT / "data"

    # Any OpenAI-compatible endpoint: a local DGX (vLLM / Ollama / SGLang) or a hosted provider.
    llm_base_url: str | None = None
    llm_api_key: str = "not-needed"
    llm_model: str | None = None
    llm_timeout: float = 900  # seconds; CPU-only local models are slow, a DGX is fast

    # Required in the X-Demo-Passcode header for anything that writes to the graph.
    demo_passcode: str = "change-me"


settings = Settings()
