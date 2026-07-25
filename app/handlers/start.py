from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.keyboards.inline import main_menu

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Я помогу отслеживать цены на авиабилеты.\n"
        "Используй меню ниже:",
        reply_markup=main_menu(),
    )
