"""Configurações do provedor OpenRouter para o motor JEV."""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class OpenRouterSettings(BaseSettings):
    """Configurações da API OpenRouter e modelo JEV."""
    
    api_key: str = Field(default="sk-or-v1-mock-key", validation_alias="OPENROUTER_API_KEY")
    endpoint: str = Field(
        default="https://openrouter.ai/api/v1/chat/completions",
        validation_alias="OPENROUTER_ENDPOINT"
    )
    model: str = Field(default="typesafe/jev-latest", validation_alias="OPENROUTER_MODEL")
    app_url: str = Field(default="https://xledger.local", validation_alias="OPENROUTER_APP_URL")
    app_title: str = Field(default="XLedger Financial Engine", validation_alias="OPENROUTER_APP_TITLE")
    timeout_seconds: float = Field(default=8.0, validation_alias="OPENROUTER_TIMEOUT_SEC")
    confidence_threshold: float = Field(default=0.90, validation_alias="CONFIDENCE_THRESHOLD")
    max_retries: int = Field(default=3, validation_alias="OPENROUTER_MAX_RETRIES")
    mock_mode: bool = Field(default=False, validation_alias="OPENROUTER_MOCK_MODE")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


openrouter_settings = OpenRouterSettings()
