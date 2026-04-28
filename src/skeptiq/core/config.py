from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from skeptiq.schemas.analysis import ImpactMagnitude

LogFormat = Literal["console", "json"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    anthropic_api_key: str
    llm_model: str = "claude-sonnet-4-6"

    telegram_bot_token: str
    my_telegram_chat_id: int
    my_timezone: str = "UTC"

    watchlist: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["BTC", "ETH"])

    min_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    min_impact: ImpactMagnitude = "medium"

    rss_poll_interval_sec: int = Field(default=60, gt=0)

    database_url: str = "sqlite+aiosqlite:///./skeptiq.db"

    log_level: str = "INFO"
    log_format: LogFormat = "console"

    @field_validator("watchlist", mode="before")
    @classmethod
    def _parse_watchlist(cls, value: object) -> object:
        if isinstance(value, str):
            return [token.strip().upper() for token in value.split(",") if token.strip()]
        return value

    @property
    def watchlist_set(self) -> set[str]:
        return set(self.watchlist)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
