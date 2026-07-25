import logging
import re
from datetime import datetime
from typing import Any

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.api.iata import resolve_city
from app.api.price_api import fetch_price
from app.config import load_config
from app.database import get_db

router = Router()


class AddRoute(StatesGroup):
    origin = State()
    destination = State()
    date = State()
    transit = State()
    layover = State()
    add_leg = State()
    passengers = State()
    baggage = State()
    notify_time = State()


def _parse_date(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw.strip(), "%d.%m.%Y")
    except ValueError:
        return None


def _yes_no_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="Да", callback_data="leg_yes")
    builder.button(text="Нет, хватит", callback_data="leg_no")
    return builder.as_markup()


def _baggage_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="Ручная кладь", callback_data="baggage_0")
    builder.button(text="С багажом", callback_data="baggage_1")
    return builder.as_markup()


def _notify_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🌅 Утром (07:00)", callback_data="notify_7")
    builder.button(text="☀️ Днём (13:00)", callback_data="notify_13")
    builder.button(text="🌆 Вечером (19:00)", callback_data="notify_19")
    return builder.as_markup()


def _format_route(legs: list[dict]) -> str:
    parts = []
    for l in legs:
        seg = f"{l['origin']} → {l['destination']}"
        if l.get("transit_code"):
            seg += f" (через {l['transit_name'] or l['transit_code']})"
        parts.append(seg)
    return " → ".join(parts)


@router.callback_query(F.data == "add_route")
async def add_route_start(callback: CallbackQuery, state: FSMContext) -> None:
    config = load_config()
    await state.set_data({"legs": [], "_avia_token": config.avia_token or ""})
    await callback.message.edit_text("Введите город отправления:")
    await state.set_state(AddRoute.origin)
    await callback.answer()


@router.message(AddRoute.origin)
async def process_origin(message: Message, state: FSMContext) -> None:
    code = await resolve_city(message.text)
    if not code:
        await message.answer(
            "Не удалось найти такой город. Попробуйте иначе (например, «Москва»)."
        )
        return
    await state.update_data(origin=message.text.strip(), origin_code=code)
    await message.answer("Введите город назначения:")
    await state.set_state(AddRoute.destination)


@router.message(AddRoute.destination)
async def process_destination(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    code = await resolve_city(message.text)
    if not code:
        await message.answer("Не удалось найти такой город. Попробуйте иначе.")
        return
    origin_code = data.get("origin_code")
    dest_codes = [l["dest_code"] for l in data.get("legs", [])] + ([origin_code] if origin_code else [])
    if code == origin_code or code in dest_codes:
        await message.answer("Вы уже были в этом городе. Введите другой.")
        return
    await state.update_data(destination=message.text.strip(), dest_code=code)
    await message.answer("Введите дату вылета (ДД.ММ.ГГГГ):")
    await state.set_state(AddRoute.date)


@router.message(AddRoute.date)
async def process_date(message: Message, state: FSMContext) -> None:
    dt = _parse_date(message.text)
    if not dt:
        await message.answer("Неверный формат. Введите дату как ДД.ММ.ГГГГ (например, 15.06.2026):")
        return
    if dt.date() < datetime.now().date():
        await message.answer("Дата вылета уже прошла. Введите будущую дату.")
        return

    data = await state.get_data()
    legs = data.get("legs", [])
    if legs:
        prev_date = _parse_date(legs[-1]["date"])
        if prev_date and dt <= prev_date:
            await message.answer("Дата должна быть позже предыдущего сегмента.")
            return

    await state.update_data(_tmp_date=message.text.strip())
    await message.answer(
        "Введите город или страну пересадки (или '-' чтобы пропустить):\n"
        "Например: Дубай"
    )
    await state.set_state(AddRoute.transit)


@router.message(AddRoute.transit)
async def process_transit(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    raw = message.text.strip()
    transit_code = None
    transit_name = None

    if raw != "-":
        transit_code = await resolve_city(raw)
        if not transit_code:
            await message.answer(
                "Не удалось найти такой город. Введите снова или '-' чтобы пропустить:"
            )
            return
        transit_name = raw

    leg = {
        "origin": data["origin"],
        "origin_code": data["origin_code"],
        "destination": data["destination"],
        "dest_code": data["dest_code"],
        "date": data["_tmp_date"],
        "transit_code": transit_code,
        "transit_name": transit_name,
        "min_layover": None,
        "max_layover": None,
    }
    await state.update_data(_pending_leg=leg)

    if transit_code:
        await message.answer(
            "Введите мин. и макс. время пересадки в часах через пробел\n"
            "Например: 1 4 (от 1 до 4 часов) или '-' чтобы пропустить:"
        )
        await state.set_state(AddRoute.layover)
    else:
        await _finalize_leg(message, state, leg)


@router.message(AddRoute.layover)
async def process_layover(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    leg = data.get("_pending_leg")
    if not leg:
        await state.set_state(AddRoute.origin)
        await message.answer("Что-то пошло не так. Начните заново.")
        return

    raw = message.text.strip()
    if raw != "-":
        match = re.match(r"^\s*(\d+)\s+(\d+)\s*$", raw)
        if not match:
            await message.answer(
                "Введите два числа через пробел (мин макс) или '-':"
            )
            return
        min_h, max_h = int(match.group(1)), int(match.group(2))
        if min_h < 0 or max_h <= min_h:
            await message.answer("Минимум должен быть >= 0, максимум > минимума.")
            return
        leg["min_layover"] = min_h * 60
        leg["max_layover"] = max_h * 60

    await _finalize_leg(message, state, leg)


async def _finalize_leg(msg: Message, state: FSMContext, leg: dict) -> None:
    data = await state.get_data()
    legs = data.get("legs", [])
    legs.append(leg)
    await state.update_data(legs=legs)
    await state.update_data(origin=data["destination"], origin_code=data["dest_code"])
    await state.set_data({k: v for k, v in (await state.get_data()).items()
                          if k not in ("_tmp_date", "_pending_leg")})

    transit_info = ""
    if leg.get("transit_code"):
        transit_info = f" через {leg['transit_name'] or leg['transit_code']}"
    await msg.answer(
        f"Сегмент добавлен: {leg['origin']} → {leg['destination']} ({leg['date']}){transit_info}\n"
        "Добавить ещё один перелёт?",
        reply_markup=_yes_no_kb(),
    )
    await state.set_state(AddRoute.add_leg)


@router.callback_query(AddRoute.add_leg, F.data.in_({"leg_yes", "leg_no"}))
async def process_add_leg(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.data == "leg_yes":
        await callback.message.edit_text("Введите следующий город назначения:")
        await state.set_state(AddRoute.destination)
    else:
        await callback.message.edit_text("Введите количество пассажиров:")
        await state.set_state(AddRoute.passengers)
    await callback.answer()


@router.message(AddRoute.passengers)
async def process_passengers(message: Message, state: FSMContext) -> None:
    if not message.text.isdigit() or int(message.text) < 1:
        await message.answer("Введите число больше 0.")
        return
    await state.update_data(passengers=int(message.text))
    await message.answer(
        "Выберите тип багажа:",
        reply_markup=_baggage_kb(),
    )
    await state.set_state(AddRoute.baggage)


@router.callback_query(AddRoute.baggage, F.data.startswith("baggage_"))
async def process_baggage(callback: CallbackQuery, state: FSMContext) -> None:
    baggage = int(callback.data.split("_")[1])
    await state.update_data(baggage=baggage)
    await callback.message.edit_text(
        "Выберите удобное время для уведомлений:",
        reply_markup=_notify_kb(),
    )
    await state.set_state(AddRoute.notify_time)
    await callback.answer()


@router.callback_query(AddRoute.notify_time, F.data.startswith("notify_"))
async def process_notify_time(callback: CallbackQuery, state: FSMContext) -> None:
    hour = int(callback.data.split("_")[1])
    data = await state.update_data(notify_hour=hour)
    legs = data["legs"]
    avia_token = data.get("_avia_token", "")

    route_id = None
    try:
        route_id = await save_route(callback.from_user.id, data)
    except Exception:
        logging.exception("Ошибка сохранения маршрута")
        await callback.message.edit_text("Что-то пошло не так. Попробуйте позже.")
        await state.clear()
        await callback.answer()
        return

    await state.clear()

    baggage_label = "с багажом" if data.get("baggage") else "ручная кладь"
    await callback.message.edit_text(
        f"Маршрут сохранён!\n"
        f"{_format_route(legs)}\n"
        f"👤 {data['passengers']} чел.\n"
        f"🧳 {baggage_label}\n"
        "Ищу цены..."
    )

    if avia_token:
        logging.info("Проверка цены для %d сегментов, токен=%s...",
                     len(legs), avia_token[:8])
        total = 0.0
        for leg in legs:
            logging.info("Запрос цены: %s->%s (%s)",
                         leg["origin_code"], leg["dest_code"], leg["date"])
            price = await fetch_price(
                origin_code=leg["origin_code"],
                dest_code=leg["dest_code"],
                date_from=leg["date"],
                token=avia_token,
                one_way=True,
                baggage=data.get("baggage", 0),
                transit_code=leg.get("transit_code"),
                min_layover=leg.get("min_layover"),
                max_layover=leg.get("max_layover"),
            )
            if price is None:
                logging.warning("Цена не получена для сегмента %s->%s",
                                leg["origin_code"], leg["dest_code"])
                total = None
                break
            total += price
            logging.info("Цена сегмента: %.0f руб.", price)

        if total is not None:
            total *= data["passengers"]
            await callback.message.answer(
                f"💰 Текущая минимальная цена: {total:.0f} руб."
            )
            if route_id:
                async with get_db() as conn:
                    await conn.execute(
                        "UPDATE routes SET last_price = $1, last_checked = CURRENT_TIMESTAMP WHERE id = $2",
                        total, route_id,
                    )
        else:
            await callback.message.answer(
                "Не удалось получить цену. Попробуйте позже."
            )

    await callback.answer()


async def save_route(telegram_id: int, data: dict) -> int:
    async with get_db() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM users WHERE telegram_id = $1", telegram_id
        )
        if row:
            user_id = row["id"]
        else:
            user_id = await conn.fetchval(
                "INSERT INTO users (telegram_id) VALUES ($1) RETURNING id",
                telegram_id,
            )

        route_id = await conn.fetchval(
            "INSERT INTO routes (user_id, passengers, baggage, notify_hour) VALUES ($1, $2, $3, $4) RETURNING id",
            user_id, data["passengers"], data.get("baggage", 0), data.get("notify_hour", 10),
        )

        for i, leg in enumerate(data["legs"]):
            await conn.execute(
                """
                INSERT INTO segments
                    (route_id, origin, origin_code, destination, dest_code,
                     date, sort_order, transit_code, transit_name,
                     min_layover, max_layover)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                route_id,
                leg["origin"],
                leg["origin_code"],
                leg["destination"],
                leg["dest_code"],
                leg["date"],
                i + 1,
                leg.get("transit_code"),
                leg.get("transit_name"),
                leg.get("min_layover"),
                leg.get("max_layover"),
            )
        return route_id
