import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.api.price_api import fetch_price
from app.config import Config
from app.database import get_db

scheduler = AsyncIOScheduler()


async def check_prices(bot: Bot, avia_token: str | None) -> None:
    if not avia_token:
        logging.warning("AVIA_API_TOKEN не задан — пропускаем проверку цен")
        return

    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT routes.id, users.telegram_id, origin, destination, origin_code,
                   dest_code, date_from, date_to, passengers, last_price
            FROM routes
            JOIN users ON routes.user_id = users.id
            """
        )
        rows = await cursor.fetchall()

    for row in rows:
        (
            route_id,
            tg_id,
            origin_name,
            dest_name,
            origin_code,
            dest_code,
            df,
            dt,
            passengers,
            last_price,
        ) = row

        try:
            new_price = await fetch_price(
                origin_code=origin_code,
                dest_code=dest_code,
                date_from=df,
                date_to=dt,
                token=avia_token,
                passengers=passengers,
            )
        except Exception:
            logging.exception("Ошибка при запросе цены для маршрута #%s", route_id)
            continue

        if new_price is None:
            continue

        if new_price != last_price:
            async with get_db() as db:
                await db.execute(
                    "UPDATE routes SET last_price = ? WHERE id = ?",
                    (new_price, route_id),
                )
                await db.commit()

            if last_price is not None:
                direction = "📈 Выросла" if new_price > last_price else "📉 Снизилась"
                try:
                    await bot.send_message(
                        tg_id,
                        f"{direction} цена на маршрут {origin_name} → {dest_name}\n"
                        f"Было: {last_price:.0f} руб.\n"
                        f"Стало: {new_price:.0f} руб.\n"
                        f"Даты: {df} – {dt}",
                    )
                except Exception:
                    logging.warning(
                        "Не удалось отправить уведомление пользователю %s", tg_id
                    )


async def start_scheduler(bot: Bot, config: Config) -> None:
    scheduler.add_job(
        check_prices,
        "interval",
        days=1,
        args=[bot, config.avia_token],
        id="check_prices",
        replace_existing=True,
    )
    scheduler.start()
    logging.info("Планировщик запущен — проверка цен раз в день")
