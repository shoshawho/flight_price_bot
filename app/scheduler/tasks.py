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
            SELECT routes.id, users.telegram_id, routes.passengers, routes.last_price
            FROM routes
            JOIN users ON routes.user_id = users.id
            """
        )
        routes = await cursor.fetchall()

    for route_id, tg_id, passengers, last_price in routes:
        async with get_db() as db:
            cursor = await db.execute(
                """
                SELECT origin, origin_code, destination, dest_code, date
                FROM segments
                WHERE route_id = ?
                ORDER BY sort_order
                """,
                (route_id,),
            )
            segs = await cursor.fetchall()

        if not segs:
            continue

        total_price = 0.0
        for origin_name, origin_code, dest_name, dest_code, date_str in segs:
            try:
                price = await fetch_price(
                    origin_code=origin_code,
                    dest_code=dest_code,
                    date_from=date_str,
                    token=avia_token,
                    one_way=True,
                )
            except Exception:
                logging.exception("Ошибка при запросе цены для сегмента #%s", route_id)
                price = None

            if price is None:
                total_price = None
                break
            total_price += price

        if total_price is None:
            continue

        total_price *= passengers

        if total_price != last_price:
            async with get_db() as db:
                await db.execute(
                    "UPDATE routes SET last_price = ? WHERE id = ?",
                    (total_price, route_id),
                )
                await db.commit()

            if last_price is not None:
                direction = "📈 Выросла" if total_price > last_price else "📉 Снизилась"
                route_str = " → ".join(
                    f"{s[0]}→{s[2]}" for s in segs
                )
                try:
                    await bot.send_message(
                        tg_id,
                        f"{direction} цена на маршрут {route_str}\n"
                        f"Было: {last_price:.0f} руб.\n"
                        f"Стало: {total_price:.0f} руб.",
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
