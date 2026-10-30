from __future__ import annotations

import inspect
from io import BytesIO
import unittest
from unittest.mock import patch

from aiogram import Dispatcher
from PIL import Image

from bots.telegram.search import handlers as search_ui
from core.models import SearchCandidate
from search.registry import get_search_provider_map, get_search_providers
from services.identity.direct_lookup import DirectIdLookupService
from services.search.service import SearchService


class DummyDirectSource:
    source_key = "dummy"
    name = "Dummy"

    async def get_details(self, identity):
        return None


async def _noop_aggregate(message, candidate, owner_user_id):
    return None


class UnifiedSearchUiTests(unittest.TestCase):
    def test_scope_parser_normalizes_provider_order(self) -> None:
        self.assertEqual(
            search_ui._parse_scope("mal,shikimori"),
            ("shikimori", "mal"),
        )
        self.assertEqual(search_ui._parse_scope("ani"), ("anilist",))
        self.assertEqual(search_ui._parse_scope("kit"), ("kitsu",))
        self.assertEqual(search_ui._parse_scope("all"), search_ui.ALL_PROVIDER_KEYS)
        self.assertIsNone(search_ui._parse_scope("unknown-source"))

    def test_default_fast_search_uses_every_registered_provider(self) -> None:
        self.assertEqual(
            search_ui.DEFAULT_SEARCH_PROVIDER_KEYS,
            search_ui.ALL_PROVIDER_KEYS,
        )
        self.assertEqual(
            search_ui.DEFAULT_SEARCH_PROVIDER_KEYS,
            ("shikimori", "mal", "anilist", "kitsu"),
        )

    def test_default_scope_reuses_shared_search_service(self) -> None:
        default_service = SearchService(get_search_providers())

        service = search_ui._service_for(
            search_ui.DEFAULT_SEARCH_PROVIDER_KEYS,
            default_service,
            {str(key): provider for key, provider in get_search_provider_map().items()},
            {},
        )

        self.assertIs(service, default_service)

    def test_direct_id_parser_supports_plain_and_explicit_ids(self) -> None:
        supported = ("mal", "anilist", "shikimori", "kitsu")
        self.assertEqual(
            search_ui._parse_direct_query("37430", supported),
            (None, "37430"),
        )
        self.assertEqual(
            search_ui._parse_direct_query("mal:37430", supported),
            ("mal", "37430"),
        )
        self.assertEqual(
            search_ui._parse_direct_query("ani:101280", supported),
            ("anilist", "101280"),
        )
        self.assertEqual(
            search_ui._parse_direct_query("kitsu:44196", supported),
            ("kitsu", "44196"),
        )
        self.assertIsNone(search_ui._parse_direct_query("futuredb:42", supported))
        self.assertIsNone(search_ui._parse_direct_query("Tensei Slime", supported))

    def test_preview_contains_all_external_ids(self) -> None:
        session = search_ui.SearchSession(
            query="slime",
            owner_user_id=1,
            items=[],
        )
        candidate = SearchCandidate(
            title="Slime",
            year=2018,
            external_ids={
                "mal": "37430",
                "anilist": "101280",
                "shikimori": "37430",
                "futuredb": "77",
            },
        )

        value = search_ui._preview_text(session, candidate, locale="ru")

        self.assertIn("Slime", value)
        self.assertIn("Год: 2018", value)
        self.assertIn("MAL (MyAnimeList) / Jikan: 37430", value)
        self.assertIn("AniList: 101280", value)
        self.assertIn("Shikimori: 37430", value)
        self.assertIn("FUTUREDB: 77", value)

    def test_preview_pagination_marks_incomplete_count(self) -> None:
        keyboard = search_ui._preview_keyboard(
            "token",
            2,
            18,
            complete=False,
            locale="ru",
        )
        nav = keyboard.inline_keyboard[0]

        self.assertEqual(nav[0].text, "◀️")
        self.assertEqual(nav[1].text, "3/18+")
        self.assertEqual(nav[1].callback_data, "sp:token:sr:2:18:0")
        self.assertEqual(nav[2].text, "▶️")
        self.assertEqual(keyboard.inline_keyboard[1][0].text, "Подробнее")

    def test_preview_uses_only_first_cover_as_explicit_media(self) -> None:
        candidate = SearchCandidate(
            title="Naruto",
            external_ids={"mal": "20"},
            posters=[
                "https://example.invalid/first.jpg",
                "https://example.invalid/second.jpg",
            ],
        )

        rich = search_ui._preview_rich("Result", candidate)

        self.assertIn("tg://photo?id=cover", rich.html or "")
        self.assertIsNotNone(rich.media)
        self.assertEqual(len(rich.media or []), 1)
        self.assertEqual(
            (rich.media or [])[0].media.media,
            "https://example.invalid/first.jpg",
        )

    def test_preview_can_reuse_cached_telegram_file_id(self) -> None:
        candidate = SearchCandidate(
            title="Naruto",
            external_ids={"mal": "20"},
            posters=["https://example.invalid/cover.jpg"],
        )

        rich = search_ui._preview_rich(
            "Result",
            candidate,
            media_value="telegram-file-id",
        )

        self.assertEqual(
            (rich.media or [])[0].media.media,
            "telegram-file-id",
        )

    def test_uploaded_webp_is_normalized_to_jpeg(self) -> None:
        source = BytesIO()
        Image.new("RGBA", (32, 24), (255, 0, 0, 128)).save(source, format="WEBP")
        normalized = search_ui._normalize_uploaded_image(source.getvalue())
        with Image.open(BytesIO(normalized)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.mode, "RGB")
            self.assertEqual(image.size, (32, 24))

    def test_image_url_and_source_keyboard_support_quota_hiding(self) -> None:
        self.assertTrue(search_ui._is_image_url("https://example.com/frame.webp?x=1"))
        self.assertFalse(search_ui._is_image_url("not a url"))
        availability = {
            "trace_moe": search_ui.ImageSearchAvailability(
                "trace_moe", "trace.moe", True, 7, 100
            ),
            "whatanimeisthis": search_ui.ImageSearchAvailability(
                "whatanimeisthis", "What Anime Is This", False, 0, 5
            ),
        }
        keyboard = search_ui._image_source_keyboard("token", availability, "ru")
        self.assertIsNotNone(keyboard)
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertIn("trace.moe · 7/100", labels)
        self.assertNotIn("What Anime Is This · 0", labels)
        self.assertNotIn("Оба источника", labels)

    def test_image_preview_includes_evidence_and_retry_entrypoint(self) -> None:
        candidate = SearchCandidate(
            title="Example",
            external_ids={"anilist": "42"},
        )
        match = search_ui.ImageSearchMatch(
            "trace_moe",
            "trace.moe",
            "42",
            0.934,
            episode="3",
            from_seconds=75.2,
        )
        session = search_ui.SearchSession(
            query="image",
            owner_user_id=1,
            items=[candidate],
            image_matches=[[match]],
            image_input_token="input-token",
        )
        value = search_ui._preview_text(
            session, candidate, locale="ru", matches=[match]
        )
        keyboard = search_ui._preview_keyboard(
            "result-token",
            0,
            1,
            complete=True,
            locale="ru",
            image_search=True,
        )
        self.assertIn("Результат поиска по изображению", value)
        self.assertIn("trace.moe: 93.4% · серия 3 · таймкод 1:15", value)
        self.assertEqual(keyboard.inline_keyboard[-1][0].text, "Нет нужного тайтла?")
        self.assertEqual(
            keyboard.inline_keyboard[-1][0].callback_data, "in:result-token"
        )

    def test_legacy_search_command_is_not_registered(self) -> None:
        source = inspect.getsource(search_ui.register_search_handlers)
        self.assertNotIn('Command("search")', source)
        self.assertIn('Command("anime")', source)

    def test_handlers_register_on_real_dispatcher(self) -> None:
        dispatcher = Dispatcher()
        initial_message_handlers = len(dispatcher.message.handlers)
        initial_callback_handlers = len(dispatcher.callback_query.handlers)

        search_ui.register_search_handlers(
            dispatcher,
            aggregate_callback=_noop_aggregate,
            default_service=SearchService(get_search_providers()),
            direct_lookup=DirectIdLookupService((DummyDirectSource(),)),
            provider_map={
                str(key): provider
                for key, provider in get_search_provider_map().items()
            },
            image_search_service=object(),
            image_search_max_bytes=20 * 1024 * 1024,
            input_ttl_seconds=300,
        )

        self.assertEqual(
            len(dispatcher.message.handlers) - initial_message_handlers,
            3,
        )
        self.assertEqual(
            len(dispatcher.callback_query.handlers) - initial_callback_handlers,
            10,
        )

    def test_search_ui_keeps_card_runtime_outside_search_module(self) -> None:
        self.assertFalse(hasattr(search_ui, "ANIME_SESSIONS"))
        self.assertFalse(hasattr(search_ui, "AGGREGATOR"))
        self.assertFalse(hasattr(search_ui, "build_dispatcher"))
        self.assertFalse(hasattr(search_ui, "run_bot"))
        self.assertFalse(hasattr(search_ui, "PROVIDERS"))
        self.assertFalse(hasattr(search_ui, "SERVICES"))

    def test_search_ui_exports_no_import_time_session_stores(self) -> None:
        for name in ("SESSIONS", "SCOPE_SESSIONS", "PENDING_INPUTS"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(search_ui, name))

    def test_search_ui_state_is_owned_by_each_registration(self) -> None:
        providers = {
            str(key): provider for key, provider in get_search_provider_map().items()
        }

        def register() -> search_ui.SearchUiState:
            return search_ui.register_search_handlers(
                Dispatcher(),
                aggregate_callback=_noop_aggregate,
                default_service=SearchService(tuple(providers.values())),
                direct_lookup=DirectIdLookupService((DummyDirectSource(),)),
                provider_map=providers,
                image_search_service=object(),
                image_search_max_bytes=20 * 1024 * 1024,
                input_ttl_seconds=300,
            )

        first = register()
        second = register()
        self.assertIsNot(first.sessions, second.sessions)
        self.assertIsNot(first.pending_inputs, second.pending_inputs)
        self.assertIsNot(first.service_cache, second.service_cache)


class InitialSearchPreviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_preview_sends_then_upgrades_same_message_to_rich_cover(
        self,
    ) -> None:
        class SentMessage:
            def __init__(self) -> None:
                self.edits = []

            async def edit_text(self, *args, **kwargs):
                self.edits.append((args, kwargs))
                return True

        class IncomingMessage:
            def __init__(self) -> None:
                self.answers = []
                self.sent = SentMessage()

            async def answer(self, *args, **kwargs):
                self.answers.append((args, kwargs))
                return self.sent

        candidate = SearchCandidate(
            title="Example Hero",
            external_ids={"mal": "10"},
            posters=["https://example.invalid/full.jpg"],
        )
        session = search_ui.SearchSession(
            query="Example Hero",
            owner_user_id=1,
            items=[candidate],
        )
        message = IncomingMessage()

        with patch.object(search_ui, "get_user_locale", return_value="ru"):
            await search_ui._send_preview(
                message,
                "token",
                session,
                0,
                edit=False,
            )

        self.assertEqual(len(message.answers), 1)
        self.assertEqual(len(message.sent.edits), 1)
        edit_kwargs = message.sent.edits[0][1]
        self.assertIn("rich_message", edit_kwargs)
        rich = edit_kwargs["rich_message"]
        self.assertEqual(
            (rich.media or [])[0].media.media,
            "https://example.invalid/full.jpg",
        )


if __name__ == "__main__":
    unittest.main()
