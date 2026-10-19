import asyncio

from bots.common import run_bot


if __name__ == "__main__":
    asyncio.run(
        run_bot(
            use_custom_api=True,
            mode_name="custom tg-bot-api",
        )
    )
