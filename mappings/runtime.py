from __future__ import annotations

import asyncio
import logging

from mappings.config import mappings_auto_update, mappings_check_interval_seconds
from mappings.updater import update_if_stale


async def periodic_mapping_updates() -> None:
    """Refresh mappings.db in a worker thread without loading datasets into RAM."""
    if not mappings_auto_update():
        return

    while True:
        try:
            await asyncio.to_thread(update_if_stale)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("Background mapping database update failed")
        await asyncio.sleep(mappings_check_interval_seconds())
