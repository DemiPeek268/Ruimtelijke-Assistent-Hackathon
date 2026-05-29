from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_backend_dir = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_backend_dir / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    OPENAI_KEY: str = ""

    ALLOWED_ORIGINS: str = "*"
    DEBUG: bool = False
    DICTIONARY_CACHE: bool = True
    OPENAI_MODEL: str = "gpt-5-chat"
    PORT: int = 8000
    DATABASE_URL: str = (
        "postgresql+asyncpg://ruimtelijke:secret123!@localhost:5432/sessions"
    )

    # MLflow observability
    MLFLOW_TRACKING_URI: str = "http://localhost:5000"
    MLFLOW_EXPERIMENT_NAME: str = "ruimtelijke-assistent-dev"
    MLFLOW_ENABLED: bool = False
    ENV: str = "dev"
    APP_VERSION: str = "dev"

    # Filter value validation — fuzzy-matching thresholds
    FILTER_MAX_FUZZY_CANDIDATES: int = (
        20  # Cap candidates shown to the correction LLM to keep the prompt concise.
    )
    FILTER_FUZZY_CUTOFF: float = 0.3  # Minimum similarity score; lower values cause too many false positives on short names.
    FILTER_ALL_VALUES_THRESHOLD: int = 200  # Columns with fewer distinct values show the full list instead of fuzzy matches.


settings = Settings()
