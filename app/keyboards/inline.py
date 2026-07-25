from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Добавить маршрут", callback_data="add_route")
    )
    builder.row(
        InlineKeyboardButton(text="Мои маршруты", callback_data="my_routes")
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Обновить цены", callback_data="refresh_prices")
    )
    return builder.as_markup()
