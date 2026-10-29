from __future__ import annotations

from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bots.telegram.callbacks import SettingsCallback
from localization import available_locales, locale_name, text
from services.users.settings import get_user_locale, set_user_locale

SETTINGS_PREFIX = "settings:"


def _settings_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=text("settings", "language_button", locale=locale),
                    callback_data=SettingsCallback("language").encode(),
                )
            ]
        ]
    )


def _language_keyboard(locale: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for value, flag in (("en", "🇬🇧"), ("ru", "🇷🇺"), ("ja", "🇯🇵")):
        if value not in available_locales():
            continue
        label = f"{flag} {locale_name(value, display_locale=value)}"
        if value == locale:
            label = "✓ " + label
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=SettingsCallback("locale", value).encode(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=text("settings", "back", locale=locale),
                callback_data=SettingsCallback("back").encode(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _settings_text(locale: str) -> str:
    language = locale_name(locale, display_locale=locale)
    return (
        f"{text('settings', 'title', locale=locale)}\n\n"
        f"{text('settings', 'current_language', locale=locale, language=language)}"
    )


def register_settings_handlers(dp: Dispatcher) -> None:
    @dp.message(Command("settings"))
    async def settings_handler(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else None
        locale = get_user_locale(user_id)
        await message.answer(
            _settings_text(locale),
            reply_markup=_settings_keyboard(locale),
        )

    @dp.callback_query(F.data == "settings:language")
    async def settings_language_callback(callback: CallbackQuery) -> None:
        locale = get_user_locale(callback.from_user.id)
        if callback.message is None:
            await callback.answer()
            return
        await callback.answer()
        await callback.message.edit_text(
            text("settings", "choose_language", locale=locale),
            reply_markup=_language_keyboard(locale),
        )

    @dp.callback_query(F.data.startswith("settings:locale:"))
    async def settings_locale_callback(callback: CallbackQuery) -> None:
        data = SettingsCallback.parse(callback.data)
        current_locale = get_user_locale(callback.from_user.id)
        if (
            data is None
            or data.action != "locale"
            or data.value not in available_locales()
        ):
            await callback.answer(
                text("settings", "unsupported_language", locale=current_locale),
                show_alert=True,
            )
            return

        locale = set_user_locale(callback.from_user.id, data.value)
        if callback.message is None:
            await callback.answer()
            return
        await callback.answer(
            text(
                "settings",
                "language_saved",
                locale=locale,
                language=locale_name(locale, display_locale=locale),
            )
        )
        await callback.message.edit_text(
            _settings_text(locale),
            reply_markup=_settings_keyboard(locale),
        )

    @dp.callback_query(F.data == "settings:back")
    async def settings_back_callback(callback: CallbackQuery) -> None:
        locale = get_user_locale(callback.from_user.id)
        if callback.message is None:
            await callback.answer()
            return
        await callback.answer()
        await callback.message.edit_text(
            _settings_text(locale),
            reply_markup=_settings_keyboard(locale),
        )
