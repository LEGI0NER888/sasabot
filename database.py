# database.py
import logging
import aiosqlite
import asyncio
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаем глобальное соединение с базой данных
db_connection = None

# Асинхронные блокировки для кэшей
cache_lock = asyncio.Lock()

# Кэши для запрещённых слов и настроек
forbidden_words_cache = set()
settings_cache = {}

# Функция для инициализации базы данных и загрузки данных
async def init_db():
    global db_connection
    db_connection = await aiosqlite.connect('forbidden_words.db')

    # Создание таблиц
    await db_connection.execute('''
        CREATE TABLE IF NOT EXISTS forbidden_words (
            word TEXT PRIMARY KEY
        )
    ''')

    await db_connection.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            mute_count INTEGER DEFAULT 0,
            last_mute_time TEXT
        )
    ''')

    await db_connection.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')

    await db_connection.commit()

    # Инициализируем кэши
    await load_forbidden_words()
    await load_settings()

    if 'anti_spam_enabled' not in settings_cache:
        await update_setting('anti_spam_enabled', '1')

async def close_db():
    await db_connection.close()
    logger.info("Соединение с базой данных закрыто.")

# Функции для работы с запрещёнными словами

async def load_forbidden_words():
    async with cache_lock:
        forbidden_words_cache.clear()
        async with db_connection.execute('SELECT word FROM forbidden_words') as cursor:
            async for row in cursor:
                forbidden_words_cache.add(row[0])
    # logger.info(f"Загружены запрещённые слова: {forbidden_words_cache}")

async def get_forbidden_words():
    async with cache_lock:
        return forbidden_words_cache.copy()

async def add_forbidden_word(word):
    word_lower = word.lower()
    async with cache_lock:
        if word_lower not in forbidden_words_cache:
            await db_connection.execute('INSERT OR IGNORE INTO forbidden_words (word) VALUES (?)', (word_lower,))
            await db_connection.commit()
            forbidden_words_cache.add(word_lower)
            logger.info(f"Добавлено запрещённое слово: {word_lower}")

async def remove_forbidden_word(word):
    word_lower = word.lower()
    async with cache_lock:
        if word_lower in forbidden_words_cache:
            await db_connection.execute('DELETE FROM forbidden_words WHERE word = ?', (word_lower,))
            await db_connection.commit()
            forbidden_words_cache.remove(word_lower)
            logger.info(f"Удалено запрещённое слово: {word_lower}")

async def clear_forbidden_words():
    async with cache_lock:
        await db_connection.execute('DELETE FROM forbidden_words')
        await db_connection.commit()
        forbidden_words_cache.clear()
        logger.info("Очищен список запрещённых слов.")

# Функции для работы с настройками

async def load_settings():
    async with cache_lock:
        settings_cache.clear()
        async with db_connection.execute('SELECT key, value FROM settings') as cursor:
            async for row in cursor:
                settings_cache[row[0]] = row[1]
    # logger.info(f"Загружены настройки: {settings_cache}")

async def get_setting(key):
    async with cache_lock:
        return settings_cache.get(key)

async def update_setting(key, value):
    async with cache_lock:
        settings_cache[key] = value
        await db_connection.execute('''
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        ''', (key, value))
        await db_connection.commit()
    logger.info(f"Обновлено значение настройки: {key} = {value}")

# Функции для работы с пользователями

async def get_user(user_id):
    async with db_connection.execute('SELECT user_id, chat_id, mute_count, last_mute_time FROM users WHERE user_id = ?', (user_id,)) as cursor:
        row = await cursor.fetchone()
        if row:
            return {
                'user_id': row[0],
                'chat_id': row[1],
                'mute_count': row[2],
                'last_mute_time': datetime.fromisoformat(row[3]) if row[3] else None
            }
    return None

async def add_or_update_user(user_id, chat_id, mute_count, last_mute_time):
    await db_connection.execute('''
        INSERT INTO users (user_id, chat_id, mute_count, last_mute_time)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            chat_id=excluded.chat_id,
            mute_count=excluded.mute_count,
            last_mute_time=excluded.last_mute_time
    ''', (user_id, chat_id, mute_count, last_mute_time.isoformat() if last_mute_time else None))
    await db_connection.commit()
    # logger.info(f"Обновлена информация о пользователе {user_id}")

async def reset_mute_counts():
    await db_connection.execute('''
        UPDATE users SET mute_count = 0 WHERE mute_count < 3
    ''')
    await db_connection.commit()
    logger.info("Сброшены счетчики мутов для всех пользователей с мутами менее 3")

async def reset_user_mute_count(user_id):
    await db_connection.execute('UPDATE users SET mute_count = 0, last_mute_time = NULL WHERE user_id = ?', (user_id,))
    await db_connection.commit()
    # logger.info(f"Сброшен счетчик мутов пользователя {user_id}")

async def get_user_data(user_id):
    return await get_user(user_id)

# Дополнительные функции

async def get_permanently_banned_users():
    users = []
    async with db_connection.execute('SELECT user_id, chat_id FROM users WHERE mute_count >= 3') as cursor:
        async for row in cursor:
            users.append({'user_id': row[0], 'chat_id': row[1]})
    return users

async def get_users_with_mutes_less_than_3():
    users = []
    async with db_connection.execute('SELECT user_id, chat_id FROM users WHERE mute_count < 3 AND mute_count > 0') as cursor:
        async for row in cursor:
            users.append({'user_id': row[0], 'chat_id': row[1]})
    return users
