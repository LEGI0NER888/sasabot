

import re
import logging
from aiogram import F, Router
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton,
    InlineKeyboardMarkup
)
from show_handlers import is_user_admin, FunctionStates
from aiogram.fsm.context import FSMContext
from collections import defaultdict
from rapidfuzz import fuzz

from config.config_bot import bot, GROUP_ID, ADMINS, CHANNEL_ID
from database import (
    get_forbidden_words, add_forbidden_word, remove_forbidden_word,
    clear_forbidden_words, get_setting,
    get_user, get_user, add_or_update_user,
    get_forbidden_nickname_emojis, get_forbidden_nickname_words
)

router = Router()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Обработчик подтверждения очистки списка слов
@router.callback_query(lambda c: c.data == 'confirm_clear_words')
async def confirm_clear_words(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, удалить все слова", callback_data="clear_words")],
        [InlineKeyboardButton(text="Отмена", callback_data="cancel_clear_words")]
    ])

    await callback_query.message.answer("Вы уверены, что хотите удалить все запрещённые слова?", reply_markup=confirm_kb)
    await callback_query.answer()

# Обработчик для удаления всех слов из списка
@router.callback_query(lambda c: c.data == 'clear_words')
async def clear_words(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    await clear_forbidden_words()
    await callback_query.answer("Все запрещённые слова успешно удалены.")
    await callback_query.message.delete()

# Обработчик отмены очистки списка
@router.callback_query(lambda c: c.data == 'cancel_clear_words')
async def cancel_clear_words(callback_query: CallbackQuery):
    await callback_query.answer("Очистка списка запрещённых слов отменена.")
    await callback_query.message.delete()

# Обработчик нажатия кнопки "Показать запрещённые слова" с кнопкой "Закрыть"
@router.callback_query(lambda c: c.data == 'show_forbidden_words')
async def process_show_forbidden_words(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):

        return

    forbidden_words = await get_forbidden_words()
    if forbidden_words:
        words_list = ', '.join(sorted(forbidden_words))
        message_text = f"🚫Запрещённые слова:\n{words_list}"
    else:
        message_text = "Список запрещённых слов пуст"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_message")]
        ]
    )
    await callback_query.message.answer(message_text, parse_mode='HTML', reply_markup=kb)
    await callback_query.answer()

# Обработчик нажатия кнопки "Добавить слова"
@router.callback_query(lambda c: c.data == "add_words")
async def process_add_words(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    await callback_query.message.answer(
        "Пожалуйста, введите слова для <b>добавления</b>. "
        "Вы можете вводить несколько слов через пробел или фразы в кавычках.\n"
        "Пример: <code>слово1 слово2 \"фраза для бана\"</code>",
        parse_mode='HTML'
    )
    await state.set_state(FunctionStates.waiting_for_words_to_add)
    await callback_query.answer()

# Обработчик нажатия кнопки "Удалить слова"
@router.callback_query(lambda c: c.data == "remove_words")
async def process_remove_words(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    await callback_query.message.answer(
        "Пожалуйста, введите слова для <b>удаления</b>. "
        "Вы можете вводить несколько слов через пробел или фразы в кавычках.\n"
        "Пример: <code>слово1 слово2 \"фраза для бана\"</code>",
        parse_mode='HTML'
    )
    await state.set_state(FunctionStates.waiting_for_words_to_remove)
    await callback_query.answer()

# Обработчик ввода слов для добавления
@router.message(FunctionStates.waiting_for_words_to_add)
async def add_words_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not await is_user_admin(user_id):
        return

    text = message.text

    import shlex
    try:
        words_to_add = shlex.split(text)
    except ValueError as e:
        await message.answer(f"Ошибка при обработке введённых данных: {e}")
        return

    added_words = []
    for word in words_to_add:
        await add_forbidden_word(word)
        added_words.append(word.lower())

    if added_words:
        await message.answer(
            f"Слова/фразы <b>{', '.join(added_words)}</b> добавлены в список запрещённых слов.",
            parse_mode='HTML'
        )
    else:
        await message.answer("Указанные слова/фразы уже были в списке запрещённых слов.")

    await state.clear()

# Обработчик ввода слов для удаления
@router.message(FunctionStates.waiting_for_words_to_remove)
async def remove_words_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not await is_user_admin(user_id):
        return

    text = message.text

    import shlex
    try:
        words_to_remove = shlex.split(text)
    except ValueError as e:
        await message.answer(f"Ошибка при обработке введённых данных: {e}")
        return

    removed_words = []
    for word in words_to_remove:
        await remove_forbidden_word(word)
        removed_words.append(word.lower())

    if removed_words:
        await message.answer(
            f"Слова/фразы <b>{', '.join(removed_words)}</b> удалены из списка запрещённых слов.",
            parse_mode='HTML'
        )
    else:
        await message.answer("Указанных слов/фраз не было в списке запрещённых слов.")

    await state.clear()



# Функция для создания регулярного выражения
def create_regex_pattern(word):
    # Экранируем каждую букву и добавляем паттерн для пробелов и спецсимволов
    escaped_letters = map(re.escape, word)
    pattern = '[^A-Za-zА-Яа-яЁё]*'.join(escaped_letters)
    return rf'\b{pattern}\b'  # Добавляем \b для границ слова, чтобы избегать случайных совпадений

def transliterate_to_cyrillic(text):
    translit_map = {
        'a': 'а', 'b': 'б', 'v': 'в', 'g': 'г', 'd': 'д',
        'e': 'е', 'z': 'з', 'i': 'и', 'k': 'к', 'l': 'л',
        'm': 'м', 'n': 'н', 'o': 'о', 'p': 'п', 'r': 'р',
        's': 'с', 't': 'т', 'u': 'у', 'f': 'ф', 'h': 'х',
        'c': 'ц', 'y': 'у', 'w': 'ш', 'x': 'кс', 'q': 'к',

    }
    result = ''
    for char in text:
        result += translit_map.get(char, char)
    return result

last_command_time = None
rules = """, вот <b>правила чата:</b>
\n1. Нельзя писать команды <i>(через /)</i>
\n2. Без запреток
\n3. Спам наказывается <i>временным</i> мутом - особенных нарушителей может <b><i>замутить навсегда!</i></b>"""

# Глобальный словарь для отслеживания количества удалённых сообщений в каждой теме обсуждения
message_counts = defaultdict(dict)

# Обработчик сообщений в группе
@router.message(F.chat.id == GROUP_ID)
async def handle_group_message(message: Message):
    text = message.text or message.caption
    chat_id = message.chat.id
    message_id = message.message_id
    thread_id = message.message_thread_id

    user_id = message.from_user.id

    if chat_id not in message_counts:
        message_counts[chat_id] = {}

    delete_message_count = int(await get_setting("delete_message_count") or 5)
    first_post_message = await get_setting("first_post_message") or (
        "Я слежу чтобы вы не писали гадости, кто ослушается: будет наказан👇🏻👇🏻👇🏻"
    )

    if message.from_user and message.from_user.id == bot.id:
        return

    if message.entities:
        for entity in message.entities:
            if entity.type == 'bot_command':
                try:
                    await message.delete()
                except Exception as e:
                    logger.error(f"Ошибка при удалении команды: {e}")
                return

    # Проверяем, есть ли у пользователя статус
    user_data = await get_user(user_id)

    if user_data and user_data['status'] in ['suspicious', 'violator']:
        # Пользователь уже помечен, не нужно повторно проверять
        pass
    else:
        full_name = message.from_user.full_name or ''
        lower_full_name = full_name.lower()
        forbidden_emojis = await get_forbidden_nickname_emojis()
        forbidden_words_nickname = await get_forbidden_nickname_words()

        # Проверка на запрещённые эмодзи
        has_forbidden_emoji = any(emoji in full_name for emoji in forbidden_emojis)
        # Проверка на запрещённые слова
        has_forbidden_word_nickname = any(word in lower_full_name for word in forbidden_words_nickname)

        if has_forbidden_emoji and has_forbidden_word_nickname:
            # Пользователь является нарушителем
            await add_or_update_user(user_id, message.chat.id, mute_count=0, last_mute_time=None, status='violator')
            logger.info(f"Пользователь {user_id} помечен как нарушитель")
        elif has_forbidden_emoji or has_forbidden_word_nickname:
            # Пользователь является подозрительным
            await add_or_update_user(user_id, message.chat.id, mute_count=0, last_mute_time=None, status='suspicious')
            logger.info(f"Пользователь {user_id} помечен как подозрительный")
    
    if message.sender_chat and message.sender_chat.id == CHANNEL_ID and not thread_id:
        try:
            await message.reply(first_post_message)
            logger.info(f"Отправлено первое сообщение в ответ на пост ID: {message_id} в чате ID: {chat_id}")
            message_counts[chat_id][message_id] = 0
        except Exception as e:
            logger.error(f"Ошибка при отправке первого сообщения: {e}")
        return
    
    if thread_id and thread_id in message_counts[chat_id]:
        delete_count = message_counts[chat_id][thread_id]

        if delete_count < delete_message_count:
            try:
                await message.delete()
                delete_count += 1
                message_counts[chat_id][thread_id] = delete_count

                if delete_count >= delete_message_count:
                    del message_counts[chat_id][thread_id]
            except Exception as e:
                logger.error(f"Ошибка при удалении сообщения: {e}")

    # Проверка на запрещённые слова
    if text:
        forbidden_words = await get_forbidden_words()
        
        # Проверка на превышение длины сообщения
        if len(text) > 300:
            try:
                await message.delete()
            except Exception as e:
                logger.error(f"Ошибка при удалении длинного сообщения: {e}")
            return

        lower_text = transliterate_to_cyrillic(text.lower())

        threshold = 70  # Порог схожести для нечеткого сравнения

        for word in forbidden_words:
            pattern = create_regex_pattern(word)
            similarity = fuzz.ratio(lower_text, word.lower())

            # Удаление сообщения, если обнаружено совпадение с запрещенным словом
            if re.search(pattern, lower_text) or similarity >= threshold:
                try:
                    await message.delete()
                    logger.info(f"Удалено сообщение {message.message_id} с запрещённым словом '{word}'")
                except Exception as e:
                    logger.error(f"Ошибка при удалении сообщения {message.message_id}: {e}")
                break  # Останавливаем проверку, если сообщение уже удалено
    