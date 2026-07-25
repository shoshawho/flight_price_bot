from aiogram import Router, F
from aiogram.types import CallbackQuery

from app.database import get_db

router = Router()


@router.callback_query(F.data == "my_routes")
async def show_routes(callback: CallbackQuery) -> None:
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT routes.id, routes.passengers, routes.last_price, routes.baggage
            FROM routes
            JOIN users ON routes.user_id = users.id
            WHERE users.telegram_id = ?
            """,
            (callback.from_user.id,),
        )
        routes = await cursor.fetchall()

    if not routes:
        await callback.message.edit_text("У вас нет сохранённых маршрутов.")
        await callback.answer()
        return

    lines = []
    for route_id, passengers, last_price, baggage in routes:
        async with get_db() as db:
            cursor = await db.execute(
                """
                SELECT origin, destination, date
                FROM segments
                WHERE route_id = ?
                ORDER BY sort_order
                """,
                (route_id,),
            )
            segs = await cursor.fetchall()

        if not segs:
            continue

        route_str = " → ".join(f"{s[0]}→{s[2]}" for s in segs)
        dates = ", ".join(s[2] for s in segs)
        price = f"{last_price:.0f} руб." if last_price else "ещё не проверялась"
        baggage_label = "с багажом" if baggage else "ручная кладь"

        lines.append(
            f"🚀 {route_str}\n"
            f"📅 {dates}\n"
            f"👤 {passengers} чел.\n"
            f"🧳 {baggage_label}\n"
            f"💰 {price}"
        )

    await callback.message.edit_text("\n\n".join(lines))
    await callback.answer()
