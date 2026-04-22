"""
Telegram Bot integration for Contract Management System.

Handles notifications, reminders, and user interactions.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logger = logging.getLogger(__name__)


class TelegramBotManager:
    """Manages Telegram bot operations and notifications."""

    def __init__(self, bot_token: str | None = None):
        """Initialize the Telegram bot manager.

        Args:
            bot_token: Telegram bot token. Defaults to TELEGRAM_BOT_TOKEN env var.
        """
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN not set. Bot features will be disabled.")
            self.application = None
            return

        self.application = Application.builder().token(self.bot_token).build()
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Register command handlers."""
        if self.application is None:
            return

        self.application.add_handler(CommandHandler("start", self._start))

    async def _start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command.

        Args:
            update: Telegram update object.
            context: Telegram context object.
        """
        user = update.effective_user
        welcome_msg = (
            f"👋 שלום {user.first_name}!\n\n"
            "ברוכים הבאים לממערכת ניהול החוזים.\n"
            "כדי להתחיל, אנא הזן את קוד הלקוח (Tenant ID) שלך:"
        )
        await update.message.reply_text(welcome_msg)

    async def send_alert(self, chat_id: int, message: str) -> bool:
        """Send an alert message to a specific user.

        Args:
            chat_id: Telegram chat ID of the recipient.
            message: Message to send.

        Returns:
            True if message was sent successfully, False otherwise.
        """
        if self.application is None or self.application.bot is None:
            logger.error("Bot not initialized. Cannot send alert.")
            return False

        try:
            await self.application.bot.send_message(chat_id=chat_id, text=message)
            logger.info(f"Alert sent to chat_id {chat_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send alert to {chat_id}: {e}")
            return False

    def start(self) -> None:
        """Start the bot polling."""
        if self.application is None:
            logger.warning("Bot not initialized. Cannot start polling.")
            return

        logger.info("Starting Telegram bot polling...")
        self.application.run_polling()


# Singleton instance for easy access from other modules
_bot_manager: TelegramBotManager | None = None


def get_bot_manager() -> TelegramBotManager:
    """Get or create the bot manager singleton.

    Returns:
        TelegramBotManager instance.
    """
    global _bot_manager
    if _bot_manager is None:
        _bot_manager = TelegramBotManager()
    return _bot_manager


async def send_contract_reminder(chat_id: int, contract_title: str, days_remaining: int) -> bool:
    """Send a contract reminder alert.

    Args:
        chat_id: Telegram chat ID.
        contract_title: Title of the contract.
        days_remaining: Days until renewal/expiry.

    Returns:
        True if sent successfully, False otherwise.
    """
    bot_manager = get_bot_manager()
    message = f"⏰ תזכורת: החוזה '{contract_title}' מסתיים בעוד {days_remaining} ימים"
    return await bot_manager.send_alert(chat_id, message)
