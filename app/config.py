import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    bot_token: str
    avia_token: str | None = None
    proxy: str | None = None


def load_config() -> Config:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise ValueError("BOT_TOKEN не задан")
    avia_token = os.getenv("AVIA_API_TOKEN") or None
    proxy = os.getenv("BOT_PROXY") or None
    return Config(bot_token=bot_token, avia_token=avia_token, proxy=proxy)
