# main.py

import asyncio
import logging

from database import init_db, close_db
from config.config_bot import bot, dp
import show_handlers as router_show
import zapret_handlers as router_zapret
import ban_handlers as router_ban
import mute_handlers as router_mute
import podozr_handlers as router_podozr
import ero_handlers as router_ero
from middlewares.anti_spam import AntiSpamMiddleware


async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()  # Инициализируем базу данных и загружаем запрещённые слова
    dp.include_router(router_show.router)
    dp.include_router(router_zapret.router)
    dp.include_router(router_ban.router)
    dp.include_router(router_mute.router)
    dp.include_router(router_podozr.router)
    dp.include_router(router_ero.router)

    # Подключаем мидлвар
    dp.message.middleware(AntiSpamMiddleware())

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)
    # await stress_test(bot, dp)
    
    # # Закрываем сессию бота
    # await bot.session.close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Bot closed')
    finally:
        asyncio.run(close_db())
