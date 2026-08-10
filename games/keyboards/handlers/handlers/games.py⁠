from aiogram import Router, F
from aiogram.types import CallbackQuery

router = Router()

@router.callback_query(F.data.startswith("game_"))
async def process_game_click(callback: CallbackQuery):
    game_type = callback.data.split("_")[1]
    await callback.message.answer(f"🎮 Игра {game_type.upper()} запущена! Сделайте ставку.")
    await callback.answer()
