###################################################
####добавление, удаление подозрений в никнеймах####
###################################################

from aiogram import F, Router
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton,
    InlineKeyboardMarkup
)


from aiogram.fsm.context import FSMContext

from show_handlers import is_user_admin, FunctionStates
from database import (
    get_forbidden_nickname_emojis, get_forbidden_nickname_words, add_forbidden_nickname_emoji, 
    add_forbidden_nickname_word, remove_forbidden_nickname_emoji, remove_forbidden_nickname_word
)
router = Router()
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
