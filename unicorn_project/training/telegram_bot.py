"""
Telegram bot utilities for handling bot interactions and messaging.
"""
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from django.conf import settings

logger = logging.getLogger(__name__)


class TelegramBotService:
    """Service for interacting with Telegram Bot API."""

    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not self.bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN not configured")

    def get_bot_token(self):
        """Get the bot token from environment."""
        return self.bot_token

    def get_bot_username(self):
        """Get bot username (requires API call - cached in settings ideally)."""
        # This would require making an API call. For now, you'll need to set it in settings
        return getattr(settings, "TELEGRAM_BOT_USERNAME", "your_bot_username")

    async def send_message(self, chat_id: int, text: str, reply_markup=None):
        """
        Send a message to a user via Telegram.
        
        Args:
            chat_id: Telegram user ID
            text: Message text
            reply_markup: Optional inline keyboard markup
        """
        try:
            from telegram import Bot
            bot = Bot(token=self.bot_token)
            await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
            logger.info(f"Message sent to {chat_id}")
        except Exception as e:
            logger.error(f"Failed to send message to {chat_id}: {e}")
            raise

    def create_linking_qr_code(self, linking_token: str) -> str:
        """
        Create a deep link URL for linking a Telegram account.
        
        Args:
            linking_token: Unique token for this linking attempt
            
        Returns:
            Deep link URL to the Telegram bot with the linking token
        """
        bot_username = self.get_bot_username()
        # Deep link format: https://t.me/bot_username?start=token
        return f"https://t.me/{bot_username}?start={linking_token}"

    def verify_telegram_data(self, telegram_id: int, data: dict) -> bool:
        """
        Verify telegram data received from the bot.
        You can add signature verification here if needed.
        
        Args:
            telegram_id: The Telegram user ID
            data: Dictionary with user data from Telegram
            
        Returns:
            True if data is valid, False otherwise
        """
        # Basic validation - in production, implement proper signature verification
        return bool(telegram_id) and telegram_id > 0


def get_telegram_service() -> TelegramBotService:
    """Factory function to get Telegram service instance."""
    return TelegramBotService()
