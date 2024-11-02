# anti_spam.py
import asyncio
import logging
from aiogram import BaseMiddleware
from aiogram.types import Message, ChatPermissions
from database import get_setting, get_user, add_or_update_user
from datetime import datetime, timedelta
from config.config_bot import ADMINS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AntiSpamMiddleware(BaseMiddleware):
    def __init__(self):
        self.user_messages = {}  # Stores timestamps of user messages: {user_id: [timestamps]}
        self.spam_incidents = {}  # Stores the time of the last spam incident per user
        self.user_locks = {}      # Locks for synchronizing access per user
        self.logger = logging.getLogger(__name__)

    async def __call__(self, handler, event: Message, data):
        if await get_setting('anti_spam_enabled') == '0':
            return await handler(event, data)

        user_id = event.from_user.id
        chat_id = event.chat.id
        current_time = datetime.now()

        if event.chat.type not in ['group', 'supergroup']:
            return await handler(event, data)

        if str(user_id) in ADMINS:
            return await handler(event, data)

        # Initialize a lock for the user if it doesn't exist
        if user_id not in self.user_locks:
            self.user_locks[user_id] = asyncio.Lock()

        async with self.user_locks[user_id]:
            user_data = await get_user(user_id)
            if user_data and user_data['mute_count'] >= 3:
                try:
                    await event.bot.restrict_chat_member(
                        chat_id=chat_id,
                        user_id=user_id,
                        permissions=ChatPermissions(can_send_messages=False)
                    )
                    self.logger.info(f"User {user_id} is permanently muted and cannot send messages.")
                except Exception as e:
                    self.logger.error(f"Error muting user {user_id} in chat {chat_id}: {e}")
                return

            if user_data and user_data['last_mute_time']:
                time_since_last_mute = current_time - user_data['last_mute_time']
                if time_since_last_mute > timedelta(hours=1) and user_data['mute_count'] < 3:
                    user_data['mute_count'] = 0
                    user_data['last_mute_time'] = None
                    await add_or_update_user(user_id, chat_id, user_data['mute_count'], user_data['last_mute_time'])
                    self.logger.info(f"Reset mute count for user {user_id} after {time_since_last_mute}.")

            if user_id not in self.user_messages:
                self.user_messages[user_id] = []
            self.user_messages[user_id].append(current_time)

            # Keep only messages within the last 2 seconds
            self.user_messages[user_id] = [
                timestamp for timestamp in self.user_messages[user_id]
                if current_time - timestamp <= timedelta(seconds=2)
            ]

            if len(self.user_messages[user_id]) >= 3:
                # Check if the user had a recent spam incident
                last_spam_time = self.spam_incidents.get(user_id)
                if not last_spam_time or current_time - last_spam_time > timedelta(seconds=10):
                    # Increase mute count and save the incident time
                    await self.handle_spammer(event, user_id, chat_id, reason="spam")
                    self.spam_incidents[user_id] = current_time
                    self.user_messages[user_id] = []  # Reset message list after handling
                else:
                    # Delete the message as a warning
                    await event.bot.delete_message(chat_id=chat_id, message_id=event.message_id)
                    self.logger.info(f"Message from user {user_id} deleted as a warning.")
                return

        return await handler(event, data)

    async def handle_spammer(self, event, user_id, chat_id, reason):
        current_time = datetime.now()
        try:
            await event.bot.delete_message(chat_id=chat_id, message_id=event.message_id)
            user_data = await get_user(user_id)
            if not user_data:
                user_data = {'user_id': user_id, 'chat_id': chat_id, 'mute_count': 0, 'last_mute_time': None}

            user_data['mute_count'] += 1
            user_data['last_mute_time'] = current_time

            await add_or_update_user(user_id, chat_id, user_data['mute_count'], user_data['last_mute_time'])
            self.logger.info(f"User {user_id} received {user_data['mute_count']} mutes.")

            if user_data['mute_count'] == 1:
                await event.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(can_send_messages=False)
                )
                self.logger.info(f"User {user_id} temporarily muted for 10 seconds for {reason}.")
                asyncio.create_task(self.unmute_user_after_delay(event.bot, chat_id, user_id, delay=10))
            elif user_data['mute_count'] == 2:
                await event.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(can_send_messages=False)
                )
                self.logger.info(f"User {user_id} temporarily muted for 10 minutes for repeated {reason}.")
                asyncio.create_task(self.unmute_user_after_delay(event.bot, chat_id, user_id, delay=600))
            elif user_data['mute_count'] >= 3:
                await event.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(can_send_messages=False)
                )
                self.logger.info(f"User {user_id} permanently muted for repeated {reason}.")
        except Exception as e:
            self.logger.error(f"Error handling spammer {user_id}: {e}")

    async def unmute_user_after_delay(self, bot, chat_id, user_id, delay):
        try:
            await asyncio.sleep(delay)
            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(
                    can_send_messages=True
                )
            )
            self.logger.info(f"User {user_id} was unmuted after {delay} seconds.")
        except Exception as e:
            self.logger.error(f"Error unmuting user {user_id} after delay: {e}")
