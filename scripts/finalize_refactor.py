from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent if (Path(__file__).resolve().parent / "core").is_dir() else Path.cwd()


def write(path: str, text: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def insert_after_future(text: str, import_line: str) -> str:
    if import_line in text:
        return text
    marker = "from __future__ import annotations\n"
    if marker not in text:
        raise RuntimeError("missing future import")
    return text.replace(marker, marker + "\n" + import_line + "\n", 1)


write(
    "core/score_summary.py",
    '''from __future__ import annotations\n\nimport math\nfrom statistics import fmean\nfrom typing import Iterable\n\n\ndef valid_scores(values: Iterable[object]) -> list[float]:\n    result: list[float] = []\n    for raw in values:\n        try:\n            score = float(raw)\n        except (TypeError, ValueError):\n            continue\n        if math.isfinite(score) and 0.0 <= score <= 10.0:\n            result.append(score)\n    return result\n\n\ndef consensus_score(values: Iterable[object]) -> float | None:\n    """Equal-source arithmetic mean on the common 0..10 score scale.\n\n    Source audience sizes are deliberately not used as weights because the\n    provider user populations overlap and are not independent samples.\n    """\n    scores = valid_scores(values)\n    return round(fmean(scores), 2) if scores else None\n''',
)

score_hits: list[Path] = []
for path in (ROOT / "services").glob("*.py"):
    text = path.read_text(encoding="utf-8")
    if "score_average" not in text:
        continue
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    changed = False
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(
            (isinstance(target, ast.Name) and target.id == "score_average")
            or (isinstance(target, ast.Attribute) and target.attr == "score_average")
            for target in targets
        ):
            continue
        names = {child.id for child in ast.walk(node.value) if isinstance(child, ast.Name)}
        candidate = "score_values" if "score_values" in names else ("scores" if "scores" in names else None)
        if candidate is None:
            raise RuntimeError(f"unrecognized score_average expression in {path}")
        start, end = node.lineno - 1, node.end_lineno
        indent = lines[start][: len(lines[start]) - len(lines[start].lstrip())]
        target_text = ast.unparse(targets[0])
        lines[start:end] = [f"{indent}{target_text} = consensus_score({candidate})\n"]
        changed = True
        break
    if changed:
        updated = insert_after_future("".join(lines), "from core.score_summary import consensus_score")
        path.write_text(updated, encoding="utf-8")
        score_hits.append(path)
if len(score_hits) != 1:
    raise RuntimeError(f"expected exactly one score-average assignment, got {score_hits}")

write(
    "bots/telegram/editing.py",
    '''from __future__ import annotations\n\nfrom typing import Any\n\nfrom bots.telegram.card.constants import STANDARD_MESSAGE_LIMIT\nfrom bots.telegram.card.renderer import split_text\n\n\nasync def edit_text_chunks(\n    message: Any,\n    text_value: str,\n    *,\n    reply_markup: Any = None,\n    locale: str = "ru",\n) -> None:\n    """Edit the original message and preserve every overflow chunk.\n\n    The keyboard stays attached to the original edited message; continuation\n    chunks are plain follow-up messages so callback ownership remains stable.\n    """\n    chunks = split_text(text_value, STANDARD_MESSAGE_LIMIT, locale=locale)\n    if not chunks:\n        chunks = [text_value]\n    await message.edit_text(text=chunks[0], reply_markup=reply_markup)\n    for chunk in chunks[1:]:\n        await message.answer(chunk)\n''',
)

fallback_hits: list[Path] = []
for path in (ROOT / "bots" / "telegram").rglob("*.py"):
    if path.name == "editing.py":
        continue
    text = path.read_text(encoding="utf-8")
    if "split_text" not in text or "[0]" not in text:
        continue
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    replacements: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Await):
            continue
        call = node.value.value
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute) or call.func.attr != "edit_text":
            continue
        text_kw = next((kw for kw in call.keywords if kw.arg == "text"), None)
        if text_kw is None or not isinstance(text_kw.value, ast.Subscript):
            continue
        sub = text_kw.value
        if not isinstance(sub.value, ast.Call) or not isinstance(sub.value.func, ast.Name) or sub.value.func.id != "split_text":
            continue
        slice_value = sub.slice.value if isinstance(sub.slice, ast.Constant) else None
        if slice_value != 0 or not sub.value.args:
            continue
        message_expr = ast.unparse(call.func.value)
        text_expr = ast.unparse(sub.value.args[0])
        locale_kw = next((kw for kw in sub.value.keywords if kw.arg == "locale"), None)
        locale_expr = ast.unparse(locale_kw.value) if locale_kw else '"ru"'
        markup_kw = next((kw for kw in call.keywords if kw.arg == "reply_markup"), None)
        markup_expr = ast.unparse(markup_kw.value) if markup_kw else "None"
        indent = lines[node.lineno - 1][: len(lines[node.lineno - 1]) - len(lines[node.lineno - 1].lstrip())]
        replacement = (
            f"{indent}await edit_text_chunks(\n"
            f"{indent}    {message_expr},\n"
            f"{indent}    {text_expr},\n"
            f"{indent}    reply_markup={markup_expr},\n"
            f"{indent}    locale={locale_expr},\n"
            f"{indent})\n"
        )
        replacements.append((node.lineno - 1, node.end_lineno, replacement))
    if replacements:
        for start, end, replacement in sorted(replacements, reverse=True):
            lines[start:end] = [replacement]
        updated = insert_after_future("".join(lines), "from bots.telegram.editing import edit_text_chunks")
        path.write_text(updated, encoding="utf-8")
        fallback_hits.append(path)
if not fallback_hits:
    raise RuntimeError("no truncating split_text(...)[0] fallback was found")

write(
    "tests/test_score_summary.py",
    '''from __future__ import annotations\n\nimport math\nimport unittest\n\nfrom core.score_summary import consensus_score, valid_scores\n\n\nclass ScoreSummaryTests(unittest.TestCase):\n    def test_equal_source_mean_keeps_sources_neutral(self) -> None:\n        self.assertEqual(consensus_score([8.0, 9.0, 7.0]), 8.0)\n\n    def test_invalid_values_are_excluded(self) -> None:\n        values = [8.0, None, math.nan, math.inf, -1, 11, "9"]\n        self.assertEqual(valid_scores(values), [8.0, 9.0])\n        self.assertEqual(consensus_score(values), 8.5)\n\n    def test_no_valid_scores_returns_none(self) -> None:\n        self.assertIsNone(consensus_score([None, "bad", math.nan, 99]))\n''',
)

write(
    "tests/test_editing.py",
    '''from __future__ import annotations\n\nimport unittest\nfrom unittest.mock import AsyncMock, patch\n\nfrom bots.telegram.editing import edit_text_chunks\n\n\nclass EditingFallbackTests(unittest.IsolatedAsyncioTestCase):\n    async def test_every_fallback_chunk_is_preserved(self) -> None:\n        message = AsyncMock()\n        keyboard = object()\n        with patch("bots.telegram.editing.split_text", return_value=["first", "second", "third"]):\n            await edit_text_chunks(message, "full", reply_markup=keyboard, locale="ru")\n        message.edit_text.assert_awaited_once_with(text="first", reply_markup=keyboard)\n        self.assertEqual([call.args[0] for call in message.answer.await_args_list], ["second", "third"])\n''',
)

readme = ROOT / "README.md"
text = readme.read_text(encoding="utf-8")
text = text.replace(
    "shared HTTP/typed error/source-health foundation уже есть, но часть крупных legacy source modules ещё постепенно переводится на этот общий transport слой;",
    "все активные HTTP source/search adapters используют общий connection pool и typed source errors; source-health/circuit breaker работает поверх resilience layer;",
)
text = text.replace(
    "character cross-source merge пока остаётся presentation/name-based и не является полноценной `CharacterIdentity`;",
    "`CharacterIdentity` отделён от anime/person identity; name-based merge остаётся только presentation fallback, когда source-ID не конфликтуют;",
)
readme.write_text(text, encoding="utf-8")

print("score:", [str(path.relative_to(ROOT)) for path in score_hits])
print("fallbacks:", [str(path.relative_to(ROOT)) for path in fallback_hits])
