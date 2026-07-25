import asyncio
import logging
import os

from app.bot import setup_bot
from app.config import load_config
from app.database import init_db
from app.handlers import start, add_route, my_routes
from app.scheduler.tasks import start_scheduler

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    config = load_config()

    if config.proxy:
        os.environ["HTTP_PROXY"] = config.proxy
        os.environ["HTTPS_PROXY"] = config.proxy
        logging.info("Прокси установлен: %s", config.proxy)

    await init_db()

    bot, dp = setup_bot(config)

    dp.include_router(start.router)
    dp.include_router(add_route.router)
    dp.include_router(my_routes.router)

    await start_scheduler(bot, config)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
