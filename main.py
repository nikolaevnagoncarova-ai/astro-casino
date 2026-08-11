import os
import time
import random
import html
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import BigInteger, Integer, String, select, text

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL")

# Безопасное чтение ADMIN_ID
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0").strip())
except ValueError:
    ADMIN_ID = 0

bot = Bot(token=TOKEN) if TOKEN else None
dp = Dispatcher(storage=MemoryStorage())

# --- БАЗА ДАННЫХ ---
DATABASE_URL = "sqlite+aiosqlite:///database.db"
engine = create_async_engine(
    DATABASE_URL, 
    echo=False, 
    connect_args={"timeout": 30}
)
async_session = async_sessionmaker(engine, expire_on_commit=False)

class Base(AsyncAttrs, DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    balance: Mapped[int] = mapped_column(BigInteger, default=10000000)  # 10M
    current_bet: Mapped[int] = mapped_column(BigInteger, default=1000000)  # 1M
    games_played: Mapped[int] = mapped_column(Integer, default=0)
    games_won: Mapped[int] = mapped_column(Integer, default=0)
    last_bonus: Mapped[int] = mapped_column(BigInteger, default=0)

class Promo(Base):
    __tablename__ = "promos"
    
    code: Mapped[str] = mapped_column(String, primary_key=True)
    reward: Mapped[int] = mapped_column(BigInteger)
    uses_left: Mapped[int] = mapped_column(Integer)

class UsedPromo(Base):
    __tablename__ = "used_promos"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    code: Mapped[str] = mapped_column(String)

# FSM Состояния
class Form(StatesGroup):
    waiting_for_promo = State()

# --- ВЫНЕCЕНИЕ ИНИЦИАЛИЗАЦИИ БД И ВЕБХУКАВ LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Настройка PRAGMA journal_mode ВНЕ транзакции (решает баг SQLite)
    async with engine.connect() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL;"))
        await conn.commit()
        
    # 2. Создание таблиц
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    # 3. Регистрация Webhook
    if WEBHOOK_URL and bot:
        webhook_path = f"{WEBHOOK_URL.rstrip('/')}/webhook"
        await bot.set_webhook(webhook_path)
        
    yield
    
    # 4. Корректное завершение ресурсов
    if bot:
        await bot.session.close()
    await engine.dispose()

app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def webhook(request: Request):
    if bot:
        try:
            data = await request.json()
            update = types.Update.model_validate(data, context={"bot": bot})
            await dp.feed_update(bot, update)
        except Exception as e:
            logging.error(f"Error handling webhook update: {e}")
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"message": "Astro Casino Bot is running"}

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def fmt(amount: int) -> str:
    """Красивое форматирование чисел с пробелами (10 000 000)."""
    return f"{amount:,}".replace(",", " ")

async def get_or_create_user_session(session, user_id: int) -> User:
    user = await session.get(User, user_id)
    if not user:
        user = User(id=user_id, balance=10000000, current_bet=1000000, games_played=0, games_won=0, last_bonus=0)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user

def get_main_keyboard():
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="🎰 Слоты", callback_data="game_slots"),
                types.InlineKeyboardButton(text="🪙 Орел/Решка", callback_data="menu_coinflip")
            ],
            [
                types.InlineKeyboardButton(text="🎲 Кости", callback_data="game_dice"),
                types.InlineKeyboardButton(text="⚙️ Ставка", callback_data="menu_bet")
            ],
            [
                types.InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
                types.InlineKeyboardButton(text="🏆 Топ игроков", callback_data="top_players")
            ],
            [
                types.InlineKeyboardButton(text="🎁 Бонус", callback_data="daily_bonus"),
                types.InlineKeyboardButton(text="🎟 Промокод", callback_data="use_promo")
            ]
        ]
    )

async def safe_edit_text(callback: types.CallbackQuery, text: str, reply_markup=None):
    """Безопасное редактирование сообщений с защитой от ошибок Telegram API."""
    if not callback.message:
        return
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except TelegramBadRequest as e:
        err_msg = str(e).lower()
        if "message is not modified" not in err_msg and "message to edit not found" not in err_msg and "message can't be edited" not in err_msg:
            raise e

async def render_menu_bet(callback: types.CallbackQuery):
    async with async_session() as session:
        user = await get_or_create_user_session(session, callback.from_user.id)
        
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(text="500 000", callback_data="set_bet_500000"),
                    types.InlineKeyboardButton(text="1 000 000", callback_data="set_bet_1000000")
                ],
                [
                    types.InlineKeyboardButton(text="5 000 000", callback_data="set_bet_5000000"),
                    types.InlineKeyboardButton(text="10 000 000", callback_data="set_bet_10000000")
                ],
                [
                    types.InlineKeyboardButton(text="🔥 ALL IN", callback_data="set_bet_allin")
                ],
                [types.InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
            ]
        )
        
        text = (
            f"⚙️ <b>Настройка размера ставки</b>\n\n"
            f"Ваш текущий баланс: <code>{fmt(user.balance)}</code> AstroCoins\n"
            f"Текущая ставка: <code>{fmt(user.current_bet)}</code> AstroCoins\n\n"
            f"Выберите новый размер ставки:"
        )
    await safe_edit_text(callback, text, reply_markup=keyboard)

# --- КОМАНДА /START И ГЛАВНОЕ МЕНЮ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        user = await get_or_create_user_session(session, message.from_user.id)
        user_name = html.escape(message.from_user.first_name or "Игрок")
        
        text = (
            f"✨ <b>ASTRO CASINO HIGH ROLLER</b> ✨\n\n"
            f"👋 Добро пожаловать, <b>{user_name}</b>!\n"
            f"Испытай свою удачу на крупных ставках.\n\n"
            f"💰 <b>Баланс:</b> <code>{fmt(user.balance)}</code> AstroCoins\n"
            f"🎯 <b>Текущая ставка:</b> <code>{fmt(user.current_bet)}</code> AstroCoins\n\n"
            f"👇 Выберите раздел из меню ниже:"
        )
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="HTML")

@dp.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    async with async_session() as session:
        user = await get_or_create_user_session(session, callback.from_user.id)
        text = (
            f"✨ <b>ASTRO CASINO — Главное Меню</b> ✨\n\n"
            f"💰 <b>Баланс:</b> <code>{fmt(user.balance)}</code> AstroCoins\n"
            f"🎯 <b>Текущая ставка:</b> <code>{fmt(user.current_bet)}</code> AstroCoins\n\n"
            f"👇 Выберите игру или раздел:"
        )
    await safe_edit_text(callback, text, reply_markup=get_main_keyboard())

# --- МЕНЮ УПРАВЛЕНИЯ СТАВКОЙ ---
@dp.callback_query(F.data == "menu_bet")
async def menu_bet_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await render_menu_bet(callback)

@dp.callback_query(F.data.startswith("set_bet_"))
async def set_bet_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    bet_value = callback.data.replace("set_bet_", "")
    
    async with async_session() as session:
        user = await get_or_create_user_session(session, callback.from_user.id)

        if bet_value == "allin":
            user.current_bet = max(1, user.balance) if user.balance > 0 else 1
        else:
            try:
                user.current_bet = int(bet_value)
            except ValueError:
                user.current_bet = 1000000
            
        await session.commit()
        new_bet = user.current_bet

    await callback.answer(f"✅ Ставка изменена на {fmt(new_bet)} AstroCoins!", show_alert=True)
    await render_menu_bet(callback)

# --- ИГРА 1: СЛОТЫ ---
@dp.callback_query(F.data == "game_slots")
async def game_slots_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        user = await get_or_create_user_session(session, callback.from_user.id)
        
        if user.balance < user.current_bet or user.current_bet <= 0:
            await callback.answer("❌ Недостаточно средств для этой ставки!", show_alert=True)
            return

        user.balance -= user.current_bet
        user.games_played += 1
        await session.commit()

        symbols = ["7️⃣", "💎", "🔔", "🍋", "🍒"]
        s1, s2, s3 = random.choice(symbols), random.choice(symbols), random.choice(symbols)

        if s1 == s2 == s3:
            multiplier = 10 if s1 == "7️⃣" else 5
        elif s1 == s2 or s2 == s3 or s1 == s3:
            multiplier = 2
        else:
            multiplier = 0

        if multiplier > 0:
            win_amount = user.current_bet * multiplier
            user.balance += win_amount
            user.games_won += 1
            result_msg = f"🎉 <b>ДЖЕКПОТ x{multiplier}!</b>\n➕ Выигрыш: <b>+{fmt(win_amount)}</b> AstroCoins!"
        else:
            result_msg = f"😢 <b>Не повезло!</b>\n➖ Минус: <b>-{fmt(user.current_bet)}</b> AstroCoins"

        await session.commit()
        current_balance = user.balance
        current_bet = user.current_bet

    await callback.answer()
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="🔄 Крутить еще", callback_data="game_slots")],
            [types.InlineKeyboardButton(text="⚙️ Изменить ставку", callback_data="menu_bet")],
            [types.InlineKeyboardButton(text="🔙 В главное меню", callback_data="main_menu")]
        ]
    )
    
    text = (
        f"🎰 <b>АСТРО СЛОТЫ</b>\n\n"
        f"┌───────────────┐\n"
        f"│  {s1} │ {s2} │ {s3}  │\n"
        f"└───────────────┘\n\n"
        f"{result_msg}\n\n"
        f"💰 Баланс: <code>{fmt(current_balance)}</code>\n"
        f"🎯 Ставка: <code>{fmt(current_bet)}</code>"
    )
    await safe_edit_text(callback, text, reply_markup=keyboard)

# --- ИГРА 2: ОРЕЛ И РЕШКА ---
@dp.callback_query(F.data == "menu_coinflip")
async def menu_coinflip_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    async with async_session() as session:
        user = await get_or_create_user_session(session, callback.from_user.id)
        balance = user.balance
        bet = user.current_bet

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="🦅 Орел", callback_data="play_coin_heads"),
                types.InlineKeyboardButton(text="🪙 Решка", callback_data="play_coin_tails")
            ],
            [types.InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
        ]
    )
    text = (
        f"🪙 <b>ОРЕЛ ИЛИ РЕШКА</b>\n\n"
        f"Удваивайте ставки в 1 клик!\n\n"
        f"💰 Баланс: <code>{fmt(balance)}</code>\n"
        f"🎯 Ставка: <code>{fmt(bet)}</code>\n\n"
        f"Сделайте ваш выбор:"
    )
    await safe_edit_text(callback, text, reply_markup=keyboard)

@dp.callback_query(F.data.startswith("play_coin_"))
async def play_coin_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    choice = callback.data.replace("play_coin_", "")
    
    async with async_session() as session:
        user = await get_or_create_user_session(session, callback.from_user.id)

        if user.balance < user.current_bet or user.current_bet <= 0:
            await callback.answer("❌ Недостаточно средств на балансе!", show_alert=True)
            return

        user.balance -= user.current_bet
        user.games_played += 1
        await session.commit()

        outcome = random.choice(["heads", "tails"])
        side_text = "🦅 Орел" if outcome == "heads" else "🪙 Решка"
        
        if choice == outcome:
            win_amount = user.current_bet * 2
            user.balance += win_amount
            user.games_won += 1
            res = f"🎉 Вы угадали! Выпал {side_text}.\n➕ Выиграно: <b>+{fmt(win_amount)}</b> AstroCoins!"
        else:
            res = f"😢 Выпал {side_text}.\n➖ Проиграно: <b>-{fmt(user.current_bet)}</b> AstroCoins"

        await session.commit()
        current_balance = user.balance

    await callback.answer()
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="🔄 Бросить снова", callback_data="menu_coinflip")],
            [types.InlineKeyboardButton(text="🔙 В меню", callback_data="main_menu")]
        ]
    )
    
    text = (
        f"🪙 <b>РЕЗУЛЬТАТ БРОСКА</b>\n\n"
        f"{res}\n\n"
        f"💰 Ваш баланс: <code>{fmt(current_balance)}</code> AstroCoins"
    )
    await safe_edit_text(callback, text, reply_markup=keyboard)

# --- ИГРА 3: КОСТИ ---
@dp.callback_query(F.data == "game_dice")
async def game_dice_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        user = await get_or_create_user_session(session, callback.from_user.id)

        if user.balance < user.current_bet or user.current_bet <= 0:
            await callback.answer("❌ Недостаточно средств!", show_alert=True)
            return

        user.balance -= user.current_bet
        user.games_played += 1
        await session.commit()

        user_score = random.randint(1, 6)
        casino_score = random.randint(1, 6)
        
        if user_score > casino_score:
            win_amount = user.current_bet * 2
            user.balance += win_amount
            user.games_won += 1
            res_text = f"🏆 <b>Победа!</b>\n➕ Забрали: <b>+{fmt(win_amount)}</b> AstroCoins"
        elif user_score < casino_score:
            res_text = f"❌ <b>Поражение!</b>\n➖ Потеряно: <b>-{fmt(user.current_bet)}</b> AstroCoins"
        else:
            user.balance += user.current_bet
            res_text = "🤝 <b>Ничья!</b> Ставка возвращена."

        await session.commit()
        current_balance = user.balance

    await callback.answer()
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="🎲 Бросить еще раз", callback_data="game_dice")],
            [types.InlineKeyboardButton(text="🔙 В главное меню", callback_data="main_menu")]
        ]
    )
    
    text = (
        f"🎲 <b>КОСТИ</b>\n\n"
        f"👤 Ваш бросок: <b>[{user_score}]</b>\n"
        f"🎰 Бросок казино: <b>[{casino_score}]</b>\n\n"
        f"{res_text}\n\n"
        f"💰 Баланс: <code>{fmt(current_balance)}</code>"
    )
    await safe_edit_text(callback, text, reply_markup=keyboard)

# --- ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ ---
@dp.callback_query(F.data == "profile")
async def profile_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    async with async_session() as session:
        user = await get_or_create_user_session(session, callback.from_user.id)
        
        winrate = 0
        if user.games_played > 0:
            winrate = round((user.games_won / user.games_played) * 100, 1)

        text = (
            f"👤 <b>ВАШ ИГРОВОЙ ПРОФИЛЬ</b>\n\n"
            f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
            f"💰 <b>Баланс:</b> <code>{fmt(user.balance)}</code> AstroCoins\n"
            f"🎯 <b>Текущая ставка:</b> <code>{fmt(user.current_bet)}</code> AstroCoins\n\n"
            f"📊 <b>Статистика:</b>\n"
            f"▫️ Сыграно игр: <b>{user.games_played}</b>\n"
            f"▫️ Побед: <b>{user.games_won}</b>\n"
            f"▫️ Процент побед: <b>{winrate}%</b>"
        )
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]]
    )
    await safe_edit_text(callback, text, reply_markup=keyboard)

# --- ТОП ИГРОКОВ ---
@dp.callback_query(F.data == "top_players")
async def top_players_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    async with async_session() as session:
        result = await session.execute(select(User).order_by(User.balance.desc()).limit(5))
        top_users = result.scalars().all()

    text = "🏆 <b>ТОП-5 МИЛЛИОНЕРОВ ASTRO CASINO</b>\n\n"
    if not top_users:
        text += "<i>Пока нет активных игроков. Станьте первым!</i>"
    else:
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for i, u in enumerate(top_users):
            text += f"{medals[i]} ID <code>{u.id}</code> — <b>{fmt(u.balance)}</b> AstroCoins\n"

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]]
    )
    await safe_edit_text(callback, text, reply_markup=keyboard)

# --- ЕЖЕДНЕВНЫЙ БОНУС С ТОЧНЫМ ТАЙМЕРОМ ---
@dp.callback_query(F.data == "daily_bonus")
async def daily_bonus_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    bonus_amount = 2500000  # 2.5M
    now = int(time.time())
    cooldown = 86400  # 24 часа

    async with async_session() as session:
        user = await get_or_create_user_session(session, callback.from_user.id)
        
        time_passed = now - user.last_bonus
        if time_passed < cooldown:
            rem = cooldown - time_passed
            hours = rem // 3600
            minutes = (rem % 3600) // 60
            seconds = rem % 60
            
            if hours > 0:
                time_str = f"{hours} ч {minutes} мин"
            elif minutes > 0:
                time_str = f"{minutes} мин {seconds} сек"
            else:
                time_str = f"{seconds} сек"

            await callback.answer(f"⏳ Бонус уже получен! Приходите через {time_str}.", show_alert=True)
            return

        user.balance += bonus_amount
        user.last_bonus = now
        await session.commit()
        new_balance = user.balance

    await callback.answer()
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text="🔙 В главное меню", callback_data="main_menu")]]
    )
    text = (
        f"🎁 <b>ЕЖЕДНЕВНЫЙ БОНУС!</b>\n\n"
        f"Зачислено: <b>+{fmt(bonus_amount)} AstroCoins</b>\n"
        f"💰 Ваш баланс: <code>{fmt(new_balance)}</code> AstroCoins\n\n"
        f"⏱ Следующий бонус будет доступен через 24 часа."
    )
    await safe_edit_text(callback, text, reply_markup=keyboard)

# --- АКТИВАЦИЯ ПРОМОКОДОВ ---
@dp.callback_query(F.data == "use_promo")
async def use_promo_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_promo)
    await callback.answer()
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")]]
    )
    await safe_edit_text(
        callback,
        "🎟 <b>Введите промокод:</b>\nОтправьте кодовое слово в чат.",
        reply_markup=keyboard
    )

@dp.message(Form.waiting_for_promo)
async def process_promo_code(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Пожалуйста, отправьте промокод текстовым сообщением.")
        return

    raw_code = message.text.strip().upper()
    user_id = message.from_user.id
    await state.clear()

    async with async_session() as session:
        used_stmt = select(UsedPromo).where(UsedPromo.user_id == user_id, UsedPromo.code == raw_code)
        already_used = (await session.execute(used_stmt)).scalar_one_or_none()
        
        if already_used:
            await message.answer("❌ Вы уже активировали этот промокод!", reply_markup=get_main_keyboard())
            return

        promo = await session.get(Promo, raw_code)
        if not promo or promo.uses_left <= 0:
            await message.answer("❌ Промокод не существует или закончились активации.", reply_markup=get_main_keyboard())
            return
        
        user = await get_or_create_user_session(session, user_id)
        user.balance += promo.reward
        promo.uses_left -= 1
        
        session.add(UsedPromo(user_id=user_id, code=raw_code))
        await session.commit()
        new_balance = user.balance

    await message.answer(
        f"🎉 <b>Промокод активирован!</b>\n"
        f"➕ Зачислено: <b>+{fmt(promo.reward)} AstroCoins</b>\n"
        f"💰 Новый баланс: <code>{fmt(new_balance)}</code>",
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )

# --- АДМИН ПАНЕЛЬ ---
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    text = (
        "🛠 <b>АДМИН-ПАНЕЛЬ КАЗИНО</b>\n\n"
        "👑 Команды управления:\n"
        "• <code>/give ID СУММА</code> — выдать баланс\n"
        "• <code>/take ID СУММА</code> — забрать баланс\n"
        "• <code>/addpromo КОД СУММА ИСПОЛЬЗОВАНИЙ</code> — создать промокод\n"
        "• <code>/stats</code> — общая статистика"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("addpromo"))
async def cmd_addpromo(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    args = message.text.split()
    if len(args) != 4:
        await message.answer("Пример: <code>/addpromo VIP10M 10000000 5</code>", parse_mode="HTML")
        return

    try:
        code, reward, uses = args[1].upper(), int(args[2]), int(args[3])
        if reward <= 0 or uses <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("❌ Сумма и количество использований должны быть положительными числами!")
        return

    async with async_session() as session:
        existing_promo = await session.get(Promo, code)
        if existing_promo:
            await message.answer(f"❌ Промокод <code>{html.escape(code)}</code> уже существует!", parse_mode="HTML")
            return

        new_promo = Promo(code=code, reward=reward, uses_left=uses)
        session.add(new_promo)
        await session.commit()

    escaped_code = html.escape(code)
    await message.answer(f"✅ Промокод <code>{escaped_code}</code> создан на {fmt(reward)} монет ({uses} активаций)!", parse_mode="HTML")

@dp.message(Command("give"))
async def cmd_give(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("Пример: <code>/give 12345678 5000000</code>", parse_mode="HTML")
        return

    try:
        target_id, amount = int(args[1]), int(args[2])
        if amount <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("❌ ID и сумма должны быть положительными целыми числами!")
        return

    async with async_session() as session:
        user = await get_or_create_user_session(session, target_id)
        user.balance += amount
        await session.commit()
        await message.answer(f"✅ Выдано {fmt(amount)} монет для ID <code>{target_id}</code>!", parse_mode="HTML")

@dp.message(Command("take"))
async def cmd_take(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("Пример: <code>/take 12345678 1000000</code>", parse_mode="HTML")
        return

    try:
        target_id, amount = int(args[1]), int(args[2])
        if amount <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("❌ ID и сумма должны быть положительными целыми числами!")
        return

    async with async_session() as session:
        user = await session.get(User, target_id)
        if user:
            user.balance = max(0, user.balance - amount)
            await session.commit()
            await message.answer(f"✅ Списано {fmt(amount)} монет у ID <code>{target_id}</code>!", parse_mode="HTML")
        else:
            await message.answer("❌ Пользователь с таким ID не найден.")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    async with async_session() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        total_users = len(users)
        total_balance = sum(u.balance for u in users)

    await message.answer(
        f"📊 <b>СТАТИСТИКА КАЗИНО</b>\n\n"
        f"👥 Всего пользователей: <b>{total_users}</b>\n"
        f"💰 Монет в системе: <b>{fmt(total_balance)} AstroCoins</b>",
        parse_mode="HTML"
    )
