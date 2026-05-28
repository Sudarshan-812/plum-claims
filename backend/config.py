"""Application configuration loaded from environment variables."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    anthropic_api_key: str = ""
    policy_file_path: str = "data/policy_terms.json"
    environment: str = "development"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()


def get_policy_path() -> Path:
    """Return absolute path to the policy terms JSON file."""
    base = Path(__file__).parent
    return base / settings.policy_file_path
