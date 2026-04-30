from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    llm_backend: str = Field(default="gemini", description="'gemini', 'huggingface', or 'ollama'")
    gemini_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-2.0-flash")
    gcp_project: str = Field(default="vouch-agentic")
    gcp_location: str = Field(default="us-central1")
    # Legacy local backends (kept for fallback)
    hf_token: str = Field(default="", description="Hugging Face access token")
    hf_model: str = Field(default="google/gemma-4-E2B-it")
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="gemma3")

    # Database (PostgreSQL via asyncpg)
    database_url: str = Field(default="sqlite+aiosqlite:///./data/vouch.db")
    # Vector store (PostgreSQL via psycopg2 — sync)
    vector_db_url: str = Field(default="")

    # API
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    cors_origins: str = Field(default="http://localhost:5173")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]


settings = Settings()
