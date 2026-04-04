from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_bot_token: str = ""
    openai_api_key: str = ""
    database_url: str = "sqlite:///./data/calories.db"

    # Open Food Facts (free, no key) — fallback when local JSON + regex miss
    open_food_facts_enabled: bool = True
    off_contact_url: str = "https://github.com"
    off_request_timeout_sec: float = 8.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
