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

## 検索と画面操作

`/anime` は作品名またはサービス固有の ID を受け付けます。検索結果をページ送りで確認し、選択した作品の詳細カードを開きます。複数表記のタイトルや別名を検索しますが、ID 指定検索ではタイトル文字列だけを根拠に統合しません。

Telegram に添付した画像や公開画像 URL から逆引き検索できます。対応プロバイダーは一致率、エピソード、時刻を詳細カード表示前に提示します。ゲスト利用と API キーの割当量はソースごとに管理されます。

主要カードには正規化された基本情報を表示します。人物、声優、キャラクター、画像、評価詳細、あらすじ、予告、関連作品、おすすめ、エピソードは必要時に読み込みます。シーズンや特別編はソースが構造を提供するときだけ表示します。

## データソース

アニメのメタデータには MyAnimeList（Jikan は補助）、AniList、Shikimori、Kitsu、AniDB（クライアント登録が必要）、AniSearch を使用します。その他のサービスは特定の機能のみを提供します。

| 主な機能 | データソース |
| --- | --- |
| 検索とメタデータ | [MyAnimeList](https://myanimelist.net/) / [Jikan](https://jikan.moe/), [AniList](https://anilist.co/), [Shikimori](https://shikimori.one/), [Kitsu](https://kitsu.app/), [AniDB](https://anidb.net/), [AniSearch](https://www.anisearch.com/) |
| 追加評価 | [IMDb](https://www.imdb.com/) |
| 画像による作品検索 | [trace.moe](https://trace.moe/), [What Anime Is This](https://whatanimeisthis.com/) |
| エピソード・主題歌・スキップ区間 | [AnimeThemes](https://animethemes.moe/), [AniSkip](https://aniskip.com/), [Anime Skip](https://anime-skip.com/), [Baha Anime Skip](https://github.com/JacobLinCool/baha-anime-skip), [SkipDB](https://github.com/SkipDB-TV/skipdb) |

[Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db) がサービス間 ID の対応を提供します。SkipDB のタイムスタンプ機能は現在無効です。ソース一覧は全作品・全話の収録を保証するものではありません。

## ソース別の対応機能

| ソース | タイトル検索 | 作品情報 | スタッフ | 人物 | エピソード | 関連作品 | おすすめ |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Shikimori | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| MAL / Jikan | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| AniList | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| Kitsu | ✓ | ✓ | — | — | ✓ | ✓ | — |
| AniDB | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| AniSearch | — | ✓ | ✓ | ✓ | ✓ | ✓ | — |

AniSearch は確認された作品に多言語情報や吹替の声優情報を加えますが、通常のタイトル検索には参加しません。AnimeThemes はエピソードの OP/ED 情報を補完します。SkipDB の runtime 利用は現在停止しています。

## 作品 ID と情報統合

一つの外部アニメデータベースを基準にはしません。MAL、AniList、Shikimori、Kitsu、AniDB、AniSearch の ID は、確認済みの対応関係がある場合にのみ結び付けます。同じ数値、似た作品名、同じシリーズという理由だけでは結合しません。

対応関係は競合を検査した直接リンクのみを使用します。統合後も各データの出典を保持し、利用可能な画面では個別ソースを選べます。IMDb の評価にはアニメ固有 ID からの一意な対応が必要で、TVDB/TMDB の橋渡しだけでは使いません。

```text
Telegram /anime → Search → Confirmed IDs → Aggregated metadata
                                  ↑
                       mappings.db (local SQLite)
                                  ↓
               Anime card → lazy source-specific sections
```

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

## 導入と運用

共通ランチャーが仮想環境、検査、バックグラウンド起動と停止を管理します。Linux には tmux を使う `start.sh`、Windows には `start.ps1` と `start.cmd`、macOS には `start.command` があります。

Docker Compose とローカル Jikan は任意の補助機能です。Jikan がなくても公式 MAL API を利用できます。`deploy/systemd/` のユニットは Linux 専用です。

```bash
python3 scripts/project.py doctor
python3 scripts/project.py setup
python3 scripts/project.py check
python3 scripts/project.py start
python3 scripts/project.py status
python3 scripts/project.py restart
python3 scripts/project.py stop
```

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

## Telegram コマンド

一般ユーザーは `/anime` を中心に利用します。管理コマンドは許可された Telegram ID のみ実行でき、ID 対応の変更には確認操作と監査履歴があります。

| コマンド | 用途 |
| --- | --- |
| `/start`, `/ping` | 開始・疎通確認 |
| `/anime`, `/anime <title>`, `/anime mal:<id>` | タイトル、ID、画像による検索 |
| `/settings` | 言語とユーザー設定 |
| `/cancel` | 入力の取り消し |
| `/users`, `/status`, `/source_health` | ユーザー、稼働状態、ソース状態 |
| `/ban <user_id> [seconds] [reason]`, `/unban <user_id>` | ユーザーの禁止と解除 |
| `/mapping_overrides`, `/mapping_history [limit]` | 対応関係の例外と履歴 |
| `/mapping_set`, `/mapping_delete`, `/mapping_confirm`, `/mapping_cancel` | 変更の仮登録、確認、取り消し |

## 設定

必須項目は `BOT_TOKEN` です。`MAL_CLIENT_ID` は MyAnimeList の機能を広げ、`ANIDB_CLIENT` は AniDB を有効にします。画像検索はゲスト利用が可能です。プロキシと User-Agent は `.proxies.d/` と `.user-agents.d/` で設定します。

```text
.env.example.d/      -> .env.d/
.proxies.example.d/  -> .proxies.d/
.user-agents.example.d/ -> .user-agents.d/
```

ボットは **Anime Mapping DB** のリリースを検証して `mappings.db` を利用します。対応表の生成は行わず、**Anime Timestamp DB** は必須依存ではありません。

## 設定項目

テンプレートから `.env.d/` を作り、既存設定を上書きしません。読み込む設定ファイル名は固定です。プロセス環境変数が優先され、プロジェクト設定間の重複キーは起動エラーになります。秘密情報を Git に保存しないでください。

| 変数 | 用途 |
| --- | --- |
| `BOT_TOKEN` | 必須の Telegram ボットトークン |
| `MAL_CLIENT_ID` | MyAnimeList 公式 API のクライアント ID |
| `ANIDB_CLIENT` | 任意の AniDB HTTP API クライアント |
| `ANILIST_ACCESS_TOKEN` | 任意の AniList 認証 |
| `TRACE_MOE_API_KEY` | trace.moe キー（ゲスト可） |
| `WHATANIMEISTHIS_API_KEY` | What Anime Is This キー（ゲスト可） |
| `ADMIN_TELEGRAM_USER_IDS` | 管理を許可する Telegram ID |
| `TELEGRAM_BOT_API_URL` | 独自 Telegram Bot API の URL |
| `MAPPINGS_DB_PATH` | ID 対応 SQLite のパス |
| `IMDB_RATINGS_BACKEND` | IMDb 評価の取得方式 |
| `BAHA_ANIME_SKIP_DB_PATH` | Baha のローカル索引パス |

`.proxies.d/` にソースごとの TOML プロファイルを指定できます。HTTP、SOCKS4、SOCKS5 に対応します。優先度、同順位のローテーション、低順位へのフェイルオーバーがあり、設定したプロキシがすべて失敗しても勝手に直接接続しません。

User-Agent のプロファイルは `.user-agents.d/` で指定します。両プロファイルとも再起動後に反映されます。独自 Telegram Bot API は任意で、外部公開時には適切な保護が必要です。

```toml
enabled = true
[[proxy]]
name = "primary"
enabled = true
priority = 100
url = "socks5://127.0.0.1:1080"
```

利用できる変数とプロファイル名は `.env.example.d/`、`.proxies.example.d/`、`.user-agents.example.d/` にあります。

## ローカルデータと保守

更新機能は `mappings.db.zst` のチェックサムを確認し、監査済みの管理者オーバーライドを保ちながらローカル DB を原子的に置き換えます。通常のボット実行に evidence DB は不要です。

```bash
python3 scripts/project.py mappings --status
python3 scripts/project.py mappings --force
python3 scripts/project.py mappings --override-list
python3 scripts/project.py mappings --override-history
python3 scripts/project.py imdb-index
python3 scripts/project.py baha-index
```

IMDb のローカル索引は確認済みのアニメ ID に結び付く評価のみを保持します。Baha Anime Skip もローカル DB から読み取り、稼働時には Bahamut に問い合わせません。両索引は mapping DB の準備後に個別更新できます。

ユーザー設定、既知ユーザー、制限と一部のクォータは SQLite に保存されます。ログは `logs/YYYY.MM.DD/` に `bot.log`、`users.log`、`api.log`、`errors.log` として記録され、ランチャーは `logs/launcher.log` も使用します。

## エピソード、OP/ED、スキップ区間

エピソード一覧とタイムスタンプは独立した機能です。エピソード一覧のソースを選んでも、タイムスタンプソースの選択は固定されません。各サービスは独自のエピソード識別子を持ち、証明できない対応を作りません。

AnimeThemes は OP/ED の名称、楽曲、歌手、動画リンクをエピソード画面に補完します。スキップソースには OP、ED、回想などの区間がありますが、配信版や話数の違いで時間が一致しないことがあります。一つのソースの区間が全ソースの同意とは限りません。

## 運用と問題解決

見つからない作品では、まず応答したサービスと対応 ID を確認してください。個別 API のタイムアウトや任意キーの欠如は全体検索を止める理由ではありません。`/status` で稼働統計、`/source_health` で障害保護の状態を確認できます。

起動に失敗する場合は `doctor` と `check` を実行し、`logs/YYYY.MM.DD/errors.log` と `BOT_TOKEN` を確認します。`.env.d/` やプロファイル変更後は再起動してください。IMDb/Baha 索引を更新する前に mapping の状態を確認します。

```bash
python3 scripts/project.py doctor
python3 scripts/project.py check
python3 scripts/project.py mappings --status
```

## 構成と障害対策

検索、ID 解決、外部ソース、集約、翻訳、保存、Telegram 表示を分離しています。タイムアウト、再試行、レート制限、サーキットブレーカーによりソースの障害を隔離します。

```text
bots/telegram/    Telegram UI, card and search handlers
core/             contracts, settings, HTTP and logging
search/           search source adapters
services/         identity, aggregation, runtime and media
sources/          API providers and source health
mappings/         local cross-ID resolution and updater
localization/     seven UI locale catalogs
jikan_service/    optional local MAL supplement
deploy/systemd/   optional Linux service/timer units
tests/            automated regression tests
```

## 開発とセキュリティ

作品 ID を慎重に扱い、初期カードへ不要な API 呼び出しを増やさない変更を推奨します。PR の前に対応 Python で検査してください。脆弱性は公開 issue ではなくセキュリティ手順に沿って連絡してください。

```bash
python3 scripts/project.py setup --dev
python3 scripts/project.py check
```

[Contributing](../CONTRIBUTING.md) · [Security](../SECURITY.md) · [Code of Conduct](../CODE_OF_CONDUCT.md)

## ドキュメント

- [CONTRIBUTING.md](../CONTRIBUTING.md) · [SECURITY.md](../SECURITY.md) · [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)
- [Application architecture](../docs/app-context.md) · [Localization](../localization/README.md)
- [Anime Mapping DB](https://github.com/anime-db-project/anime-mapping-db)

## ライセンスと出典

ソースコードは Apache-2.0 です。外部サービスやデータセットのライセンス、出典表示、API 利用規約は別途適用されます。認証情報はコミットしないでください。 [Apache-2.0](../LICENSE).

[OpenAI Codex](https://github.com/apps/openai-codex) · [Issues](https://github.com/anime-db-project/anime-db-bot/issues)
