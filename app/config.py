"""Configuration de l'application via variables d'environnement (.env)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Personal Assistant Hub"
    app_env: str = "development"
    debug: bool = True
    port: int = 8000

    # Sécurité & Accès distant
    api_key: str = ""

    # Base de Données Locale SQLite (hub_data.db)
    sqlite_db_path: str = "hub_data.db"

    # Google Sheets
    google_service_account_file: str = "credentials.json"
    google_service_account_info: str = ""
    spreadsheet_meals_shopping_id: str = ""
    spreadsheet_budget_id: str = ""
    spreadsheet_sport_id: str = ""

    # Google Gemini LLM
    gemini_api_key: str = ""
    gemini_model: str = "auto"
    gemini_max_daily_requests: int = 1000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
