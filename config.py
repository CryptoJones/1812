from pydantic_settings import BaseSettings
from pydantic import ConfigDict, field_validator


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", extra="ignore")
    # Discord
    discord_token: str

    # LLM
    llm_provider: str = "openai"          # openai | anthropic | ollama | openrouter
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434/v1"
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Persona
    system_prompt: str = (
        "You are 1812 — a Discord bot built by CryptoJones, named after Tchaikovsky's 1812 Overture. "
        "You live in Discord servers and you know Discord inside and out: slash commands, bots, webhooks, "
        "roles, permissions, channels, threads, stages, forums, embeds, the API, discord.py, interactions, "
        "intents, rate limits, gateway events, and server administration. "
        "When someone asks about Discord — how to build something, why something is broken, how permissions work, "
        "how to structure a server, how to write a bot — that is your home turf. Give direct, specific answers. "
        "You have opinions. You have context about what you're running on. "
        "You are not ChatGPT. You are not a generic assistant. You are 1812. "
        "Be concise unless depth is needed. Don't hedge everything. Don't add unnecessary disclaimers. "
        "If you don't know something, say so plainly and move on."
    )

    # History
    max_history_messages: int = 20        # per channel, before summarisation
    summarise_at: int = 40                # trigger summarisation at this count

    # Rate limiting
    rate_limit_requests: int = 10
    rate_limit_window_seconds: int = 60

    # Storage
    db_path: str = "1812.db"

    # Web sidecar
    web_host: str = "0.0.0.0"
    web_port: int = 8080

    # Auto-shutdown after N minutes of runtime. None = unbounded (default).
    # Useful for time-boxed runs, scheduled jobs, and CI canaries.
    # CLI `--shutdown-after MINUTES` overrides this env value.
    shutdown_after_minutes: int | None = None

    @field_validator("llm_provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = {"openai", "anthropic", "ollama", "openrouter"}
        if v not in allowed:
            raise ValueError(f"llm_provider must be one of {allowed}")
        return v

    @field_validator("shutdown_after_minutes")
    @classmethod
    def validate_shutdown_after_minutes(cls, v: int | None) -> int | None:
        if v is None:
            return v
        if v <= 0:
            raise ValueError(
                "shutdown_after_minutes must be a positive integer "
                "(unset / null = unbounded)"
            )
        return v


settings = Settings()
