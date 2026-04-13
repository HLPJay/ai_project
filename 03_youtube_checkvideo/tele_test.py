# test_bot2.py
import asyncio
import httpx
from telegram import Bot
from telegram.request import HTTPXRequest

BOT_TOKEN = "8733793389:AAG2xAA2U9UX9gd8zs_LAqq4zAt21lPGHkY"
PROXY_URL = "http://127.0.0.1:7888"

async def test():
    print("开始连接...")
    request = HTTPXRequest(proxy=PROXY_URL)
    bot = Bot(token=BOT_TOKEN, request=request)
    try:
        me = await asyncio.wait_for(bot.get_me(), timeout=15)
        print(f"✅ 连接成功：@{me.username}")
    except asyncio.TimeoutError:
        print("❌ 超时")
    except Exception as e:
        print(f"❌ 错误：{type(e).__name__}: {e}")
    finally:
        await bot.shutdown()

asyncio.run(test())