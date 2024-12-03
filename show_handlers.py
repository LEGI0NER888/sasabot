

from aiogram.enums import ParseMode
import logging
from aiogram import F, Router
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton,
    InlineKeyboardMarkup
)

from aiogram.filters import CommandStart
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext



from config.config_bot import bot, GROUP_ID, ADMINS, CHANNEL_ID
from database import (
    get_setting, update_setting,

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










