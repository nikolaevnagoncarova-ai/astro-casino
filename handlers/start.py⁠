from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandStart
from keyboards.ui import get_main_keyboard

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "✨ Добро пожаловать в Astro Casino!\nВыберите игру из меню ниже:",
        reply_markup=get_main_keyboard()
    )
