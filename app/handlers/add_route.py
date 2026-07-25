import logging
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
    add_leg = State()
    passengers = State()
    baggage = State()


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

    leg = {
        "origin": data["origin"],
        "origin_code": data["origin_code"],
        "destination": data["destination"],
        "dest_code": data["dest_code"],
        "date": message.text.strip(),
    }
    legs.append(leg)
    await state.update_data(legs=legs)
    await state.update_data(origin=data["destination"], origin_code=data["dest_code"])
    await message.answer(
        f"Сегмент добавлен: {leg['origin']} → {leg['destination']} ({leg['date']})\n"
        "Добавить ещё один перелёт?",
        reply_markup=_yes_no_kb(),
    )
    await state.set_state(AddRoute.add_leg)


@router.callback_query(AddRoute.add_leg)
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


@router.callback_query(AddRoute.baggage)
async def process_baggage(callback: CallbackQuery, state: FSMContext) -> None:
    baggage = int(callback.data.split("_")[1])
    data = await state.update_data(baggage=baggage)
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

    route_str = " → ".join(f"{l['origin']}→{l['destination']}" for l in legs)
    baggage_label = "с багажом" if baggage else "ручная кладь"
    await callback.message.edit_text(
        f"Маршрут сохранён!\n"
        f"{route_str}\n"
        f"👤 {data['passengers']} чел.\n"
        f"🧳 {baggage_label}\n"
        "Ищу цены..."
    )

    if avia_token:
        total = 0.0
        for leg in legs:
            price = await fetch_price(
                origin_code=leg["origin_code"],
                dest_code=leg["dest_code"],
                date_from=leg["date"],
                token=avia_token,
                one_way=True,
                baggage=baggage,
            )
            if price is None:
                total = None
                break
            total += price

        if total is not None:
            total *= data["passengers"]
            await callback.message.answer(
                f"💰 Текущая минимальная цена: {total:.0f} руб."
            )
            if route_id:
                async with get_db() as db:
                    await db.execute(
                        "UPDATE routes SET last_price = ? WHERE id = ?",
                        (total, route_id),
                    )
                    await db.commit()
        else:
            await callback.message.answer(
                "Не удалось получить цену. Попробуйте позже или проверьте логи."
            )

    await callback.answer()


async def save_route(telegram_id: int, data: dict) -> int:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cursor.fetchone()
        if row:
            user_id = row[0]
        else:
            cursor = await db.execute(
                "INSERT INTO users (telegram_id) VALUES (?)", (telegram_id,)
            )
            user_id = cursor.lastrowid

        cursor = await db.execute(
            "INSERT INTO routes (user_id, passengers, baggage) VALUES (?, ?, ?)",
            (user_id, data["passengers"], data.get("baggage", 0)),
        )
        route_id = cursor.lastrowid

        for i, leg in enumerate(data["legs"]):
            await db.execute(
                """
                INSERT INTO segments
                    (route_id, origin, origin_code, destination, dest_code, date, sort_order)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    route_id,
                    leg["origin"],
                    leg["origin_code"],
                    leg["destination"],
                    leg["dest_code"],
                    leg["date"],
                    i + 1,
                ),
            )
        await db.commit()
        return route_id
