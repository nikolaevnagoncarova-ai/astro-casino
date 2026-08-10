import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import asyncio
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# База данных прямо здесь
DATABASE_URL = "sqlite+aiosqlite:///./test.db"
engine = create_async_engine(DATABASE_URL, echo=True)
Base = declarative_base()

# Настройки
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL", "")

app = FastAPI()
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)) if BOT_TOKEN else None
dp = Dispatcher()

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
