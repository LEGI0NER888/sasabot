
from aiogram import F, Router
import logging
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton,
    InlineKeyboardMarkup, ChatPermissions
)

from database import (

    get_users_with_mutes_less_than_3,add_or_update_user

)
from show_handlers import is_user_admin

router = Router()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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