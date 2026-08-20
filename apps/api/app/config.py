from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / '.env', Path('.env')),
        env_file_encoding='utf-8',
        extra='ignore',
    )

    openai_api_key: str = ''
    openai_base_url: str = 'https://api.openai.com/v1'
    openai_model: str = 'gpt-4o-mini'
    use_mock_llm: bool = False

    api_host: str = '0.0.0.0'
    api_port: int = 8000
    cors_origins: str = 'http://localhost:5173'

    checkpoint_db_path: str = './.data/checkpoints.db'
    checkpoint_allow_memory_fallback: bool = False
    graph_cache_size: int = 128

    max_discussion_rounds: int = 8
    max_revision_rounds: int = 5

    agent_max_steps: int = 30
    agent_command_timeout: int = 120
    agent_command_output_limit: int = 200_000
    agent_shell_enabled: bool = True
    agent_http_enabled: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(',') if origin.strip()]

    @property
    def should_use_mock(self) -> bool:
        return self.use_mock_llm or not self.openai_api_key or self.openai_api_key == 'sk-xxx'


@lru_cache
def get_settings() -> Settings:
    return Settings()
