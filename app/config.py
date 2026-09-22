"""Configuration de l'application via variables d'environnement."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Personal Assistant Hub"
    app_env: str = "development"
    debug: bool = True
    port: int = 8000

    # Sécurité & Accès distant
    api_key: str = ""

    # Google Sheets
    google_service_account_file: str = "credentials.json"
    spreadsheet_meals_shopping_id: str = ""
    spreadsheet_budget_id: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
