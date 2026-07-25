from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.api.price_api import fetch_price
from app.config import load_config
from app.database import get_db

router = Router()


def _back_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Обновить цены", callback_data="refresh_prices")
    builder.button(text="« Назад", callback_data="back_menu")
    return builder.as_markup()


@router.callback_query(F.data == "my_routes")
async def show_routes(callback: CallbackQuery) -> None:
    text = await _build_routes_text(callback.from_user.id)
    if text is None:
        await callback.message.edit_text("У вас нет сохранённых маршрутов.")
    else:
        await callback.message.edit_text(text, reply_markup=_back_kb())
    await callback.answer()


@router.callback_query(F.data == "refresh_prices")
async def refresh_prices(callback: CallbackQuery) -> None:
    config = load_config()
    avia_token = config.avia_token
    if not avia_token:
        await callback.message.edit_text(
            "AVIA_API_TOKEN не настроен. Проверка цен недоступна."
        )
        await callback.answer()
        return

    logging.info("Ручная проверка цен, токен=%s...", avia_token[:8])
    await callback.message.edit_text("🔄 Проверяю цены...")

    async with get_db() as conn:
        user_routes = await conn.fetch(
            """
            SELECT routes.id, routes.passengers, routes.baggage
            FROM routes
            JOIN users ON routes.user_id = users.id
            WHERE users.telegram_id = $1
            """,
            callback.from_user.id,
        )

    if not user_routes:
        await callback.message.edit_text("У вас нет сохранённых маршрутов.")
        await callback.answer()
        return

    results = []
    has_error = False

    for r in user_routes:
        route_id = r["id"]
        passengers = r["passengers"]
        baggage = r["baggage"]

        async with get_db() as conn:
            segs = await conn.fetch(
                """
                SELECT origin, origin_code, destination, dest_code, date,
                       transit_code, min_layover, max_layover
                FROM segments
                WHERE route_id = $1
                ORDER BY sort_order
                """,
                route_id,
            )

        if not segs:
            continue

        total = 0.0
        for s in segs:
            origin_code = s["origin_code"]
            dest_code = s["dest_code"]
            date_str = s["date"]
            transit_code = s["transit_code"]
            min_lay = s["min_layover"]
            max_lay = s["max_layover"]
            try:
                logging.info("Запрос цены: %s->%s (%s)", origin_code, dest_code, date_str)
                price = await fetch_price(
                    origin_code=origin_code,
                    dest_code=dest_code,
                    date_from=date_str,
                    token=avia_token,
                    one_way=True,
                    baggage=baggage,
                    transit_code=transit_code,
                    min_layover=min_lay,
                    max_layover=max_lay,
                )
            except Exception:
                price = None

            if price is None:
                total = None
                break
            total += price

        if total is None:
            has_error = True
            continue

        total *= passengers

        async with get_db() as conn:
            row = await conn.fetchrow(
                "SELECT last_price FROM routes WHERE id = $1", route_id
            )
            old_price = row["last_price"] if row else None

            await conn.execute(
                "UPDATE routes SET last_price = $1, last_checked = CURRENT_TIMESTAMP WHERE id = $2",
                total, route_id,
            )

        route_str = " → ".join(f"{s['origin']}→{s['destination']}" for s in segs)
        if old_price is not None and total != old_price:
            direction = "📈" if total > old_price else "📉"
            results.append(f"{route_str}: {old_price:.0f} → {total:.0f} руб. {direction}")
        else:
            results.append(f"{route_str}: {total:.0f} руб.")

    if not results and has_error:
        await callback.message.edit_text("Не удалось получить цены. Попробуйте позже.")
    elif has_error:
        results.append("\n⚠️ Некоторые цены не получены")
        await callback.message.edit_text(
            "🔄 Цены обновлены:\n\n" + "\n".join(results),
            reply_markup=_back_kb(),
        )
    else:
        await callback.message.edit_text(
            "🔄 Цены обновлены:\n\n" + "\n".join(results),
            reply_markup=_back_kb(),
        )

    await callback.answer()


@router.callback_query(F.data == "back_menu")
async def back_to_menu(callback: CallbackQuery) -> None:
    from app.keyboards.inline import main_menu
    await callback.message.edit_text(
        "Главное меню:",
        reply_markup=main_menu(),
    )
    await callback.answer()


async def _build_routes_text(telegram_id: int) -> str | None:
    async with get_db() as conn:
        routes = await conn.fetch(
            """
            SELECT routes.id, routes.passengers, routes.last_price,
                   routes.baggage, routes.notify_hour
            FROM routes
            JOIN users ON routes.user_id = users.id
            WHERE users.telegram_id = $1
            """,
            telegram_id,
        )

    if not routes:
        return None

    lines = []
    for r in routes:
        route_id = r["id"]
        passengers = r["passengers"]
        last_price = r["last_price"]
        baggage = r["baggage"]
        notify_hour = r["notify_hour"]

        async with get_db() as conn:
            segs = await conn.fetch(
                """
                SELECT origin, destination, date, transit_name
                FROM segments
                WHERE route_id = $1
                ORDER BY sort_order
                """,
                route_id,
            )

        if not segs:
            continue

        parts = []
        for s in segs:
            seg_str = f"{s['origin']} → {s['destination']}"
            if s["transit_name"]:
                seg_str += f" (через {s['transit_name']})"
            parts.append(seg_str)
        route_str = " → ".join(parts)
        dates = ", ".join(s["date"] for s in segs)
        price = f"{last_price:.0f} руб." if last_price else "ещё не проверялась"
        baggage_label = "с багажом" if baggage else "ручная кладь"
        notify_label = f"{notify_hour}:00" if notify_hour is not None else "—"

        lines.append(
            f"🚀 {route_str}\n"
            f"📅 {dates}\n"
            f"👤 {passengers} чел.\n"
            f"🧳 {baggage_label}\n"
            f"⏰ Уведомления в {notify_label}\n"
            f"💰 {price}"
        )

    return "\n\n".join(lines)
