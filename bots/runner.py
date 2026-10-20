from __future__ import annotations

import logging

from aiogram.types import Message

from bots import common as common_bot
from bots.search_ui import register_search_handlers
from core.models import SearchCandidate


_RAW_AGGREGATE_AND_SEND = common_bot._aggregate_and_send


async def _aggregate_and_cleanup_search(
    message: Message,
    candidate: SearchCandidate,
) -> None:
    """Replace/remove the bot's search-results message around aggregation.

    Direct one-result searches call the aggregator with the user's command
    message, so those messages are left untouched. Callback selections pass
    the bot-authored results message; that one is converted to a loading state
    and then removed after the anime card has been produced.
    """

    is_bot_search_message = bool(message.from_user and message.from_user.is_bot)

    if is_bot_search_message:
        try:
            await message.edit_text(
                f"Загружаю данные для «{candidate.title}»…",
                reply_markup=None,
            )
        except Exception:
            logging.debug(
                "Could not replace search results with loading state",
                exc_info=True,
            )

    await _RAW_AGGREGATE_AND_SEND(message, candidate)

    if not is_bot_search_message:
        return

    try:
        await message.delete()
        return
    except Exception:
        logging.debug("Could not delete completed search message", exc_info=True)

    # Some Telegram contexts do not allow deleting the old message. In that
    # case at least make sure the stale list of search results is gone.
    try:
        await message.edit_text(
            f"Выбрано: {candidate.title}",
            reply_markup=None,
        )
    except Exception:
        logging.debug(
            "Could not replace completed search message",
            exc_info=True,
        )


async def run_bot(*, use_custom_api: bool, mode_name: str) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logging.info("Bot mode: %s", mode_name)
    logging.info("Default search providers: %s", common_bot.SEARCH_SERVICE.provider_name)
    logging.info("Metadata sources: %s", ", ".join(source.name for source in common_bot.SOURCES))
    logging.info("Selectable /search providers are enabled")

    # build_dispatcher() resolves _aggregate_and_send from bots.common when its
    # callback runs. Replace that global with the cleanup wrapper so the same
    # behavior applies to both /anime and /search selections.
    common_bot._aggregate_and_send = _aggregate_and_cleanup_search

    bot = common_bot.create_bot(use_custom_api=use_custom_api)
    dp = common_bot.build_dispatcher(mode_name=mode_name)
    register_search_handlers(
        dp,
        aggregate_callback=_aggregate_and_cleanup_search,
        default_service=common_bot.SEARCH_SERVICE,
    )

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
