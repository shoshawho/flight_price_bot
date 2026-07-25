import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from app.api.iata import resolve_city
from app.database import get_db

router = Router()


class AddRoute(StatesGroup):
    origin = State()
    destination = State()
    date_from = State()
    date_to = State()
    passengers = State()


def _parse_date(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw.strip(), "%d.%m.%Y")
    except ValueError:
        return None


@router.callback_query(F.data == "add_route")
async def add_route_start(callback: CallbackQuery, state: FSMContext) -> None:
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
        await message.answer(
            "Не удалось найти такой город. Попробуйте иначе."
        )
        return
    if code == data.get("origin_code"):
        await message.answer("Город назначения совпадает с отправлением. Введите другой.")
        return
    await state.update_data(destination=message.text.strip(), dest_code=code)
    await message.answer("Введите дату вылета (ДД.ММ.ГГГГ):")
    await state.set_state(AddRoute.date_from)


@router.message(AddRoute.date_from)
async def process_date_from(message: Message, state: FSMContext) -> None:
    dt = _parse_date(message.text)
    if not dt:
        await message.answer("Неверный формат. Введите дату как ДД.ММ.ГГГГ (например, 15.06.2026):")
        return
    if dt.date() < datetime.now().date():
        await message.answer("Дата вылета уже прошла. Введите будущую дату.")
        return
    await state.update_data(date_from=message.text.strip(), _dt_from=dt)
    await message.answer("Введите дату возвращения (ДД.ММ.ГГГГ):")
    await state.set_state(AddRoute.date_to)


@router.message(AddRoute.date_to)
async def process_date_to(message: Message, state: FSMContext) -> None:
    dt = _parse_date(message.text)
    if not dt:
        await message.answer("Неверный формат. Введите дату как ДД.ММ.ГГГГ:")
        return
    data = await state.get_data()
    dt_from = data.get("_dt_from")
    if dt_from and dt <= dt_from:
        await message.answer("Дата возвращения должна быть позже даты вылета.")
        return
    await state.update_data(date_to=message.text.strip())
    await message.answer("Введите количество пассажиров:")
    await state.set_state(AddRoute.passengers)


@router.message(AddRoute.passengers)
async def process_passengers(message: Message, state: FSMContext) -> None:
    if not message.text.isdigit() or int(message.text) < 1:
        await message.answer("Введите число больше 0.")
        return
    data = await state.update_data(passengers=int(message.text))
    data.pop("_dt_from", None)

    try:
        await save_route(message.from_user.id, data)
    except Exception:
        logging.exception("Ошибка сохранения маршрута")
        await message.answer("Что-то пошло не так. Попробуйте позже.")
        await state.clear()
        return

    await state.clear()
    await message.answer(
        f"Маршрут сохранён!\n"
        f"{data['origin']} → {data['destination']}\n"
        f"{data['date_from']} – {data['date_to']}\n"
        f"👤 {data['passengers']} чел.\n"
        "Буду следить за ценой."
    )


async def save_route(telegram_id: int, data: dict) -> None:
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

        await db.execute(
            """
            INSERT INTO routes
                (user_id, origin, origin_code, destination, dest_code,
                 date_from, date_to, passengers)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                data["origin"],
                data["origin_code"],
                data["destination"],
                data["dest_code"],
                data["date_from"],
                data["date_to"],
                data["passengers"],
            ),
        )
        await db.commit()
