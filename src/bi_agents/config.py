import os
from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from pathlib import Path


class Settings(BaseSettings):
    # add model_confgi instead of the inner class
    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")
    # Project paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    TEMP_CODES_DIR: Path = BASE_DIR / "temp"
    STATIC_DIR: Path = BASE_DIR / "static"
    DATA_DIR: Path = BASE_DIR / "data"
    METADATA_DIR: Path = BASE_DIR / "metadata"
    VENV_DIR: Path = BASE_DIR / "environment"

    # Log DB path
    LOGS_DB_PATH: Path = BASE_DIR / "logs/logs.db"

    # API Keys and Connection Strings
    OPENAI_API_KEY: str
    AZURE_STORAGE_CONNECTION_STRING: str
    MONGODB_URI: str
    AZURE_CONTAINER_NAME: str = "data"

    # Agent/Model settings
    DEFAULT_MODEL: str = "gpt-4o-mini"
    DEFAULT_METADATA_LLM: str = "gpt-4o-mini"
    MESSAGE_HISTORY_LIMIT: int = 3


settings = Settings()

# Create necessary directories on startup
settings.TEMP_CODES_DIR.mkdir(exist_ok=True)
settings.STATIC_DIR.mkdir(exist_ok=True)
settings.DATA_DIR.mkdir(exist_ok=True)
settings.METADATA_DIR.mkdir(exist_ok=True)
settings.LOGS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
