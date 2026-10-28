from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from services.access_control import is_telegram_admin
from services.rate_limits import PersonalRateLimiter, get_personal_rate_limiter
from services.user_settings import get_user_locale


_TEXT = {
    "ru": (
        "Ошибка: Too Many Requests\n"
        "Слишком много запросов. Повторите через {seconds} секунд."
    ),
    "en": (
        "Error: Too Many Requests\nToo many requests. Try again in {seconds} seconds."
    ),
}


def _notice(locale: str, retry_after: int) -> str:
    language = "en" if locale == "en" else "ru"
    return _TEXT[language].format(seconds=max(1, int(retry_after)))


class TelegramRateLimitMiddleware(BaseMiddleware):
    """Apply per-user limits without sharing a bucket between accounts.

    Administrators bypass only this personal limit. Outbound source limiters live
    below the platform layer and therefore still apply to administrators.
    """

    def __init__(self, limiter: PersonalRateLimiter | None = None) -> None:
        self._limiter = limiter

    @property
    def limiter(self) -> PersonalRateLimiter:
        return self._limiter or get_personal_rate_limiter()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)

        user_id = int(user.id)
        if is_telegram_admin(user_id):
            return await handler(event, data)

        if isinstance(event, CallbackQuery) and (event.data or "") == "noop":
            return await handler(event, data)

        decision = self.limiter.check("telegram", user_id)
        if decision.allowed:
            return await handler(event, data)

        locale = get_user_locale(user_id)
        notice = _notice(locale, decision.retry_after)
        if isinstance(event, CallbackQuery):
            await event.answer(notice, show_alert=True)
        elif isinstance(event, Message):
            await event.answer(notice)
        return None
