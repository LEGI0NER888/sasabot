from aiogram import Bot, Dispatcher
from dotenv import dotenv_values
from aiogram.fsm.storage.memory import MemoryStorage

config = dotenv_values("./config/.env")
API_TOKEN = config['TOKEN']
GROUP_ID = int(config['GROUP_ID'])
CHANNEL_ID = int(config['CHANNEL_ID'])
ADMINS = config['ADMINS']
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
MODERS = config['MODERS']
