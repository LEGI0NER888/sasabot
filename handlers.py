# handlers.py
from datetime import datetime, timedelta
from aiogram.enums import ParseMode
import re
import logging
from aiogram import F, Router
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton,
    InlineKeyboardMarkup, ChatPermissions
)

from aiogram.filters import CommandStart
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from collections import defaultdict
from rapidfuzz import fuzz

from config.config_bot import bot, GROUP_ID, ADMINS, CHANNEL_ID
from database import (
    get_forbidden_words, add_forbidden_word, remove_forbidden_word,
    clear_forbidden_words, get_setting, update_setting,
    get_user_data, reset_user_mute_count, get_permanently_banned_users,
    get_users_with_mutes_less_than_3,get_user, get_user, add_or_update_user, delete_user,
    get_suspicious_users, get_violator_users, add_banned_user, update_status_to_normal,
    get_forbidden_nickname_emojis, get_forbidden_nickname_words, add_forbidden_nickname_emoji, 
    add_forbidden_nickname_word, remove_forbidden_nickname_emoji, remove_forbidden_nickname_word
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()

class FunctionStates(StatesGroup):
    change_first_post_message = State()
    change_delete_message_count = State()
    waiting_for_words_to_add = State()
    waiting_for_words_to_remove = State()
    waiting_for_nickname_words_to_add = State()
    waiting_for_nickname_words_to_remove = State()
    waiting_for_nickname_emojis_to_add = State()
    waiting_for_nickname_emojis_to_remove = State()

# Глобальный словарь для отслеживания количества удалённых сообщений в каждой теме обсуждения
message_counts = defaultdict(dict)

# Флаг для отслеживания, было ли отправлено приветственное сообщение в теме
welcome_sent = {}  # Ключ: thread_id, Значение: True/False

# Флаг для отслеживания времени последнего использования команды
last_command_times = {}


# Проверка, является ли пользователь администратором
async def is_user_admin(user_id):
    return str(user_id) in ADMINS

# Обработчик команды /start
@router.message(CommandStart(), F.chat.type == 'private')
async def cmd_start(message: Message):
    user_id = message.from_user.id
    if await is_user_admin(user_id):
        anti_spam_status = "Включен" if await get_setting('anti_spam_enabled') == '1' else "Отключен"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💀 Запретки 💀", callback_data="zapret_words_kb")],
                [InlineKeyboardButton(text="🤡 Запретные никнеймы 🤡", callback_data="zapret_nicknames_kb")],
                [InlineKeyboardButton(text="💦 Запретные эмоджи 💦", callback_data="zapret_emoji_kb")],
                [InlineKeyboardButton(text="🔒 Забаненные 🔒", callback_data="show_permanently_banned_users")],
                [InlineKeyboardButton(text="🔇 Размут замученных 🔇", callback_data="unban_users_with_less_than_3_mutes")],
                [InlineKeyboardButton(text="🔍 Подозрения 🔍", callback_data="suspicions_menu")],
                [InlineKeyboardButton(text=f"⌨️ [Антиспам: {anti_spam_status}] ⌨️", callback_data="toggle_anti_spam")],
                [InlineKeyboardButton(text="✉️ [Изменить кол-во удаляемых сообщений] ✉️", callback_data="change_delete_count")],
                [InlineKeyboardButton(text="✏️ [Редактирование 1-го поста] ✏️", callback_data="change_first_post_message")],
                
            ]
        )
        await message.answer("Добро пожаловать в админ-панель!", reply_markup=kb)
    else:
        return
    
@router.callback_query(lambda c: c.data == 'zapret_words_kb')
async def zapret_words(callback_query: CallbackQuery):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить слова ➕", callback_data="add_words")],
            [InlineKeyboardButton(text="➖ Удалить слова ➖", callback_data="remove_words")],
            [InlineKeyboardButton(text="⛔️ Показать запрещённые слова ⛔️", callback_data="show_forbidden_words")],
            [InlineKeyboardButton(text="🧹 [Очистить список слов] 🧹", callback_data="confirm_clear_words")],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_message")]
        ]
    )
    await callback_query.message.answer('ЗАПРЕТКИ (В ЧАТЕ)', parse_mode='HTML', reply_markup=kb)
    await callback_query.answer()

@router.callback_query(lambda c: c.data == 'zapret_nicknames_kb')
async def zapret_nicknames(callback_query: CallbackQuery):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить слова для никнеймов ➕", callback_data="add_nickname_words")],
            [InlineKeyboardButton(text="➖ Удалить слова для никнеймов ➖", callback_data="remove_nickname_words")],
            [InlineKeyboardButton(text="⛔️ Показать запрещённые слова в никнеймах ⛔️", callback_data="show_forbidden_nickname_words")],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_message")]
        ]
    )
    await callback_query.message.answer('ЗАПРЕТНЫЕ НИКНЕЙМЫ', parse_mode='HTML', reply_markup=kb)
    await callback_query.answer()

@router.callback_query(lambda c: c.data == 'zapret_emoji_kb')
async def zapret_emoji(callback_query: CallbackQuery):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить эмодзи для никнеймов ➕", callback_data="add_nickname_emojis")],
            [InlineKeyboardButton(text="➖ Удалить эмодзи для никнеймов ➖", callback_data="remove_nickname_emojis")],
            [InlineKeyboardButton(text="⛔️ Показать запрещённые эмодзи в никнеймах ⛔️", callback_data="show_forbidden_nickname_emojis")],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_message")]
        ]
    )
    await callback_query.message.answer('ЗАПРЕТНЫЕ ЭМОДЗИ (В НИКАХ)', parse_mode='HTML', reply_markup=kb)
    await callback_query.answer()
# Обработчик переключения антиспама
@router.callback_query(lambda c: c.data == 'toggle_anti_spam')
async def toggle_anti_spam(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    current_value = await get_setting('anti_spam_enabled')
    new_value = '0' if current_value == '1' else '1'
    await update_setting('anti_spam_enabled', new_value)
    status = "включена" if new_value == '1' else "отключена"
    await callback_query.answer(f"Антиспамовая защита {status}.", show_alert=True)

    anti_spam_status = "Включен" if new_value == '1' else "Отключен"
    kb = callback_query.message.reply_markup
    for row in kb.inline_keyboard:
        for button in row:
            if button.callback_data == 'toggle_anti_spam':
                button.text = f"Антиспам: {anti_spam_status}"
    await callback_query.message.edit_reply_markup(reply_markup=kb)

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
    


# Обработчик для показа перманентно забаненных пользователей с пагинацией
@router.callback_query(lambda c: c.data.startswith('show_permanently_banned_users'))
async def show_permanently_banned_users(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    data_parts = callback_query.data.split(':')
    if len(data_parts) > 1 and data_parts[1].startswith('page='):
        page_number = int(data_parts[1].split('=')[1])
    else:
        page_number = 1

    banned_users = await get_permanently_banned_users()

    if banned_users:
        users_per_page = 10
        total_pages = (len(banned_users) + users_per_page - 1) // users_per_page

        if page_number < 1:
            page_number = 1
        elif page_number > total_pages:
            page_number = total_pages

        start_index = (page_number - 1) * users_per_page
        end_index = start_index + users_per_page
        users_on_page = banned_users[start_index:end_index]

        keyboard_buttons = []
        for user in users_on_page:
            user_text = f"ID: {user['user_id']}"
            button = [InlineKeyboardButton(text=user_text, callback_data=f"select_banned_user_{user['user_id']}")]
            keyboard_buttons.append(button)

        nav_buttons = []
        if page_number > 1:
            nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"show_permanently_banned_users:page={page_number - 1}"))
        if page_number < total_pages:
            nav_buttons.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"show_permanently_banned_users:page={page_number + 1}"))

        unban_all_button = [InlineKeyboardButton(text="🔓 Разбанить всех", callback_data="unban_all_permanently_banned_users")]

        close_button = [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_message")]

        kb = InlineKeyboardMarkup(
            inline_keyboard=keyboard_buttons + [nav_buttons] + [unban_all_button] + [close_button]
        )

        try:
            await callback_query.message.answer("Выберите пользователя для разбана или разбаньте всех:", reply_markup=kb)
        except Exception:
            await callback_query.message.edit_reply_markup(reply_markup=kb)

    else:
        await callback_query.message.answer("Нет перманентно забаненных пользователей.", reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Закрыть", callback_data="close_message")]]
        ))
    await callback_query.answer()

# Обработчик подтверждения разбана всех перманентно забаненных пользователей
@router.callback_query(lambda c: c.data == 'unban_all_permanently_banned_users')
async def confirm_unban_all_permanently_banned_users(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, разбанить всех", callback_data="unban_all_confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_unban_all")]
    ])

    await callback_query.message.answer("Вы уверены, что хотите разбанить всех перманентно забаненных пользователей?", reply_markup=confirm_kb)
    await callback_query.answer()

# Обработчик отмены разбана всех
@router.callback_query(lambda c: c.data == 'cancel_unban_all')
async def cancel_unban_all(callback_query: CallbackQuery):
    await callback_query.answer("Разбан отменён.")
    await callback_query.message.delete()

# Обработчик выполнения разбана всех перманентно забаненных пользователей
@router.callback_query(lambda c: c.data == 'unban_all_confirm')
async def unban_all_confirm(callback_query: CallbackQuery):
    admin_user_id = callback_query.from_user.id
    if not await is_user_admin(admin_user_id):
        return

    banned_users = await get_permanently_banned_users()

    if not banned_users:
        await callback_query.answer("Нет пользователей для разбана.", show_alert=True)
        await callback_query.message.delete()
        return

    success_count = 0
    for user in banned_users:
        user_id = user['user_id']
        chat_id = user['chat_id']
        try:
            await callback_query.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=True)
            )
            await update_status_to_normal(user_id)

            await reset_user_mute_count(user_id)
            await delete_user(user_id)
            success_count += 1
            # logger.info(f"Пользователь {user_id} разбанен администратором {admin_user_id}.")
        except Exception as e:
            logger.error(f"Ошибка при разбане пользователя {user_id}: {e}")

    await callback_query.answer(f"Разбанено пользователей: {success_count}.", show_alert=True)
    await callback_query.message.delete()

# Обработчик выбора забаненного пользователя для разбана
@router.callback_query(lambda c: c.data.startswith('select_banned_user_'))
async def select_banned_user(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    selected_user_id = int(callback_query.data.split('_')[-1])

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Разбанить", callback_data=f"unban_user_{selected_user_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_unban_user")]
    ])

    await callback_query.message.answer(f"Вы хотите разбанить пользователя {selected_user_id}?", reply_markup=keyboard)
    await callback_query.answer()

# Обработчик отмены разбана
@router.callback_query(lambda c: c.data == 'cancel_unban_user')
async def cancel_unban_user(callback_query: CallbackQuery):
    await callback_query.answer("Разбан отменён.")
    await callback_query.message.delete()

# Обработчик разбана пользователя
@router.callback_query(lambda c: c.data.startswith('unban_user_'))
async def unban_user(callback_query: CallbackQuery):
    admin_user_id = callback_query.from_user.id
    if not await is_user_admin(admin_user_id):
        return

    selected_user_id = int(callback_query.data.split('_')[2])
    user_data = await get_user_data(selected_user_id)

    if user_data:
        chat_id = user_data['chat_id']
        try:
            await callback_query.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=selected_user_id,
                permissions=ChatPermissions(can_send_messages=True)
            )
            await update_status_to_normal(selected_user_id)
            await reset_user_mute_count(selected_user_id)
            await delete_user(selected_user_id)
            await callback_query.answer(f"Пользователь {selected_user_id} разбанен.", show_alert=True)
            await callback_query.message.delete()
            # logger.info(f"Пользователь {selected_user_id} разбанен администратором {admin_user_id}.")
        except Exception as e:
            logger.error(f"Ошибка при разбане пользователя {selected_user_id}: {e}")
            await callback_query.answer(f"Не удалось разбанить пользователя {selected_user_id}.", show_alert=True)
    else:
        await callback_query.answer(f"Пользователь {selected_user_id} не найден среди забаненных.", show_alert=True)
        await callback_query.message.delete()

# Обработчик изменения сообщения для первого поста
@router.callback_query(lambda c: c.data == 'change_first_post_message')
async def prompt_for_new_post_message(callback_query: CallbackQuery, state: FSMContext):
    first_message = await get_setting("first_post_message")
    await callback_query.message.answer(f"<b>Текст поста сейчас: \n<i>{first_message}</i></b>\n\n\nВведите новое описание для первого поста:", parse_mode=ParseMode.HTML,reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="close_message_and_state")]]
            ))
    await state.set_state(FunctionStates.change_first_post_message)
    await callback_query.answer()

@router.message(FunctionStates.change_first_post_message)
async def change_first_post_message(message: Message, state: FSMContext):
    new_message = message.text
    await update_setting("first_post_message", new_message)
    await message.answer(
        f"Новое сообщение для первого поста установлено:\n\n{new_message}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Закрыть", callback_data="close_message")]]
        )
    )
    await state.clear()

# Обработчик изменения числа удаляемых сообщений
@router.callback_query(lambda c: c.data == 'change_delete_count')
async def prompt_for_new_delete_count(callback_query: CallbackQuery, state: FSMContext):
    counter = await get_setting("delete_message_count")
    await callback_query.message.answer(f"<b>Число удаляемых сообщений сейчас:\t<i>{counter}</i></b>\n\nВведите новое число сообщений для удаления:", parse_mode=ParseMode.HTML,reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="close_message_and_state")]]
            ))
    await state.set_state(FunctionStates.change_delete_message_count)
    await callback_query.answer()

@router.message(FunctionStates.change_delete_message_count)
async def change_delete_message_count(message: Message, state: FSMContext):
    try:
        new_count = int(message.text)
        await update_setting("delete_message_count", str(new_count))
        await message.answer(
            f"Новое число удаляемых сообщений установлено: {new_count}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Закрыть", callback_data="close_message")]]
            )
        )
        await state.clear()
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число.")





# Обработчик закрытия сообщения
@router.callback_query(lambda c: c.data == 'close_message')
async def close_message(callback_query: CallbackQuery):
    await callback_query.message.delete()
    await callback_query.answer()

# Обработчик закрытия сообщения
@router.callback_query(lambda c: c.data == 'close_message_and_state')
async def close_message_and_state(callback_query: CallbackQuery,state: FSMContext):
    await callback_query.message.delete()
    await state.clear()
    await callback_query.answer()





# Обработчик для разбана пользователей с мутами < 3
@router.callback_query(lambda c: c.data == 'unban_users_with_less_than_3_mutes')
async def confirm_unban_users(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    users_to_unban = await get_users_with_mutes_less_than_3()
    count = len(users_to_unban)

    if count == 0:
        await callback_query.message.answer(
            "Нет пользователей для разбана.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Закрыть", callback_data="close_message")]]
            )
        )
        await callback_query.answer()
        return

    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, разбанить всех", callback_data="unban_users_confirm")],
        [InlineKeyboardButton(text="Отмена", callback_data="cancel_unban_users")]
    ])

    await callback_query.message.answer(
        f"Найдено {count} пользователей с мутами меньше 3. Вы хотите разбанить их всех?",
        reply_markup=confirm_kb
    )
    await callback_query.answer()

# Обработчик отмены разбана
@router.callback_query(lambda c: c.data == 'cancel_unban_users')
async def cancel_unban_users(callback_query: CallbackQuery):
    await callback_query.answer("Разбан отменён.")
    await callback_query.message.delete()

# Обработчик подтверждения разбана
@router.callback_query(lambda c: c.data == 'unban_users_confirm')
async def unban_users_confirm(callback_query: CallbackQuery):
    
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    users_to_unban = await get_users_with_mutes_less_than_3()

    for user in users_to_unban:
        try:
            await callback_query.bot.restrict_chat_member(
                chat_id=user['chat_id'],
                user_id=user['user_id'],
                permissions=ChatPermissions(can_send_messages=True)
            )
            await add_or_update_user(user['user_id'], user['chat_id'], 0, None)
            # logger.info(f"Пользователь {user['user_id']} разблокирован и счетчик мутов сброшен.")
        except Exception as e:
            logger.error(f"Ошибка при разблокировке пользователя {user['user_id']}: {e}")

    await callback_query.answer("Все пользователи с мутами меньше 3 разблокированы.")
    await callback_query.message.delete()

##############
###ЭРО-боты###
##############

# Обработчик для меню "Подозрения"
@router.callback_query(lambda c: c.data == 'suspicions_menu')
async def show_suspicions_menu(callback_query: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Подозрительные", callback_data="show_suspicious_users")],
        [InlineKeyboardButton(text="🚫 Нарушители", callback_data="show_violator_users")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_message")]
    ])
    await callback_query.message.answer("Выберите категорию:", reply_markup=kb)
    await callback_query.answer()

# Обработчик для показа списка подозрительных пользователей
@router.callback_query(lambda c: c.data.startswith('show_suspicious_users'))
async def show_suspicious_users(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    suspicious_users = await get_suspicious_users()

    if suspicious_users:
        users_per_page = 10
        page_number = 1  # Для простоты, реализация пагинации опущена
        keyboard_buttons = []
        for user in suspicious_users:
            try:
                user_chat = await bot.get_chat(user['user_id'])
                user_full_name = user_chat.full_name
            except:
                user_full_name = f"ID: {user['user_id']}"
            user_text = f"{user_full_name}"
            button = [InlineKeyboardButton(text=user_text, callback_data=f"select_suspicious_user_{user['user_id']}")]
            keyboard_buttons.append(button)

        kb = InlineKeyboardMarkup(
            inline_keyboard=keyboard_buttons + [
                [InlineKeyboardButton(text="🔒 Забанить всех", callback_data="ban_all_suspicious_users")],
                [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_message")]
            ]
        )

        await callback_query.message.answer("Список подозрительных пользователей:", reply_markup=kb)
    else:
        await callback_query.message.answer("Нет подозрительных пользователей.", reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Закрыть", callback_data="close_message")]]
        ))
    await callback_query.answer()

# Обработчик для показа списка нарушителей
@router.callback_query(lambda c: c.data.startswith('show_violator_users'))
async def show_violator_users(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    violator_users = await get_violator_users()

    if violator_users:
        users_per_page = 10
        page_number = 1  # Для простоты, реализация пагинации опущена
        keyboard_buttons = []
        for user in violator_users:
            # Получаем полное имя пользователя через API
            try:
                user_chat = await bot.get_chat(user['user_id'])
                user_full_name = user_chat.full_name
            except:
                user_full_name = f"ID: {user['user_id']}"
            user_text = f"{user_full_name}"
            button = [InlineKeyboardButton(text=user_text, callback_data=f"select_violator_user_{user['user_id']}")]
            keyboard_buttons.append(button)

        kb = InlineKeyboardMarkup(
            inline_keyboard=keyboard_buttons + [
                [InlineKeyboardButton(text="🔒 Забанить всех", callback_data="ban_all_violator_users")],
                [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_message")]
            ]
        )

        await callback_query.message.answer("Список нарушителей:", reply_markup=kb)
    else:
        await callback_query.message.answer("Нет нарушителей.", reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Закрыть", callback_data="close_message")]]
        ))
    await callback_query.answer()

# Обработчик выбора подозрительного пользователя
@router.callback_query(lambda c: c.data.startswith('select_suspicious_user_'))
async def select_suspicious_user(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    selected_user_id = int(callback_query.data.split('_')[-1])
    # Получаем информацию о пользователе
    user_data = await get_user_data(selected_user_id)
    if user_data:
        user_chat = await bot.get_chat(selected_user_id)
        try:
            mention = f'@{user_chat.username}'
            user_profile_link = f'<a href="https://t.me/{user_chat.username}">{mention}</a>'
            
        except:
            user_full_name = user_chat.full_name
            link = f'tg://user?id={selected_user_id}'
            
            user_profile_link = f'<a href="{link}">{user_full_name}</a>'

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Забанить", callback_data=f"ban_suspicious_user_{selected_user_id}")],
            [InlineKeyboardButton(text="🚫 Удалить из пула", callback_data=f"remove_suspicious_user_{selected_user_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="close_message")]
        ])

        await callback_query.message.answer(
            f"Выберите действие для пользователя {user_profile_link}:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        await callback_query.answer()
    else:
        await callback_query.answer("Пользователь не найден.", show_alert=True)
        await callback_query.message.delete()

# Обработчик бана подозрительного пользователя
@router.callback_query(lambda c: c.data.startswith('ban_suspicious_user_'))
async def ban_suspicious_user(callback_query: CallbackQuery):
    admin_user_id = callback_query.from_user.id
    if not await is_user_admin(admin_user_id):
        return

    selected_user_id = int(callback_query.data.split('_')[-1])
    user_data = await get_user_data(selected_user_id)

    if user_data:
        chat_id = user_data['chat_id']
        try:
            await callback_query.bot.ban_chat_member(chat_id=chat_id, user_id=selected_user_id)
            await add_banned_user(selected_user_id)
            await callback_query.answer(f"Пользователь {selected_user_id} забанен.", show_alert=True)
            await callback_query.message.delete()
            logger.info(f"Пользователь {selected_user_id} забанен администратором {admin_user_id}.")
        except Exception as e:
            logger.error(f"Ошибка при бане пользователя {selected_user_id}: {e}")
            await callback_query.answer(f"Не удалось забанить пользователя {selected_user_id}.", show_alert=True)
    else:
        await callback_query.answer(f"Пользователь {selected_user_id} не найден.", show_alert=True)
        await callback_query.message.delete()

# Обработчик удаления подозрительного пользователя из пула
@router.callback_query(lambda c: c.data.startswith('remove_suspicious_user_'))
async def remove_suspicious_user(callback_query: CallbackQuery):
    chat_id = GROUP_ID
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    selected_user_id = int(callback_query.data.split('_')[-1])
    try:
        member = await bot.get_chat_member(chat_id, selected_user_id)
        status = member.status
    
        await bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=selected_user_id,
                    permissions=ChatPermissions(
                        can_send_messages=True
                    )
                )
        
        await delete_user(selected_user_id)
        await callback_query.answer(f"Пользователь {selected_user_id} удалён из пула.", show_alert=True)
        # await send_nickname_change_request(selected_user_id)
        await callback_query.message.delete()
    except Exception as e:
        await delete_user(selected_user_id)
        await callback_query.answer(f"Пользователь {selected_user_id} удалён из пула.", show_alert=True)
        # await send_nickname_change_request(selected_user_id)
        await callback_query.message.delete()

# async def send_nickname_change_request(user_id):
#     try:
#         message_text = "Здравствуйте! Ваш никнейм содержит запрещённые слова или эмодзи. Пожалуйста, измените его, чтобы продолжить общение в чате."
#         await bot.send_message(chat_id=user_id, text=message_text)
#         logger.info(f"Отправлено сообщение пользователю {user_id} с просьбой сменить никнейм.")
#     except Exception as e:
#         logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

# Обработчик бана всех подозрительных пользователей
@router.callback_query(lambda c: c.data == 'ban_all_suspicious_users')
async def ban_all_suspicious_users(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    # Получаем список подозрительных пользователей
    suspicious_users = await get_suspicious_users()

    if not suspicious_users:
        await callback_query.answer("Нет подозрительных пользователей для бана.", show_alert=True)
        await callback_query.message.delete()
        return

    # Спрашиваем подтверждение у администратора
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, забанить всех", callback_data="ban_all_suspicious_confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_ban_all_suspicious")]
    ])

    await callback_query.message.answer(
        f"Вы уверены, что хотите забанить всех подозрительных пользователей ({len(suspicious_users)} чел.)?",
        reply_markup=confirm_kb
    )
    await callback_query.answer()

# Обработчик отмены бана всех подозрительных пользователей
@router.callback_query(lambda c: c.data == 'cancel_ban_all_suspicious')
async def cancel_ban_all_suspicious(callback_query: CallbackQuery):
    await callback_query.answer("Бан отменён.")
    await callback_query.message.delete()

# Обработчик подтверждения бана всех подозрительных пользователей
@router.callback_query(lambda c: c.data == 'ban_all_suspicious_confirm')
async def ban_all_suspicious_confirm(callback_query: CallbackQuery):
    admin_user_id = callback_query.from_user.id
    if not await is_user_admin(admin_user_id):
        return

    suspicious_users = await get_suspicious_users()

    if not suspicious_users:
        await callback_query.answer("Нет подозрительных пользователей для бана.", show_alert=True)
        await callback_query.message.delete()
        return

    success_count = 0
    for user in suspicious_users:
        user_id = user['user_id']
        chat_id = user['chat_id']
        try:
            # Баним пользователя
            await callback_query.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            # Удаляем пользователя из пула
            await add_banned_user(user_id)
            success_count += 1
            logger.info(f"Пользователь {user_id} забанен администратором {admin_user_id}.")
        except Exception as e:
            logger.error(f"Ошибка при бане пользователя {user_id}: {e}")

    await callback_query.answer(f"Забанено пользователей: {success_count}.", show_alert=True)
    await callback_query.message.delete()


# Обработчик выбора нарушителя
@router.callback_query(lambda c: c.data.startswith('select_violator_user_'))
async def select_violator_user(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    selected_user_id = int(callback_query.data.split('_')[-1])
    user_data = await get_user_data(selected_user_id)
    if user_data:
        user_chat = await bot.get_chat(selected_user_id)
        try:
            mention = f'@{user_chat.username}'
            user_profile_link = f'<a href="https://t.me/{user_chat.username}">{mention}</a>'
            
        except:
            user_full_name = user_chat.full_name
            link = f'tg://user?id={selected_user_id}'
            
            user_profile_link = f'<a href="{link}">{user_full_name}</a>'

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Забанить", callback_data=f"ban_violator_user_{selected_user_id}")],
            [InlineKeyboardButton(text="🚫 Удалить из пула", callback_data=f"remove_violator_user_{selected_user_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="close_message")]
        ])

        await callback_query.message.answer(
            f"Выберите действие для пользователя {user_profile_link}:",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
        await callback_query.answer()
    else:
        await callback_query.answer("Пользователь не найден.", show_alert=True)
        await callback_query.message.delete()

# Обработчик бана нарушителя
@router.callback_query(lambda c: c.data.startswith('ban_violator_user_'))
async def ban_violator_user(callback_query: CallbackQuery):
    admin_user_id = callback_query.from_user.id
    if not await is_user_admin(admin_user_id):
        return

    selected_user_id = int(callback_query.data.split('_')[-1])
    user_data = await get_user_data(selected_user_id)

    if user_data:
        chat_id = user_data['chat_id']
        try:
            await callback_query.bot.ban_chat_member(chat_id=chat_id, user_id=selected_user_id)
            await add_banned_user(selected_user_id)
            await callback_query.answer(f"Пользователь {selected_user_id} забанен.", show_alert=True)
            await callback_query.message.delete()
            logger.info(f"Пользователь {selected_user_id} забанен администратором {admin_user_id}.")
        except Exception as e:
            logger.error(f"Ошибка при бане пользователя {selected_user_id}: {e}")
            await callback_query.answer(f"Не удалось забанить пользователя {selected_user_id}.", show_alert=True)
    else:
        await callback_query.answer(f"Пользователь {selected_user_id} не найден.", show_alert=True)
        await callback_query.message.delete()

# Обработчик удаления нарушителя из пула
@router.callback_query(lambda c: c.data.startswith('remove_violator_user_'))
async def remove_violator_user(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    if not await is_user_admin(user_id):
        return
    
    selected_user_id = int(callback_query.data.split('_')[-1])
    try:
        member = await bot.get_chat_member(chat_id, selected_user_id)
        status = member.status
    
        await bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=selected_user_id,
                    permissions=ChatPermissions(
                        can_send_messages=True
                    )
                )
        
        await delete_user(selected_user_id)
        await callback_query.answer(f"Пользователь {selected_user_id} удалён из пула.", show_alert=True)
        # await send_nickname_change_request(selected_user_id)
        await callback_query.message.delete()
    except Exception as e:
        await delete_user(selected_user_id)
        await callback_query.answer(f"Пользователь {selected_user_id} удалён из пула.", show_alert=True)
        # await send_nickname_change_request(selected_user_id)
        await callback_query.message.delete()


# Обработчик бана всех нарушителей
@router.callback_query(lambda c: c.data == 'ban_all_violator_users')
async def ban_all_violator_users(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    violator_users = await get_violator_users()

    if not violator_users:
        await callback_query.answer("Нет нарушителей для бана.", show_alert=True)
        await callback_query.message.delete()
        return

    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, забанить всех", callback_data="ban_all_violators_confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_ban_all_violators")]
    ])

    await callback_query.message.answer(
        f"Вы уверены, что хотите забанить всех нарушителей ({len(violator_users)} чел.)?",
        reply_markup=confirm_kb
    )
    await callback_query.answer()

@router.callback_query(lambda c: c.data == 'cancel_ban_all_violators')
async def cancel_ban_all_violators(callback_query: CallbackQuery):
    await callback_query.answer("Бан отменён.")
    await callback_query.message.delete()

@router.callback_query(lambda c: c.data == 'ban_all_violators_confirm')
async def ban_all_violators_confirm(callback_query: CallbackQuery):
    admin_user_id = callback_query.from_user.id
    if not await is_user_admin(admin_user_id):
        return

    violator_users = await get_violator_users()

    if not violator_users:
        await callback_query.answer("Нет нарушителей для бана.", show_alert=True)
        await callback_query.message.delete()
        return

    success_count = 0
    for user in violator_users:
        user_id = user['user_id']
        chat_id = user['chat_id']
        try:
            await callback_query.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            await add_banned_user(user_id)
            success_count += 1
            logger.info(f"Пользователь {user_id} забанен администратором {admin_user_id}.")
        except Exception as e:
            logger.error(f"Ошибка при бане пользователя {user_id}: {e}")

    await callback_query.answer(f"Забанено пользователей: {success_count}.", show_alert=True)
    await callback_query.message.delete()


###################################################
####добавление, удаление подозрений в никнеймах####
###################################################

@router.callback_query(lambda c: c.data == "add_nickname_words")
async def process_add_nickname_words(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    await callback_query.message.answer(
        "Пожалуйста, введите слова для <b>добавления в запрещённые никнеймы</b>. "
        "Вы можете вводить несколько слов через пробел или фразы в кавычках.\n"
        "Пример: <code>слово1 слово2 \"фраза для бана\"</code>",
        parse_mode='HTML'
    )
    await state.set_state(FunctionStates.waiting_for_nickname_words_to_add)
    await callback_query.answer()


@router.message(FunctionStates.waiting_for_nickname_words_to_add)
async def add_nickname_words_handler(message: Message, state: FSMContext):
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
        await add_forbidden_nickname_word(word)
        added_words.append(word.lower())

    if added_words:
        await message.answer(
            f"Слова/фразы <b>{', '.join(added_words)}</b> добавлены в список запрещённых слов для никнеймов.",
            parse_mode='HTML'
        )
    else:
        await message.answer("Указанные слова/фразы уже были в списке запрещённых слов для никнеймов.")

    await state.clear()


@router.callback_query(lambda c: c.data == "remove_nickname_words")
async def process_remove_nickname_words(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    await callback_query.message.answer(
        "Пожалуйста, введите слова для <b>удаления из запрещённых никнеймов</b>. "
        "Вы можете вводить несколько слов через пробел или фразы в кавычках.\n"
        "Пример: <code>слово1 слово2 \"фраза для бана\"</code>",
        parse_mode='HTML'
    )
    await state.set_state(FunctionStates.waiting_for_nickname_words_to_remove)
    await callback_query.answer()


@router.message(FunctionStates.waiting_for_nickname_words_to_remove)
async def remove_nickname_words_handler(message: Message, state: FSMContext):
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
        await remove_forbidden_nickname_word(word)
        removed_words.append(word.lower())

    if removed_words:
        await message.answer(
            f"Слова/фразы <b>{', '.join(removed_words)}</b> удалены из списка запрещённых слов для никнеймов.",
            parse_mode='HTML'
        )
    else:
        await message.answer("Указанных слов/фраз не было в списке запрещённых слов для никнеймов.")

    await state.clear()


@router.callback_query(lambda c: c.data == 'show_forbidden_nickname_words')
async def process_show_forbidden_nickname_words(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    forbidden_nickname_words = await get_forbidden_nickname_words()
    if forbidden_nickname_words:
        words_list = ', '.join(sorted(forbidden_nickname_words))
        message_text = f"🚫Запрещённые слова в никнеймах:\n{words_list}"
    else:
        message_text = "Список запрещённых слов в никнеймах пуст"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_message")]
        ]
    )
    await callback_query.message.answer(message_text, parse_mode='HTML', reply_markup=kb)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "add_nickname_emojis")
async def process_add_nickname_emojis(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    await callback_query.message.answer(
        "Пожалуйста, введите эмодзи для <b>добавления в запрещённые никнеймы</b>. "
        "Вы можете вводить несколько эмодзи через пробел.\n"
        "Пример: 😈 🤬",
        parse_mode='HTML'
    )
    await state.set_state(FunctionStates.waiting_for_nickname_emojis_to_add)
    await callback_query.answer()


@router.message(FunctionStates.waiting_for_nickname_emojis_to_add)
async def add_nickname_emojis_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not await is_user_admin(user_id):
        return

    emojis_to_add = message.text.strip().split()
    added_emojis = []
    for emoji in emojis_to_add:
        await add_forbidden_nickname_emoji(emoji)
        added_emojis.append(emoji)

    if added_emojis:
        await message.answer(
            f"Эмодзи <b>{' '.join(added_emojis)}</b> добавлены в список запрещённых эмодзи для никнеймов.",
            parse_mode='HTML'
        )
    else:
        await message.answer("Указанные эмодзи уже были в списке запрещённых эмодзи для никнеймов.")

    await state.clear()

@router.callback_query(lambda c: c.data == "remove_nickname_emojis")
async def process_remove_nickname_emojis(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    await callback_query.message.answer(
        "Пожалуйста, введите эмодзи для <b>удаления из запрещённых никнеймов</b>. "
        "Вы можете вводить несколько эмодзи через пробел.\n"
        "Пример: 😈 🤬",
        parse_mode='HTML'
    )
    await state.set_state(FunctionStates.waiting_for_nickname_emojis_to_remove)
    await callback_query.answer()

@router.message(FunctionStates.waiting_for_nickname_emojis_to_remove)
async def remove_nickname_emojis_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not await is_user_admin(user_id):
        return

    emojis_to_remove = message.text.strip().split()
    removed_emojis = []
    for emoji in emojis_to_remove:
        await remove_forbidden_nickname_emoji(emoji)
        removed_emojis.append(emoji)

    if removed_emojis:
        await message.answer(
            f"Эмодзи <b>{' '.join(removed_emojis)}</b> удалены из списка запрещённых эмодзи для никнеймов.",
            parse_mode='HTML'
        )
    else:
        await message.answer("Указанных эмодзи не было в списке запрещённых эмодзи для никнеймов.")

    await state.clear()


@router.callback_query(lambda c: c.data == 'show_forbidden_nickname_emojis')
async def process_show_forbidden_nickname_emojis(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    forbidden_nickname_emojis = await get_forbidden_nickname_emojis()
    if forbidden_nickname_emojis:
        emojis_list = ' '.join(sorted(forbidden_nickname_emojis))
        message_text = f"🚫Запрещённые эмодзи в никнеймах:\n{emojis_list}"
    else:
        message_text = "Список запрещённых эмодзи в никнеймах пуст"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_message")]
        ]
    )
    await callback_query.message.answer(message_text, parse_mode='HTML', reply_markup=kb)
    await callback_query.answer()
