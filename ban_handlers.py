
from aiogram import F, Router
import logging
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton,
    InlineKeyboardMarkup, ChatPermissions
)

from config.config_bot import bot, GROUP_ID, ADMINS, CHANNEL_ID
from database import (

    get_user_data, reset_user_mute_count, get_permanently_banned_users,update_status_to_normal, delete_user

)
from show_handlers import is_user_admin

router = Router()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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