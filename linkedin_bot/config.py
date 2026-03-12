"""Application configuration via Pydantic Settings.

Loads credentials from .env, validates resume path, and provides
typed search configuration from YAML.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class SearchConfig(BaseModel):
    """Typed search configuration loaded from search_config.yaml.

    Validates all fields at load time instead of failing with KeyError at runtime.

    Args:
        keywords: Job search keywords.
        remote_only: Filter for remote positions only.
        experience_levels: Experience level filter codes.
        date_posted: Date posted filter (1=24h, 2=week, 3=month).
        locations: Locations to search.
        blacklist_titles: Title keywords to skip.
        blacklist_companies: Company names to skip.
        min_match_score: Minimum AI match score (0-100).
    """

    model_config = {"extra": "ignore"}

    keywords: list[str] = Field(default_factory=lambda: ["Software Engineer"])
    remote_only: bool = True
    experience_levels: list[int] = Field(default_factory=lambda: [3, 4])
    date_posted: int = Field(default=2, ge=1, le=3)
    locations: list[str] = Field(default_factory=lambda: [""])
    blacklist_titles: list[str] = Field(default_factory=list)
    blacklist_companies: list[str] = Field(default_factory=list)
    min_match_score: int = Field(default=50, ge=0, le=100)


class Settings(BaseSettings):
    """Bot configuration loaded from .env file.

    All credentials and behavioral settings are loaded from environment
    variables or the .env file at the project root.
    """

    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── DeepSeek API ──
    deepseek_api_key: SecretStr = SecretStr("")
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # ── LinkedIn Credentials ──
    linkedin_email: str = ""
    linkedin_password: SecretStr = SecretStr("")

    # ── Resume PDF path (for upload in Easy Apply) ──
    resume_path: str = ""

    # ── Bot Behavior ──
    max_applications_per_session: int = Field(default=30, ge=1, le=100)
    min_delay_seconds: float = Field(default=3.0, ge=1.0)
    max_delay_seconds: float = Field(default=8.0, ge=2.0)
    dry_run: bool = True
    headless: bool = False

    # ── Pagination ──
    max_pages_per_search: int = Field(default=3, ge=1, le=10)

    # ── AI Retry ──
    ai_max_retries: int = Field(default=3, ge=1, le=5)
    ai_retry_delay: float = Field(default=2.0, ge=0.5)

    @field_validator("resume_path")
    @classmethod
    def validate_resume_path(cls, v: str) -> str:
        """Validate resume file exists if provided.

        Returns resolved absolute path for consistent usage.
        """
        if v:
            resolved = Path(v).resolve()
            if not resolved.exists():
                msg = f"Resume file not found: {resolved}"
                raise ValueError(msg)
            return str(resolved)
        return v


def load_yaml(filename: str) -> dict[str, Any]:
    """Load a YAML configuration file from the project root.

    Args:
        filename: Name of the YAML file relative to project root.

    Returns:
        Parsed YAML content as a dictionary.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
    """
    filepath = ROOT_DIR / filename
    if not filepath.exists():
        msg = f"Configuration file not found: {filepath}"
        raise FileNotFoundError(msg)
    with filepath.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}
    return data


def load_resume() -> dict[str, Any]:
    """Load resume data from resume.yaml."""
    return load_yaml("resume.yaml")


def load_search_config() -> SearchConfig:
    """Load and validate job search configuration from search_config.yaml.

    Returns:
        Validated SearchConfig model.
    """
    raw = load_yaml("search_config.yaml")
    return SearchConfig.model_validate(raw)


# Singleton
settings = Settings()
