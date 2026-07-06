"""
Configuration Module for the Autonomous Business Document Agent.

This module centralizes all application settings and environment variable validation.
It leverages Pydantic Settings to read configuration values from environment variables
or a local '.env' file, performing strict validation on startup.

Design Decisions & Trade-offs:
1. Pydantic Settings: Using BaseSettings guarantees fail-fast validation on startup.
   If GEMINI_API_KEY is missing, the application halts immediately with a clear error.
2. Alias mapping: Allows matching typical uppercase ENV variables (e.g., GEMINI_API_KEY)
   to clean, lowercase Pythonic attributes (e.g., settings.gemini_api_key).
3. Directory verification: Proactively creates the directory for storing generated documents.
"""

import sys
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application Settings validator and container.
    Loads variables from the environment or a .env file automatically.
    """

    # Gemini API Credentials (Required)
    gemini_api_key: str = Field(..., alias="GEMINI_API_KEY")

    # Gemini model name
    gemini_model: str = Field(default="gemini-2.0-flash", alias="GEMINI_MODEL")

    # Groq API key (optional, used as primary when Gemini quota is exhausted)
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")

    # FastAPI Server configuration (Optional, with defaults)
    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    environment: str = Field(default="development", alias="ENVIRONMENT")

    # Logging levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Destination directory for generated Word files
    generated_dir: Path = Field(default=Path("generated"), alias="GENERATED_DIR")

    # Configure Pydantic Settings to read from .env files
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore extra environment variables
        populate_by_name=True,  # Allow populating using either field name or alias
    )

    @field_validator("gemini_api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """
        Validate that the Gemini API Key is not empty and is not the default placeholder.
        """
        cleaned = v.strip()
        if not cleaned or cleaned == "your_gemini_api_key_here":
            raise ValueError(
                "GEMINI_API_KEY environment variable is not configured. "
                "Please configure a valid API key from Google AI Studio in your '.env' file."
            )
        return cleaned

    @field_validator("generated_dir")
    @classmethod
    def ensure_dir_exists(cls, v: Path) -> Path:
        """
        Ensures the document output directory exists. If not, it is created.
        """
        try:
            v.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise ValueError(f"Failed to create generated directory at '{v}': {e}")
        return v


# Instantiate the settings. This runs validation at module import time.
# If config fails, we output a readable message and exit gracefully.
try:
    settings = Settings()
except Exception as err:
    print(
        f"\n[CONFIG ERROR] Failed to load configuration:\n{err}\n"
        "Please check your '.env' file against '.env.example'.\n",
        file=sys.stderr,
    )
    sys.exit(1)
