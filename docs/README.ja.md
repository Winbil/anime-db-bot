> **AI 支援プロジェクト:** このプロジェクトの開発には AI が使用されています。

<p align="center">
  <a href="../README.md">English</a> · <a href="README.ru.md">Русский</a> · <strong>日本語</strong>
</p>

# anime-db-bot

> MyAnimeList/Jikan、AniList、Shikimori、AniDB、AniSearch を横断して検索・統合する、identity-native な Telegram アニメボットです。

[![Python](https://img.shields.io/badge/Python-3.11--3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![CI](https://github.com/Winbil/anime-db-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/Winbil/anime-db-bot/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-D22128.svg)](../LICENSE)

`anime-db-bot` は複数のアニメデータベースを検索し、確認済みの cross-database identity を解決して、特定の外部データベースを唯一の正解とせずに 1 つの統合カードを生成します。

設計上、**search**、**identity**、**mappings**、**metadata sources**、**aggregation**、**localization**、**platform UI** は明確に分離されています。staff/seiyuu は ID・名前・役割だけの軽量 manifest を先に取得して正確な total を確定し、portrait は global batch（既定 50 件）で段階的に enrichment します。

## 主な特徴

- **複数プロバイダー検索** — Shikimori、MyAnimeList、AniList を 1 つの `/anime` フローから検索します。
- **Source-independent identity** — `AnimeIdentity` は外部 ID を対等な関連として保持し、グローバルな primary ID を持ちません。
- **保守的な cross-ID mapping** — runtime mapping は direct-only / conflict-aware で、provenance と監査可能な manual override を保持します。
- **統合 metadata card** — 成功した metadata source の値を正規化・統合しつつ、source provenance を維持します。
- **Manifest + lazy enrichment** — staff/seiyuu の ID・名前・役割を軽量 manifest として prefetch し、portrait は global batch（既定 50 件）で追加します。characters、screenshots、detailed popularity、descriptions/background、trailers、episodes は引き続き lazy です。
- **共通 resilience layer** — typed source errors、retry、circuit breaker、half-open recovery、rate limits、shared HTTP lifecycle。
- **永続化された platform-scoped settings** — user locale、known users、moderation state を SQLite に保存します。
- **3 言語 UI** — English が default/fallback、Russian と Japanese は `/settings` から選択できます。
- **Production-oriented checks** — Python 3.11–3.14、Ruff、formatter、mypy scope、coverage gate、ShellCheck。

## Source capabilities

| Source | Search | Metadata | People | Characters | Trailers | Episodes | Screenshots | Popularity | Description |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Shikimori | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ |
| MAL / Jikan | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| AniList | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | ✓ |
| AniDB | — | ✓ | ✓ | ✓ | — | ✓ | — | — | ✓ |
| AniSearch | — | ✓ | ✓ | ✓ | — | ✓ | — | ✓ | ✓ |
| SkipDB (dormant) | — | — | — | — | — | — | — | — | — |

AniDB は optional で、`ANIDB_CLIENT` が設定されている場合のみ有効になります。Jikan は**独立した identity database ではありません**。公式 MAL API に存在しないデータを補うためのローカル MAL backend です。Main-card licensors と lazy popularity statistics は別々の local endpoint を使うため、score distribution の取得は initial card path から外れています。

AniSearch は、mappings.db の確認済み `anisearch` edge を使う identity-native Database API source です。公開 API には通常のタイトル query-search endpoint がないため、高速 `/anime <title>` 検索には参加しません。AniSearch は ID と `/full` を同じ厳しい rate-limit group に置いているため、title ごとに cached `/full` を 1 回だけ取得し、heavy fields は initial aggregation には混ぜません。people/characters/episodes はその同じ payload を再利用するため、追加の network wait は発生しません。現在取り込む AniSearch のローカライズは英語と日本語だけです。トークンなしの ID-family request は公式仕様どおり 10 秒間隔（有効な token がある場合は 5 秒）で送信し、AniSearch 由来の synopsis には必須の AniSearch 直接リンクを付けます。

SkipDB対応はIMDbベースのdormant providerとしてコードベースに残していますが、現在のアニメ向けskip-segment coverageが小さすぎるためruntimeには登録していません。parser/settings/testsは保持し、coverageが十分に増えた場合に再有効化できる状態を維持します。SkipDBデータはODbL 1.0 + reciprocityです。

## 仕組み

```text
Telegram /anime
      │
      ▼
SearchService
      │
      ▼
SearchCandidate
      │
      ▼
AnimeIdentity  ◄──── disk-backed mappings.db
      │                + live MAL → Shikimori fallback
      ▼
AnimeAggregator
      │
      ├── Shikimori
      ├── AniList
      ├── MAL / Jikan
      └── AniDB (optional)
      │
      ▼
AggregatedAnime
      │
      ▼
Telegram card + lazy sections
```

### Identity rules

`AnimeIdentity` に primary ID はありません。異なるデータベースで数値 ID が同じでも、それだけで同じ作品とは判定しません。

Cross-source merge は保守的なルールで動作します。

1. 共通する明示的な external ID は強い identity evidence として扱います。
2. 同じ provider 内で ID が競合する場合は merge しません。
3. Text search では same-provider conflict がない場合に限り、制限付きの exact normalized romaji fallback を使用できます。
4. Direct-ID lookup では title-only merge を使用しません。
5. Runtime mapping は direct-only で、TVDB/TMDB などを経由する任意の recursive traversal は行いません。

内部では routing と lazy capability のために完全な enriched identity を保持します。一方、カード上の ID ブロックには、そのカードの metadata 取得に実際に成功した source の ID だけを表示します。

## 検索

ユーザー向けの検索コマンドは `/anime` のみです。

```text
/anime Frieren
/anime 37430
/anime mal:37430
/anime anilist:<id>
/anime shikimori:<id>
```

`/anime <title>` は登録済み search provider を並列に問い合わせ、Telegram pagination の前に bounded な query-scoped result set を構築します。Relevance は title、alias、native/romaji、prefix/token match、transliteration、保守的な similarity fallback を考慮します。

Hard cap によって upstream quota を保護します。最終件数を保証できない場合、UI は未確定件数を正直に表示し、確定値として扱いません。

引数なしの `/anime` は対話式 source selector を開きます。Pending input は user/chat の組み合わせにスコープされ、自動で期限切れになり、`/cancel` でキャンセルできます。

## Lazy card sections

メインカードは metadata-first のままです。以下の情報は必要になった時だけ読み込みます。

- staff / creators;
- オリジナルの日本語 voice actors;
- characters / portraits;
- screenshots;
- detailed popularity / ranking statistics;
- descriptions / source background;
- trailers / promos;
- episodes.

海外吹き替えの voice credit はオリジナル日本語 voice list に混在させません。Localization/ADR staff も primary production staff から除外します。

## 必要環境

推奨環境:

- Linux server;
- Python **3.11 / 3.12 / 3.13 / 3.14**;
- Git;
- bundled `start.sh` を使う場合は `tmux`;
- optional local Jikan supplement 用の Docker + Docker Compose。

Docker がなくてもボットは起動できます。その場合、公式 MAL API は利用できますが、Jikan 専用の補助機能は無効になります。

## Quick start

```bash
git clone git@github.com:Winbil/anime-db-bot.git
cd anime-db-bot

cp .env.example .env
# .env を編集し、少なくとも BOT_TOKEN を設定します。

./scripts/setup.sh
./scripts/check.sh
./start.sh
```

`start.sh` は Telegram bot を detached `tmux` session で起動し、Docker Compose が利用可能な場合はローカル Jikan container も起動します。

```bash
tmux attach -t anime-db-bot
TODAY="$(date '+%Y.%m.%d')"
tail -f "logs/$TODAY/bot.log"
tail -f "logs/$TODAY/users.log"
tail -f "logs/$TODAY/api.log"
```

Runtime log は `logs/YYYY.MM.DD/` 配下で用途別に分割されます。`bot.log` は application/runtime、`users.log` は Telegram user action、`api.log` は outbound source/API/retry/health event、`errors.log` はすべての `ERROR+` record の追加コピーです。runtime の local midnight を越えると、bot を再起動せず次の record から新しい日付ディレクトリへ自動的に切り替わります。

## 設定

Runtime environment parsing は `core/settings.py` に集約されています。`.env.example` にすべての設定項目と安全な default が記載されています。

### 主な環境変数

| Variable | 必須 | 用途 |
| --- | :---: | --- |
| `BOT_TOKEN` | はい | BotFather から取得した Telegram bot token。 |
| `MAL_CLIENT_ID` | 推奨 | 公式 MyAnimeList search / metadata を有効化。 |
| `ANIDB_CLIENT` | いいえ | AniDB HTTP API metadata/people/episodes を有効化。 |
| `ANIDB_CLIENT_VERSION` | いいえ | 登録済み AniDB HTTP client version。default は `1`。 |
| `ANILIST_ACCESS_TOKEN` | いいえ | Authenticated access が必要な場合の optional AniList token。 |
| `ADMIN_TELEGRAM_USER_IDS` | いいえ | Telegram 管理者 user ID の一覧。 |
| `TELEGRAM_BOT_API_URL` | いいえ | Custom/self-hosted Telegram Bot API endpoint。 |
| `USER_SETTINGS_DB_PATH` | いいえ | User settings / known-user registry 用 SQLite path。 |
| `BANS_DB_PATH` | いいえ | Moderation ban 用 SQLite path。 |
| `MAPPINGS_DB_PATH` | いいえ | Runtime cross-ID mapping database。 |

`.env`、bot token、access token、password、private credentials は commit しないでください。

### AniDB

この integration は AniDB HTTP API を使用します。必要なのは登録済みの **client name と version** であり、AniDB account password ではありません。

```env
ANIDB_CLIENT=your_registered_client_name
ANIDB_CLIENT_VERSION=1
```

AniDB XML response は disk cache に保存されます。Network request は直列化され、API への負荷を抑えるため追加の最小 request interval も適用されます。

### MAL / Jikan

MAL が identity source です。Jikan はローカル supplemental backend であり、`jikan` identity key は作成しません。

```text
compose.yml
jikan_service/
scripts/update-jikan.sh
deploy/systemd/anime-db-bot-jikan-update.{service,timer}
```

Jikan が停止しても公式 MAL search / metadata は利用できます。

## コマンド

### User commands

```text
/start
/ping
/settings
/anime
/anime <title>
/anime <external_id>
/anime mal:<id>
/anime anilist:<id>
/anime shikimori:<id>
/cancel
```

### Admin commands

```text
/users
/source_health
/ban <user_id> [seconds] [reason]
/unban <user_id>
/mapping_overrides
/mapping_history [limit]
/mapping_set <accept|reject> <source_provider> <source_id> <target_provider> <target_id> <reason>
/mapping_delete <source_provider> <source_id> <target_provider> <target_id> <reason>
/mapping_confirm <token>
/mapping_cancel <token>
```

Mapping mutation は 2 段階です。`/mapping_set` と `/mapping_delete` は短時間だけ有効な pending mutation を作り、`/mapping_confirm <token>` の後で初めて database を変更します。Audit history には変更を実行した Telegram administrator が記録されます。

## Localization

Domain model は locale-neutral です。Source adapter は upstream の status/type/season/genre/role を canonical key に正規化し、翻訳は render 時だけ行います。

対応 UI locale:

- `en` — English (**default / fallback**);
- `ru` — Русский;
- `ja` — 日本語.

既存ユーザーの明示的に保存された locale は維持されます。新規ユーザー、設定がない場合、未知の locale、欠落 translation key は English に fallback します。

Anime description など source が返す free-form text は machine translation しません。詳細は [`localization/README.md`](../localization/README.md) を参照してください。

## Persistence

State は用途ごとに分離されています。

- user settings / known users — `(platform, user_id)` scoped SQLite;
- bans — 独立した persistent SQLite store;
- `mappings.db` — disk-backed cross-ID resolver;
- AniDB XML — disk cache;
- Telegram search/card callback sessions — bounded in-memory TTL/LRU state。

Platform scoping 導入前の legacy user settings は、保存済み locale を変更せず Telegram record として migration されます。

## Resilience / rate limiting

Outbound HTTP は `AppContext` が所有する shared `httpx.AsyncClient` を使用します。Source failure は typed error に正規化され、共通 retry / circuit-breaker layer を通ります。

Transient/non-transient handling、bounded retry、cooldown、circuit breaker、1 つだけ許可される half-open recovery probe をサポートします。

Personal Telegram limit は `(platform, user_id)` ごとに独立しています。Admin は personal limiter を bypass できますが、**upstream provider safety limit は決して bypass しません**。

## アーキテクチャ

```text
anime-db-bot/
├── bots/telegram/
│   ├── card/            # card runtime, feature handlers, UI primitives, views
│   │   ├── features/    # characters, descriptions, episodes, popularity, screenshots, trailers
│   │   ├── runtime/     # handlers, session state, card service wiring
│   │   ├── ui/          # keyboards, selectors, constants
│   │   └── views/       # renderers and section presentation
│   ├── people/          # lazy people loading, portraits, views
│   ├── search/          # Telegram search handlers/UI
│   └── transports/      # official / self-hosted Bot API transports
├── core/                # contracts, models, identity, settings, HTTP, errors
├── localization/        # locale catalogs and canonical localization data
├── mappings/            # cross-ID database, importers, resolver, updater
├── search/              # provider-facing search adapters and registry
├── services/
│   ├── aggregation/     # metadata aggregation and merge policy
│   ├── identity/        # direct lookup and cross-source identity resolution
│   ├── media/           # characters, episodes, people, trailers
│   ├── runtime/         # AppContext, source health, rate-limit runtime policy
│   ├── search/          # search orchestration and query expansion
│   └── users/           # access control, bans, persistent user settings
├── sources/
│   ├── providers/       # MAL, AniList, Shikimori, AniDB, AniSearch, Jikan adapters
│   └── runtime/         # source catalog, registries, resilience wrappers
├── tests/               # unit, integration, wiring, regression tests
├── jikan_service/       # local Jikan/MAL supplement service
├── scripts/             # setup, checks, maintenance helpers
└── deploy/systemd/      # optional maintenance units
```

`services/runtime/app_context.py` は application composition root です。Production runtime dependency は import-time singleton として作るのではなく、ここで lifecycle ownership を管理します。

詳細: [`docs/app-context.md`](app-context.md)

## Cross-ID mappings

Mapping updater は複数の外部 dataset を SQLite にストリームし、provenance/evidence/conflict を保存して rebuilt database を検証し、atomic swap します。完全な graph を RAM にロードしません。

Manual directional override は `accept` / `reject`、author/reason/timestamp、append-only history をサポートします。

```bash
./scripts/update-mappings.sh
.venv/bin/python -m mappings --status
.venv/bin/python -m mappings --override-list
.venv/bin/python -m mappings --override-history
```

## 開発

```bash
./scripts/setup.sh
./scripts/check.sh
```

追加のチェック:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q bots core localization mappings search services sources tests
.venv/bin/python -m pip check
```

GitHub Actions では Python 3.11 / 3.12 / 3.13 / 3.14 の成功を必須とします。Quality job では Ruff、typed foundation formatter check、mypy、full test suite + coverage gate `>=70%`、ShellCheck も実行します。

## Contributing

Pull request を歓迎します。変更を送る前に [CONTRIBUTING.md](../CONTRIBUTING.md) を読み、[Code of Conduct](../CODE_OF_CONDUCT.md) に従ってください。Bug report と feature request には repository の issue form を使用してください。

## Security

- `.env` と credentials は version control に含めないでください。
- Log は日付別の `bot/users/api/errors` file に分割され、既定で secret redaction、update ごとの correlation ID、runtime の local timezone timestamp、各 file の bounded rotation を使用します。`LOG_REDACT_SECRETS=0` は local diagnostics 用に masking を完全に無効化し credentials をそのまま記録する可能性があるため、shared/public logs では有効のままにしてください。
- Admin-only action は access-control layer の内側に置いてください。
- Self-hosted Telegram Bot API、将来の metrics endpoint、将来の external API を公開する場合は explicit authentication/network controls が必要です。
- Mapping override は identity edge を変更するため audit 対象です。

脆弱性の報告方法は [SECURITY.md](../SECURITY.md) を参照してください。Credential、token、private deployment detail を public issue に投稿しないでください。

## Project status

プロジェクトは active development 中です。Telegram search/card flow、identity model、mapping database、multi-source aggregation、localization、lazy capabilities、persistence、resilience、CI foundation は実装済みです。Structured discovery/search filters、user account integration、notifications、monitoring/Prometheus metrics、external API/Mini App、追加 source は今後の予定です。

## License

このプロジェクトは [Apache License 2.0](../LICENSE) の下で提供されます。ライセンス条件に従って利用・変更・再配布でき、必要な notice の保持と重要な変更の明示が求められます。

## Data sources / acknowledgements

`anime-db-bot` は以下のサービス・データを利用または統合します。

- [MyAnimeList](https://myanimelist.net/)
- [Jikan](https://jikan.moe/)
- [AniList](https://anilist.co/)
- [Shikimori](https://shikimori.one/)
- [AniDB](https://anidb.net/)
- [AniSearch](https://www.anisearch.com/) — Database API metadata; attribution and synopsis-link requirements apply
- [SkipDB](https://skipdb.tv/) — skip-segment data under ODbL 1.0 + reciprocity

Cross-ID mapping は複数の community dataset から構築されます。各 upstream service / dataset には、それぞれ独自の terms、rate limit、attribution requirement が適用されます。

AniSearch Database API の読み取り専用メタデータ取得には OAuth は不要です。`ANISEARCH_APP_ID` と `ANISEARCH_APP_SECRET` は将来のユーザー認可機能向けの任意の OAuth アプリ資格情報であり、読み取り専用 API リクエストには送信されません。
