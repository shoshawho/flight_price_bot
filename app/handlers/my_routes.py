from aiogram import Router, F
from aiogram.types import CallbackQuery

from app.database import get_db

router = Router()


@router.callback_query(F.data == "my_routes")
async def show_routes(callback: CallbackQuery) -> None:
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT origin, destination, date_from, date_to, passengers, last_price
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
    for r in routes:
        price = f"{r[5]:.0f} руб." if r[5] else "ещё не проверялась"
        lines.append(
            f"{r[0]} → {r[1]}\n"
            f"📅 {r[2]} – {r[3]}\n"
            f"👤 {r[4]} чел.\n"
            f"💰 {price}"
        )

    await callback.message.edit_text("\n\n".join(lines))
    await callback.answer()
