import os
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import BigInteger, Integer

TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# База данных
DATABASE_URL = "sqlite+aiosqlite:///database.db"
engine = create_async_engine(DATABASE_URL, echo=True)
async_session = async_sessionmaker(engine, expire_on_commit=False)

class Base(AsyncAttrs, DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    balance: Mapped[int] = mapped_column(Integer, default=1000)

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    if WEBHOOK_URL and bot:
        await bot.set_webhook(f"{WEBHOOK_URL}/webhook")

@app.post("/webhook")
async def webhook(request: Request):
    if bot:
        update = types.Update(**await request.json())
        await dp.feed_update(bot, update)
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"message": "Bot is running"}

# Обработчик команды /start
@dp.message(types.Command("start"))
async def cmd_start(message: types.Message):
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="🎰 Играть в слоты", callback_data="play_slots")],
            [types.InlineKeyboardButton(text="👤 Профиль", callback_data="profile")]
        ]
    )
    
    await message.answer(
        "<b>Добро пожаловать в Astro Casino</b>\n\n"
        "Элегантная атмосфера, высокие ставки и чистый азарт. "
        "Здесь звезды сходятся в твою пользу, а расчет и удача идут рука об руку.\n\n"
        "👉 Выберите раздел для начала игры:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
