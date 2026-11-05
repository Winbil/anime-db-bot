> **AI 支援プロジェクト:** AI の支援を受けて開発されています。

<p align="center">
  <a href="../README.md">English</a> · <a href="README.ru.md">Русский</a> · <strong>日本語</strong> · <a href="README.de.md">Deutsch</a> · <a href="README.es.md">Español</a> · <a href="README.fr.md">Français</a> · <a href="README.it.md">Italiano</a>
</p>

# anime-db-bot

[![Python](https://img.shields.io/badge/Python-3.11--3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![CI](https://github.com/anime-db-project/anime-db-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/anime-db-project/anime-db-bot/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-D22128.svg)](../LICENSE)

複数の独立したアニメデータベースを横断検索し、作品情報を一つの Telegram インターフェースに集約するボットです。エピソード、キャラクター、制作スタッフ、関連作品も閲覧できます。

## 主な機能

- 作品名、外部 ID、画像からの検索とページ送りに対応。
- 評価、あらすじ、放送情報、キャスト、スタッフ、関連作品、おすすめを統合表示。
- エピソード、OP/ED 情報、利用可能なスキップ区間を必要時に読み込み。
- 確認済みの ID 対応関係だけで作品を結合し、曖昧な一致を避けます。
- 永続的なユーザー設定、管理機能、ソース別レート制限、プロキシ、User-Agent 設定。
- 7 言語の UI に対応。ソース由来の文章は元の言語を尊重します。

## データソース

アニメのメタデータには MyAnimeList（Jikan は補助）、AniList、Shikimori、Kitsu、AniDB（クライアント登録が必要）、AniSearch を使用します。その他のサービスは特定の機能のみを提供します。

| 主な機能 | データソース |
| --- | --- |
| 検索とメタデータ | [MyAnimeList](https://myanimelist.net/) / [Jikan](https://jikan.moe/), [AniList](https://anilist.co/), [Shikimori](https://shikimori.one/), [Kitsu](https://kitsu.app/), [AniDB](https://anidb.net/), [AniSearch](https://www.anisearch.com/) |
| 追加評価 | [IMDb](https://www.imdb.com/) |
| 画像による作品検索 | [trace.moe](https://trace.moe/), [What Anime Is This](https://whatanimeisthis.com/) |
| エピソード・主題歌・スキップ区間 | [AnimeThemes](https://animethemes.moe/), [AniSkip](https://aniskip.com/), [Anime Skip](https://anime-skip.com/), [Baha Anime Skip](https://github.com/JacobLinCool/baha-anime-skip), [SkipDB](https://github.com/SkipDB-TV/skipdb) |

[Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db) がサービス間 ID の対応を提供します。SkipDB のタイムスタンプ機能は現在無効です。ソース一覧は全作品・全話の収録を保証するものではありません。

## クイックスタート

Python 3.11–3.14、Linux／macOS／Windows に対応します。リポジトリを取得し、共通ランチャーを使ってください。

```bash
git clone https://github.com/anime-db-project/anime-db-bot.git
cd anime-db-bot
python3 scripts/project.py setup
# .env.d/telegram.env に BOT_TOKEN を設定
python3 scripts/project.py check
python3 scripts/project.py run
```

Windows では `python3 scripts/project.py` の代わりに `py -3 scripts\project.py` を使います。バックグラウンド起動は `python3 scripts/project.py start`（`status`、`restart`、`stop` に対応）です。Linux では `./start.sh` も使用できます。

## 使い方

`/anime` で検索先を選ぶか作品名を入力します。画像を `/anime` に添付するか公開画像 URL を渡すと、利用可能な場合に画像検索を行います。`/settings` は設定、`/cancel` は入力の取り消しです。

```text
/anime Frieren
/anime mal:5114
/anime anilist:<id>
/anime shikimori:<id>
/settings
/ping
/cancel
```

## 設定

必須項目は `BOT_TOKEN` です。`MAL_CLIENT_ID` は MyAnimeList の機能を広げ、`ANIDB_CLIENT` は AniDB を有効にします。画像検索はゲスト利用が可能です。プロキシと User-Agent は `.proxies.d/` と `.user-agents.d/` で設定します。

```text
.env.example.d/      -> .env.d/
.proxies.example.d/  -> .proxies.d/
.user-agents.example.d/ -> .user-agents.d/
```

ボットは **Anime Mapping DB** のリリースを検証して `mappings.db` を利用します。対応表の生成は行わず、**Anime Timestamp DB** は必須依存ではありません。

## ドキュメント

- [CONTRIBUTING.md](../CONTRIBUTING.md) · [SECURITY.md](../SECURITY.md) · [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)
- [Application architecture](../docs/app-context.md) · [Localization](../localization/README.md)
- [Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db)

## ライセンスと出典

ソースコードは Apache-2.0 です。外部サービスやデータセットのライセンス、出典表示、API 利用規約は別途適用されます。認証情報はコミットしないでください。 [Apache-2.0](../LICENSE).

[OpenAI Codex](https://github.com/apps/openai-codex) · [Issues](https://github.com/anime-db-project/anime-db-bot/issues)
