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

# Кэши для запрещённых эмодзи и слов в никнеймах
forbidden_nickname_emojis_cache = set()
forbidden_nickname_words_cache = set()

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
            last_mute_time TEXT,
            status TEXT DEFAULT 'normal'
        )
    ''')

    await db_connection.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')

    # Создание таблицы запрещённых эмодзи в никнеймах
    await db_connection.execute('''
        CREATE TABLE IF NOT EXISTS forbidden_nickname_emojis (
            emoji TEXT PRIMARY KEY
        )
    ''')

    # Создание таблицы запрещённых слов в никнеймах
    await db_connection.execute('''
        CREATE TABLE IF NOT EXISTS forbidden_nickname_words (
            word TEXT PRIMARY KEY
        )
    ''')


    await db_connection.commit()

    # Инициализируем кэши
    await load_forbidden_words()
    await load_settings()
    await load_forbidden_nickname_emojis()
    await load_forbidden_nickname_words()

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
    async with db_connection.execute('SELECT user_id, chat_id FROM users WHERE mute_count >= 3 OR status = "banned"') as cursor:
        async for row in cursor:
            users.append({'user_id': row[0], 'chat_id': row[1]})
    return users

async def get_users_with_mutes_less_than_3():
    users = []
    async with db_connection.execute('SELECT user_id, chat_id FROM users WHERE mute_count < 3 AND mute_count > 0') as cursor:
        async for row in cursor:
            users.append({'user_id': row[0], 'chat_id': row[1]})
    return users



#########################################
#########################################

# Новые функции для загрузки запрещённых эмодзи в никнеймах
async def load_forbidden_nickname_emojis():
    async with cache_lock:
        forbidden_nickname_emojis_cache.clear()
        async with db_connection.execute('SELECT emoji FROM forbidden_nickname_emojis') as cursor:
            async for row in cursor:
                forbidden_nickname_emojis_cache.add(row[0])
    logger.info(f"Загружены запрещённые эмодзи в никнеймах: {forbidden_nickname_emojis_cache}")

# Получение списка запрещённых эмодзи в никнеймах
async def get_forbidden_nickname_emojis():
    async with cache_lock:
        return forbidden_nickname_emojis_cache.copy()

# Добавление запрещённого эмодзи в никнейме
async def add_forbidden_nickname_emoji(emoji):
    async with cache_lock:
        if emoji not in forbidden_nickname_emojis_cache:
            await db_connection.execute('INSERT OR IGNORE INTO forbidden_nickname_emojis (emoji) VALUES (?)', (emoji,))
            await db_connection.commit()
            forbidden_nickname_emojis_cache.add(emoji)
            logger.info(f"Добавлено запрещённое эмодзи в никнейме: {emoji}")

# Удаление запрещённого эмодзи в никнейме
async def remove_forbidden_nickname_emoji(emoji):
    async with cache_lock:
        if emoji in forbidden_nickname_emojis_cache:
            await db_connection.execute('DELETE FROM forbidden_nickname_emojis WHERE emoji = ?', (emoji,))
            await db_connection.commit()
            forbidden_nickname_emojis_cache.remove(emoji)
            logger.info(f"Удалено запрещённое эмодзи в никнейме: {emoji}")

# Новые функции для загрузки запрещённых слов в никнеймах
async def load_forbidden_nickname_words():
    async with cache_lock:
        forbidden_nickname_words_cache.clear()
        async with db_connection.execute('SELECT word FROM forbidden_nickname_words') as cursor:
            async for row in cursor:
                forbidden_nickname_words_cache.add(row[0])
    logger.info(f"Загружены запрещённые слова в никнеймах: {forbidden_nickname_words_cache}")

# Получение списка запрещённых слов в никнеймах
async def get_forbidden_nickname_words():
    async with cache_lock:
        return forbidden_nickname_words_cache.copy()

# Добавление запрещённого слова в никнейме
async def add_forbidden_nickname_word(word):
    word_lower = word.lower()
    async with cache_lock:
        if word_lower not in forbidden_nickname_words_cache:
            await db_connection.execute('INSERT OR IGNORE INTO forbidden_nickname_words (word) VALUES (?)', (word_lower,))
            await db_connection.commit()
            forbidden_nickname_words_cache.add(word_lower)
            logger.info(f"Добавлено запрещённое слово в никнейме: {word_lower}")

# Удаление запрещённого слова в никнейме
async def remove_forbidden_nickname_word(word):
    word_lower = word.lower()
    async with cache_lock:
        if word_lower in forbidden_nickname_words_cache:
            await db_connection.execute('DELETE FROM forbidden_nickname_words WHERE word = ?', (word_lower,))
            await db_connection.commit()
            forbidden_nickname_words_cache.remove(word_lower)
            logger.info(f"Удалено запрещённое слово в никнейме: {word_lower}")

# Обновление функций get_user и add_or_update_user для учёта новых полей
async def get_user(user_id):
    async with db_connection.execute('SELECT user_id, chat_id, mute_count, last_mute_time, status FROM users WHERE user_id = ?', (user_id,)) as cursor:
        row = await cursor.fetchone()
        if row:
            return {
                'user_id': row[0],
                'chat_id': row[1],
                'mute_count': row[2],
                'last_mute_time': datetime.fromisoformat(row[3]) if row[3] else None,
                'status': row[4]
                
            }
    return None

async def add_or_update_user(user_id, chat_id, mute_count, last_mute_time, status='normal'):
    await db_connection.execute('''
        INSERT INTO users (user_id, chat_id, mute_count, last_mute_time, status)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            chat_id=excluded.chat_id,
            mute_count=excluded.mute_count,
            last_mute_time=excluded.last_mute_time,
            status=excluded.status
    ''', (user_id, chat_id, mute_count, last_mute_time.isoformat() if last_mute_time else None, status))
    await db_connection.commit()
    logger.info(f"Обновлена информация о пользователе {user_id}")

# Функции для получения списка подозрительных и нарушителей
async def get_suspicious_users():
    users = []
    async with db_connection.execute('SELECT user_id, chat_id FROM users WHERE status = "suspicious"') as cursor:
        async for row in cursor:
            users.append({'user_id': row[0], 'chat_id': row[1]})
    return users

async def get_violator_users():
    users = []
    async with db_connection.execute('SELECT user_id, chat_id FROM users WHERE status = "violator"') as cursor:
        async for row in cursor:
            users.append({'user_id': row[0], 'chat_id': row[1]})
    return users

async def delete_user(user_id):
    
    await db_connection.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    await db_connection.commit()
    logger.info(f"Пользователь {user_id} удалён из базы данных")


#################################
#################################
#################################

# Получение списка запрещённых слов в никнеймах
async def get_forbidden_nickname_words():
    async with cache_lock:
        return forbidden_nickname_words_cache.copy()

# Добавление запрещённого слова в никнейме
async def add_forbidden_nickname_word(word):
    word_lower = word.lower()
    async with cache_lock:
        if word_lower not in forbidden_nickname_words_cache:
            await db_connection.execute('INSERT OR IGNORE INTO forbidden_nickname_words (word) VALUES (?)', (word_lower,))
            await db_connection.commit()
            forbidden_nickname_words_cache.add(word_lower)
            logger.info(f"Добавлено запрещённое слово в никнейме: {word_lower}")

# Удаление запрещённого слова в никнейме
async def remove_forbidden_nickname_word(word):
    word_lower = word.lower()
    async with cache_lock:
        if word_lower in forbidden_nickname_words_cache:
            await db_connection.execute('DELETE FROM forbidden_nickname_words WHERE word = ?', (word_lower,))
            await db_connection.commit()
            forbidden_nickname_words_cache.remove(word_lower)
            logger.info(f"Удалено запрещённое слово в никнейме: {word_lower}")

# Получение списка запрещённых эмодзи в никнеймах
async def get_forbidden_nickname_emojis():
    async with cache_lock:
        return forbidden_nickname_emojis_cache.copy()

# Добавление запрещённого эмодзи в никнейме
async def add_forbidden_nickname_emoji(emoji):
    async with cache_lock:
        if emoji not in forbidden_nickname_emojis_cache:
            await db_connection.execute('INSERT OR IGNORE INTO forbidden_nickname_emojis (emoji) VALUES (?)', (emoji,))
            await db_connection.commit()
            forbidden_nickname_emojis_cache.add(emoji)
            logger.info(f"Добавлено запрещённое эмодзи в никнейме: {emoji}")

# Удаление запрещённого эмодзи в никнейме
async def remove_forbidden_nickname_emoji(emoji):
    async with cache_lock:
        if emoji in forbidden_nickname_emojis_cache:
            await db_connection.execute('DELETE FROM forbidden_nickname_emojis WHERE emoji = ?', (emoji,))
            await db_connection.commit()
            forbidden_nickname_emojis_cache.remove(emoji)
            logger.info(f"Удалено запрещённое эмодзи в никнейме: {emoji}")

async def add_banned_user(user_id):
    async with cache_lock:
        await db_connection.execute('UPDATE users SET status = "banned" WHERE user_id = ?', (user_id,))
        await db_connection.commit()

async def update_status_to_normal(user_id):
    async with cache_lock:
        await db_connection.execute('UPDATE users SET status = "normal" WHERE user_id = ?', (user_id,))
        await db_connection.commit()