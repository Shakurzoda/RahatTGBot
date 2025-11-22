from __future__ import annotations

from typing import Optional

from aiogram.exceptions import TelegramBadRequest

from logger import get_logger

logger = get_logger("handlers")


async def safe_edit_message_text(
    bot,
    *,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup=None,
    order_id: Optional[int] = None,
    context: str = "client",
) -> Optional[str]:
    """Safely edit message text without propagating TelegramBadRequest.

    Returns the exception text when TelegramBadRequest occurs so callers can
    optionally apply fallbacks (e.g., resending a message). Any exception is
    logged as a warning without raising.
    """

    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
        )
        return None
    except TelegramBadRequest as exc:  # pragma: no cover - network dependent
        exc_text = str(exc)
        logger.warning(
            "Не удалось отредактировать сообщение (%s) для заказа %s: %s",
            context,
            order_id,
            exc,
        )
        return exc_text


async def safe_edit_message_reply_markup(
    bot,
    *,
    chat_id: int,
    message_id: int,
    reply_markup=None,
    order_id: Optional[int] = None,
    context: str = "client",
) -> Optional[str]:
    """Safely edit message reply markup without raising TelegramBadRequest."""

    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=reply_markup,
        )
        return None
    except TelegramBadRequest as exc:  # pragma: no cover - network dependent
        exc_text = str(exc)
        logger.warning(
            "Не удалось обновить клавиатуру сообщения (%s) для заказа %s: %s",
            context,
            order_id,
            exc,
        )
        return exc_text
