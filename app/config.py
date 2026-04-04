from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_bot_token: str = ""
    openai_api_key: str = ""
    database_url: str = "sqlite:///./data/calories.db"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
