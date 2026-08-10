from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_main_keyboard():
    kb = [
        [InlineKeyboardButton(text="🎰 Слоты", callback_data="game_slots"),
         InlineKeyboardButton(text="🚀 Краш", callback_data="game_crash")],
        [InlineKeyboardButton(text="🎲 Кости", callback_data="game_dice"),
         InlineKeyboardButton(text="🪙 Монетка", callback_data="game_coin")],
        [InlineKeyboardButton(text="💼 Профиль", callback_data="profile")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)
