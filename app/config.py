import logging
import os
from dataclasses import dataclass


@dataclass
class Config:
    bot_token: str
    database_url: str
    avia_token: str | None = None
    proxy: str | None = None


def load_config() -> Config:
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise ValueError("BOT_TOKEN не задан")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        database_url = "sqlite"

    raw = os.environ.get("AVIA_API_TOKEN", "")
    logging.info("RAW AVIA_API_TOKEN len=%d prefix=%s", len(raw), raw[:8] if raw else "EMPTY")
    avia_token = raw or None

    proxy = os.getenv("BOT_PROXY") or None
    return Config(bot_token=bot_token, database_url=database_url, avia_token=avia_token, proxy=proxy)
