from __future__ import annotations

from collections.abc import Callable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bots.telegram.callbacks import (
    KeyedPageCallback,
    PagePickerCallback,
    SectionSourceCallback,
    TokenIndexCallback,
    ViewCallback,
)
from localization import text

PICKER_PAGE_SIZE = 30
PICKER_COLUMNS = 5


def _window_for(current: int) -> int:
    return max(0, int(current)) // PICKER_PAGE_SIZE


def card_picker_callback(token: str, route: str, current: int, total: int) -> str:
    return PagePickerCallback(
        "cp",
        token,
        route,
        current,
        total,
        _window_for(current),
    ).encode()


def search_picker_callback(token: str, current: int, total: int) -> str:
    return PagePickerCallback(
        "sp",
        token,
        "sr",
        current,
        total,
        _window_for(current),
    ).encode()


def _people_page(display_index: int, without_portrait_count: int) -> int:
    shown = max(1, int(display_index) + 1)
    without = max(0, int(without_portrait_count))
    return 0 if shown <= without else shown - without


def card_route_callback(token: str, route: str, index: int) -> str:
    """Build the existing callback for one picker selection.

    Routes deliberately stay compact because Telegram limits callback_data to 64 bytes.
    ``pv`` routes translate the visible "shown N/total" position used by people and
    character galleries back to their portrait-page number.
    """

    parts = route.split("~")
    kind = parts[0] if parts else ""
    index = max(0, int(index))

    if kind == "av" and len(parts) == 2:
        return ViewCallback(token, parts[1], index).encode()
    if kind == "ad" and len(parts) == 2:
        return KeyedPageCallback("ad", token, parts[1], index).encode()
    if kind == "as" and len(parts) == 3:
        return SectionSourceCallback(token, parts[1], parts[2], index).encode()
    if kind in {"ap", "ac", "at"} and len(parts) == 2:
        return KeyedPageCallback(kind, token, parts[1], index).encode()
    if kind == "apg" and len(parts) == 3:
        try:
            group_start = int(parts[2])
        except ValueError as exc:
            raise ValueError("Invalid episode-group page-picker route") from exc
        if group_start < 0:
            raise ValueError("Invalid episode-group page-picker route")
        return KeyedPageCallback("ap", token, parts[1], group_start + index).encode()

    if kind == "pv" and len(parts) >= 4:
        try:
            without = int(parts[-1])
        except ValueError as exc:
            raise ValueError("Invalid people page-picker route") from exc
        page = _people_page(index, without)
        target = parts[1]
        if target == "av" and len(parts) == 4:
            return ViewCallback(token, parts[2], page).encode()
        if target == "as" and len(parts) == 5:
            return SectionSourceCallback(token, parts[2], parts[3], page).encode()
        if target == "ac" and len(parts) == 4:
            return KeyedPageCallback("ac", token, parts[2], page).encode()

    raise ValueError(f"Unsupported page-picker route: {route}")


def _picker_keyboard(
    data: PagePickerCallback,
    *,
    locale: str,
    destination: Callable[[int], str],
) -> InlineKeyboardMarkup:
    total = max(1, int(data.total))
    current = max(0, min(int(data.current), total - 1))
    window_count = max(1, (total + PICKER_PAGE_SIZE - 1) // PICKER_PAGE_SIZE)
    window = max(0, min(int(data.window), window_count - 1))
    start = window * PICKER_PAGE_SIZE
    end = min(total, start + PICKER_PAGE_SIZE)

    buttons = [
        InlineKeyboardButton(
            text=(f"✓ {index + 1}" if index == current else str(index + 1)),
            callback_data=destination(index),
        )
        for index in range(start, end)
    ]
    rows = [
        buttons[index : index + PICKER_COLUMNS]
        for index in range(0, len(buttons), PICKER_COLUMNS)
    ]

    if window_count > 1:
        nav: list[InlineKeyboardButton] = []
        if window > 0:
            nav.append(
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=PagePickerCallback(
                        data.prefix,
                        data.token,
                        data.route,
                        current,
                        total,
                        window - 1,
                    ).encode(),
                )
            )
        nav.append(
            InlineKeyboardButton(
                text=f"{start + 1}–{end}/{total}",
                callback_data="noop",
            )
        )
        if window + 1 < window_count:
            nav.append(
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=PagePickerCallback(
                        data.prefix,
                        data.token,
                        data.route,
                        current,
                        total,
                        window + 1,
                    ).encode(),
                )
            )
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton(
                text=text("common", "back", locale=locale),
                callback_data=destination(current),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def card_picker_keyboard(
    data: PagePickerCallback,
    *,
    locale: str,
) -> InlineKeyboardMarkup:
    return _picker_keyboard(
        data,
        locale=locale,
        destination=lambda index: card_route_callback(data.token, data.route, index),
    )


def search_picker_keyboard(
    data: PagePickerCallback,
    *,
    locale: str,
) -> InlineKeyboardMarkup:
    if data.route != "sr":
        raise ValueError(f"Unsupported search page-picker route: {data.route}")
    return _picker_keyboard(
        data,
        locale=locale,
        destination=lambda index: TokenIndexCallback("sr", data.token, index).encode(),
    )
