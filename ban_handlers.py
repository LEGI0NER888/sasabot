from aiogram import F, Router
from aiogram.enums import ParseMode
import logging
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton,
    InlineKeyboardMarkup, ChatPermissions
)

from config.config_bot import bot, GROUP_ID, ADMINS, CHANNEL_ID
from database import (
    get_user_data, reset_user_mute_count, get_permanently_banned_users, update_status_to_normal, delete_user
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
            # Получаем полное имя пользователя через API
            try:
                user_chat = await bot.get_chat(user['user_id'])
                user_full_name = user_chat.full_name
                username = user_chat.username
                if user_full_name:
                    user_text = user_full_name
                else:
                    user_text = f"@{username}" if username else f"ID: {user['user_id']}"
            except:
                user_text = f"ID: {user['user_id']}"

            button = InlineKeyboardButton(
                text=user_text,
                callback_data=f"select_banned_user_{user['user_id']}"
            )
            keyboard_buttons.append([button])  # Каждая кнопка в отдельной строке

        # Кнопки навигации
        nav_buttons = []
        if page_number > 1:
            nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"show_permanently_banned_users:page={page_number - 1}"))
        if page_number < total_pages:
            nav_buttons.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"show_permanently_banned_users:page={page_number + 1}"))

        # Кнопки действий
        action_buttons = [
            InlineKeyboardButton(text="🗑️ Очистить всех", callback_data="clear_all_banned_users"),
            InlineKeyboardButton(text="❌ Закрыть", callback_data="close_message")
        ]

        # Собираем клавиатуру
        keyboard = keyboard_buttons
        if nav_buttons:
            keyboard.append(nav_buttons)
        keyboard.append(action_buttons)

        kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

        try:
            await callback_query.message.answer("Список забаненных пользователей:", reply_markup=kb)
        except Exception:
            await callback_query.message.edit_reply_markup(reply_markup=kb)

    else:
        await callback_query.message.answer("Нет перманентно забаненных пользователей.", reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Закрыть", callback_data="close_message")]]
        ))
    await callback_query.answer()

# Обработчик подтверждения очистки всех забаненных пользователей
@router.callback_query(lambda c: c.data == 'clear_all_banned_users')
async def confirm_clear_all_banned_users(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить всех", callback_data="clear_all_confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_clear_all")]
    ])

    await callback_query.message.answer("Вы уверены, что хотите удалить всех забаненных пользователей из базы данных?", reply_markup=confirm_kb)
    await callback_query.answer()

# Обработчик отмены очистки всех
@router.callback_query(lambda c: c.data == 'cancel_clear_all')
async def cancel_clear_all(callback_query: CallbackQuery):
    await callback_query.answer("Действие отменено.")
    await callback_query.message.delete()

# Обработчик выполнения очистки всех забаненных пользователей
@router.callback_query(lambda c: c.data == 'clear_all_confirm')
async def clear_all_confirm(callback_query: CallbackQuery):
    admin_user_id = callback_query.from_user.id
    if not await is_user_admin(admin_user_id):
        return

    banned_users = await get_permanently_banned_users()

    if not banned_users:
        await callback_query.answer("Нет пользователей для удаления.", show_alert=True)
        await callback_query.message.delete()
        return

    success_count = 0
    for user in banned_users:
        user_id = user['user_id']
        try:
            # Удаляем пользователя из базы данных
            await delete_user(user_id)
            success_count += 1
            # logger.info(f"Пользователь {user_id} удален из базы данных администратором {admin_user_id}.")
        except Exception as e:
            logger.error(f"Ошибка при удалении пользователя {user_id}: {e}")

    await callback_query.answer(f"Удалено пользователей: {success_count}.", show_alert=True)
    await callback_query.message.delete()

# Обработчик выбора забаненного пользователя для действий
@router.callback_query(lambda c: c.data.startswith('select_banned_user_'))
async def select_banned_user(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    try:
        selected_user_id = int(callback_query.data.split('_')[-1])
    except ValueError:
        await callback_query.answer("Некорректный ID пользователя.", show_alert=True)
        return

    user_data = await get_user_data(selected_user_id)
    if user_data:
        try:
            user_chat = await bot.get_chat(selected_user_id)
            username = user_chat.username
            if username:
                mention = f'@{username}'
                user_profile_link = f'<a href="https://t.me/{username}">{mention}</a>'
            else:
                user_full_name = user_chat.full_name
                link = f'tg://user?id={selected_user_id}'
                user_profile_link = f'<a href="{link}">{user_full_name}</a>'
        except:
            user_profile_link = f"ID: {selected_user_id}"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Разбанить", callback_data=f"unban_user_{selected_user_id}")],
            [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_banned_user_{selected_user_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_unban_user")]
        ])

        try:
            await callback_query.message.answer(
                f"Выберите действие для пользователя {user_profile_link}:",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
        except:
            pass
        await callback_query.answer()
    else:
        await callback_query.answer("Пользователь не найден среди забаненных.", show_alert=True)
        try:
            await callback_query.message.delete()
        except:
            pass

# Обработчик удаления забаненного пользователя из базы данных
@router.callback_query(lambda c: c.data.startswith('delete_banned_user_'))
async def delete_banned_user(callback_query: CallbackQuery):
    admin_user_id = callback_query.from_user.id
    if not await is_user_admin(admin_user_id):
        return

    try:
        selected_user_id = int(callback_query.data.split('_')[-1])
    except ValueError:
        await callback_query.answer("Некорректный ID пользователя.", show_alert=True)
        return

    user_data = await get_user_data(selected_user_id)
    if user_data:
        try:
            await delete_user(selected_user_id)
            await callback_query.answer(f"Пользователь {selected_user_id} удален из базы данных.", show_alert=True)
            await callback_query.message.delete()
            # logger.info(f"Пользователь {selected_user_id} удален из базы данных администратором {admin_user_id}.")
        except Exception as e:
            logger.error(f"Ошибка при удалении пользователя {selected_user_id}: {e}")
            await callback_query.answer(f"Не удалось удалить пользователя {selected_user_id}.", show_alert=True)
    else:
        await callback_query.answer("Пользователь не найден в базе данных.", show_alert=True)
        await callback_query.message.delete()

# Обработчик отмены действия
@router.callback_query(lambda c: c.data == 'cancel_unban_user')
async def cancel_unban_user(callback_query: CallbackQuery):
    await callback_query.answer("Действие отменено.")
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
            await callback_query.bot.unban_chat_member(
                chat_id=chat_id,
                user_id=selected_user_id
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
