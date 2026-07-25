from aiogram import Bot, Dispatcher
from app.config import Config


def setup_bot(config: Config) -> tuple[Bot, Dispatcher]:
    bot = Bot(token=config.bot_token)
    dp = Dispatcher()
    return bot, dp
