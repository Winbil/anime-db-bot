from __future__ import annotations

import logging

from bots.common import (
    AGGREGATOR,
    SEARCH_SERVICE,
    SOURCES,
    _aggregate_and_send,
    build_dispatcher,
    create_bot,
)
from bots.search_ui import register_search_handlers


async def run_bot(*, use_custom_api: bool, mode_name: str) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logging.info("Bot mode: %s", mode_name)
    logging.info("Default search providers: %s", SEARCH_SERVICE.provider_name)
    logging.info("Metadata sources: %s", ", ".join(source.name for source in SOURCES))
    logging.info("Selectable /search providers are enabled")

    bot = create_bot(use_custom_api=use_custom_api)
    dp = build_dispatcher(mode_name=mode_name)
    register_search_handlers(
        dp,
        aggregate_callback=_aggregate_and_send,
        default_service=SEARCH_SERVICE,
    )

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
