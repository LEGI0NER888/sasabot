# handlers.py

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
    get_users_with_mutes_less_than_3, add_or_update_user
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()

class FunctionStates(StatesGroup):
    change_first_post_message = State()
    change_delete_message_count = State()
    waiting_for_words_to_add = State()
    waiting_for_words_to_remove = State()

# Глобальный словарь для отслеживания количества удалённых сообщений в каждой теме обсуждения
message_counts = defaultdict(dict)

# Флаг для отслеживания, было ли отправлено приветственное сообщение в теме
welcome_sent = {}  # Ключ: thread_id, Значение: True/False

# Словарь для отслеживания количества сообщений со ссылками от каждого пользователя
link_spam_counts = {}  # Ключ: user_id, Значение: количество сообщений со ссылками

# Словарь для подсчёта количества мутов пользователя
mute_counts = {}  # Ключ: user_id, Значение: количество мутов

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
                [InlineKeyboardButton(text="➕ Добавить слова ➕", callback_data="add_words")],
                [InlineKeyboardButton(text="➖ Удалить слова ➖", callback_data="remove_words")],
                [InlineKeyboardButton(text="⛔️ Показать запрещённые слова ⛔️", callback_data="show_forbidden_words")],
                [InlineKeyboardButton(text="🧹 [Очистить список слов] 🧹", callback_data="confirm_clear_words")],
                [InlineKeyboardButton(text="🔒 Забаненные 🔒", callback_data="show_permanently_banned_users")],
                [InlineKeyboardButton(text="🔇 Размут замученных 🔇", callback_data="unban_users_with_less_than_3_mutes")],
                [InlineKeyboardButton(text=f"⌨️ Антиспам: {anti_spam_status} ⌨️", callback_data="toggle_anti_spam")],
                [InlineKeyboardButton(text="✉️ [Изменить кол-во удаляемых сообщений] ✉️", callback_data="change_delete_count")],
                [InlineKeyboardButton(text="✏️ [Редактирование 1-го поста] ✏️", callback_data="change_first_post_message")],
            ]
        )
        await message.answer("Добро пожаловать в админ-панель!", reply_markup=kb)
    else:
        return

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
        await callback_query.answer("У вас нет прав доступа.", show_alert=True)
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
    escaped_letters = map(re.escape, word)
    pattern = r'\W*'.join(escaped_letters)
    return pattern

# Обработчик сообщений в группе
@router.message(F.chat.id == GROUP_ID)
async def handle_group_message(message: Message):
    text = message.text or message.caption
    chat_id = message.chat.id
    message_id = message.message_id
    thread_id = message.message_thread_id

    if chat_id not in message_counts:
        message_counts[chat_id] = {}

    # logger.info(f"Получено сообщение: chat_id={chat_id}, message_id={message_id}, thread_id={thread_id}")

    delete_message_count = int(await get_setting("delete_message_count") or 5)
    first_post_message = await get_setting("first_post_message") or (
        "Я слежу чтобы вы не писали гадости, кто ослушается: будет наказан👇🏻👇🏻👇🏻"
    )

    if message.from_user and message.from_user.id == bot.id:
        # logger.info("Сообщение от бота. Пропускаем.")
        return

    if message.entities:
        for entity in message.entities:
            if entity.type == 'bot_command':
                try:
                    await message.delete()
                    # logger.info(f"Удалена команда от пользователя {message.from_user.id} в чате {chat_id}")
                except Exception as e:
                    logger.error(f"Ошибка при удалении команды: {e}")
                return

    if message.sender_chat and message.sender_chat.id == CHANNEL_ID and not thread_id:
        try:
            await message.reply(first_post_message)
            # logger.info(f"Отправлено первое сообщение в ответ на пост ID: {message_id} в чате ID: {chat_id}")
            message_counts[chat_id][message_id] = 0
        except Exception as e:
            logger.error(f"Ошибка при отправке первого сообщения: {e}")
        return

    if thread_id and thread_id in message_counts[chat_id]:
        delete_count = message_counts[chat_id][thread_id]

        if delete_count < delete_message_count:
            try:
                await message.delete()
                # logger.info(f"Удалено сообщение ID: {message_id} в треде ID: {thread_id}")
                delete_count += 1
                message_counts[chat_id][thread_id] = delete_count

                if delete_count >= delete_message_count:
                    del message_counts[chat_id][thread_id]
                    # logger.info(f"Достигнуто максимальное количество удалений для треда ID: {thread_id}")
            except Exception as e:
                logger.error(f"Ошибка при удалении сообщения: {e}")

    if text:
        forbidden_words = await get_forbidden_words()
        threshold = 75
        lower_text = text.lower()
        for word in forbidden_words:
            similarity = fuzz.ratio(lower_text, word)
            pattern = create_regex_pattern(word)
            if re.search(pattern, lower_text) or similarity >= threshold:
                try:
                    await message.delete()
                    # logger.info(f"Удалено сообщение {message.message_id} с запрещённым словом '{word}'")
                except Exception as e:
                    logger.error(f"Ошибка при удалении сообщения {message.message_id}: {e}")
                break

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
            await reset_user_mute_count(user_id)
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

    await callback_query.message.answer(f"Вы хотите разбанить пользователя {callback_query.from_user.username}?", reply_markup=keyboard)
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
            await reset_user_mute_count(selected_user_id)
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
    await callback_query.message.answer("Введите новое описание для первого поста:")
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
    await callback_query.message.answer("Введите новое число сообщений для удаления:")
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
