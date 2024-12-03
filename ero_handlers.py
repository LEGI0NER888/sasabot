##############
###ЭРО-боты###
##############

from aiogram.enums import ParseMode
import logging, math
from aiogram import F, Router
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton,
    InlineKeyboardMarkup, ChatPermissions
)
from show_handlers import is_user_admin
from config.config_bot import bot, GROUP_ID
from database import (

    get_user_data, delete_user, update_user_list,
    get_suspicious_users, get_violator_users, add_banned_user

)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
router = Router()

# Константы для пагинации
USERS_PER_PAGE = 10

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

# Обработчик для показа списка подозрительных пользователей с пагинацией
@router.callback_query(lambda c: c.data.startswith('show_suspicious_users'))
async def show_suspicious_users(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        return

    # Извлекаем номер страницы из callback_data
    try:
        parts = callback_query.data.split('_')
        if len(parts) > 3:
            # Предполагаем формат: show_suspicious_users_page_X
            page_number = int(parts[-1])
        else:
            page_number = 1
    except:
        page_number = 1

    suspicious_users = await get_suspicious_users()

    if suspicious_users:
        total_users = len(suspicious_users)
        total_pages = math.ceil(total_users / USERS_PER_PAGE)
        page_number = max(1, min(page_number, total_pages))  # Ограничиваем номер страницы

        start_index = (page_number - 1) * USERS_PER_PAGE
        end_index = start_index + USERS_PER_PAGE
        current_page_users = suspicious_users[start_index:end_index]

        keyboard_buttons = []
        for user in current_page_users:
            # Получаем полное имя пользователя через API
            try:
                user_chat = await bot.get_chat(user['user_id'])
                user_full_name = user_chat.full_name
                username = user_chat.username
                if username:
                    user_text = f"@{username}"
                else:
                    user_text = user_full_name
            except:
                user_text = f"ID: {user['user_id']}"

            button = InlineKeyboardButton(
                text=user_text,
                callback_data=f"select_suspicious_user_{user['user_id']}"
            )
            keyboard_buttons.append([button])  # Каждая кнопка в отдельной строке

        # Кнопки навигации
        navigation_buttons = []
        if page_number > 1:
            navigation_buttons.append(
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"show_suspicious_users_page_{page_number - 1}"
                )
            )
        if page_number < total_pages:
            navigation_buttons.append(
                InlineKeyboardButton(
                    text="Вперед ➡️",
                    callback_data=f"show_suspicious_users_page_{page_number + 1}"
                )
            )

        # Добавляем кнопки навигации, если необходимо
        if navigation_buttons:
            keyboard_buttons.append(navigation_buttons)

        # Кнопки действий
        action_buttons = [
            InlineKeyboardButton(
                text="🔒 Забанить всех",
                callback_data="ban_all_suspicious_users"
            ),
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data="update_user_list"
            ),
            InlineKeyboardButton(
                text="❌ Закрыть",
                callback_data="close_message"
            )
        ]
        keyboard_buttons.append(action_buttons)

        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        try:
            await callback_query.message.answer(
                "Список подозрительных пользователей:",
                reply_markup=kb
            )
        except:
            pass
    else:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Закрыть", callback_data="close_message")]]
        )
        try:
            await callback_query.message.answer(
                "Нет подозрительных пользователей.",
                reply_markup=kb
            )
        except:
            pass

    await callback_query.answer()

# Обработчик кнопки "Обновить"
@router.callback_query(lambda c: c.data == "update_user_list")
async def update_user_list_handler(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        await callback_query.answer("У вас нет прав для выполнения этого действия.", show_alert=True)
        return

    await update_user_list()
    await callback_query.answer("Список пользователей обновлен.", show_alert=True)

    # Обновляем текущее сообщение с обновленным списком пользователей
    # Например, повторно вызываем функцию отображения списка нарушителей
    await show_violator_users(callback_query)


# Обработчик выбора подозрительного пользователя с пагинацией
@router.callback_query(lambda c: c.data.startswith('select_suspicious_user_'))
async def select_suspicious_user(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        await callback_query.answer("У вас нет прав для выполнения этого действия.", show_alert=True)
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
            [
                InlineKeyboardButton(
                    text="✅ Забанить",
                    callback_data=f"ban_suspicious_user_{selected_user_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Удалить из пула",
                    callback_data=f"remove_suspicious_user_{selected_user_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="close_message"
                )
            ]
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
        await callback_query.answer("Пользователь не найден.", show_alert=True)
        try:
            await callback_query.message.delete()
        except:
            pass


# Обработчик для показа списка нарушителей с пагинацией
@router.callback_query(lambda c: c.data.startswith('show_violator_users'))
async def show_violator_users(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        await callback_query.answer("У вас нет прав для выполнения этого действия.", show_alert=True)
        return

    # Извлекаем номер страницы из callback_data
    try:
        _, _, page = callback_query.data.partition('_')
        page_number = int(page) if page.isdigit() else 1
    except:
        page_number = 1

    violator_users = await get_violator_users()

    if violator_users:
        total_users = len(violator_users)
        total_pages = math.ceil(total_users / USERS_PER_PAGE)
        page_number = max(1, min(page_number, total_pages))  # Ограничиваем номер страницы

        start_index = (page_number - 1) * USERS_PER_PAGE
        end_index = start_index + USERS_PER_PAGE
        current_page_users = violator_users[start_index:end_index]

        keyboard_buttons = []
        for user in current_page_users:
            # Получаем полное имя пользователя через API
            try:
                user_chat = await bot.get_chat(user['user_id'])
                user_full_name = user_chat.full_name
            except:
                user_full_name = f"ID: {user['user_id']}"
            user_text = user_full_name
            button = InlineKeyboardButton(text=user_text, callback_data=f"select_violator_user_{user['user_id']}")
            keyboard_buttons.append([button])  # Каждая кнопка в отдельной строке

        # Кнопки навигации
        navigation_buttons = []
        if page_number > 1:
            navigation_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"show_violator_users_{page_number - 1}"))
        if page_number < total_pages:
            navigation_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"show_violator_users_{page_number + 1}"))

        # Добавляем кнопки навигации, если необходимо
        if navigation_buttons:
            keyboard_buttons.append(navigation_buttons)

        # Кнопки действий
        action_buttons = [
            InlineKeyboardButton(text="🔒 Забанить всех", callback_data="ban_all_violator_users"),
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data="update_user_list"
            ),
            InlineKeyboardButton(text="❌ Закрыть", callback_data="close_message")
        ]
        keyboard_buttons.append(action_buttons)

        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        try:
            await callback_query.message.answer("Список нарушителей:", reply_markup=kb)
        except:
            pass
    else:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Закрыть", callback_data="close_message")]]
        )
        try:
            await callback_query.message.answer("Нет нарушителей.", reply_markup=kb)
        except:
            pass

    await callback_query.answer()

# Обработчик выбора нарушителя
@router.callback_query(lambda c: c.data.startswith('select_violator_user_'))
async def select_violator_user(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await is_user_admin(user_id):
        await callback_query.answer("У вас нет прав для выполнения этого действия.", show_alert=True)
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
            [InlineKeyboardButton(text="✅ Забанить", callback_data=f"ban_violator_user_{selected_user_id}")],
            [InlineKeyboardButton(text="🚫 Удалить из пула", callback_data=f"remove_violator_user_{selected_user_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="close_message")]
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
        await callback_query.answer("Пользователь не найден.", show_alert=True)
        try:
            await callback_query.message.delete()
        except:
            pass



# Обработчик бана подозрительного пользователя
@router.callback_query(lambda c: c.data.startswith('ban_suspicious_user_'))
async def ban_suspicious_user(callback_query: CallbackQuery):
    admin_user_id = callback_query.from_user.id
    if not await is_user_admin(admin_user_id):
        return
    message_id = callback_query.message.message_id
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
        await callback_query.message.delete(message_id=message_id)
        await callback_query.message.delete(message_id=message_id-2)

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