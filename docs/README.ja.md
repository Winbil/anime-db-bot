> **AI 支援プロジェクト:** このプロジェクトの開発には AI が使用されています。

<p align="center">
  <a href="../README.md">English</a> · <a href="README.ru.md">Русский</a> · <strong>日本語</strong> · <a href="README.de.md">Deutsch</a> · <a href="README.es.md">Español</a> · <a href="README.fr.md">Français</a> · <a href="README.it.md">Italiano</a>
</p>

# anime-db-bot

> MyAnimeList/Jikan、AniList、Shikimori、Kitsu、AniDB、AniSearch を横断して検索・統合する、identity-native な Telegram アニメボットです。

[![Python](https://img.shields.io/badge/Python-3.11--3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![CI](https://github.com/Winbil/anime-db-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/Winbil/anime-db-bot/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-D22128.svg)](../LICENSE)

`anime-db-bot` は複数のアニメデータベースを検索し、確認済みの cross-database identity を解決して、特定の外部データベースを唯一の正解とせずに 1 つの統合カードを生成します。

設計上、**search**、**identity**、**mappings**、**metadata sources**、**aggregation**、**localization**、**platform UI** は明確に分離されています。staff/seiyuu は ID・名前・役割だけの軽量 manifest を先に取得して正確な total を確定し、portrait は global batch（既定 50 件）で段階的に enrichment します。

## 主な特徴

- **複数プロバイダー検索** — Shikimori、MyAnimeList、AniList、Kitsu を 1 つの `/anime` フローから検索します。
- **Source-independent identity** — `AnimeIdentity` は外部 ID を対等な関連として保持し、グローバルな primary ID を持ちません。
- **保守的な cross-ID mapping** — runtime mapping は direct-only / conflict-aware で、provenance と監査可能な manual override を保持します。
- **統合 metadata card** — 成功した metadata source の値を正規化・統合しつつ、source provenance を維持します。
- **Manifest + lazy enrichment** — staff/seiyuu の ID・名前・役割を軽量 manifest として prefetch し、portrait は global batch（既定 50 件）で追加します。characters、screenshots、detailed popularity、descriptions/background、trailers、episodes は引き続き lazy です。
- **共通 resilience layer** — typed source errors、retry、circuit breaker、half-open recovery、rate limits、shared HTTP lifecycle。
- **永続化された platform-scoped settings** — user locale、known users、moderation state を SQLite に保存します。
- **7 言語 UI** — English が default/fallback で、Russian、Japanese、German、Spanish、French、Italian を `/settings` から選択できます。
- **Production-oriented checks** — Python 3.11–3.14、Ruff、formatter、mypy scope、coverage gate、ShellCheck。

## Source capabilities

| Source | Search | Metadata | People | Characters | Trailers | Episodes | Screenshots | Popularity | Description |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Shikimori | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ |
| MAL / Jikan | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| AniList | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | ✓ |
| Kitsu | ✓ | ✓ | — | — | ✓ | ✓ | — | ✓ | ✓ |
| AniDB | — | ✓ | ✓ | ✓ | — | ✓ | — | — | ✓ |
| AniSearch | — | ✓ | ✓ | ✓ | — | ✓ | — | ✓ | ✓ |
| SkipDB (dormant) | — | — | — | — | — | — | — | — | — |

Kitsu は identity-native な public JSON:API source です。通常の read-only GET request は OAuth credentials を必要としません。確認済み Kitsu ID は既存の `mappings.db` に参加し、Kitsu 自身も MAL/AniList/AniDB への direct mapping を返します。現在は search、metadata、popularity、description、episodes、利用可能な場合の YouTube trailer を提供します。people/characters relationship は疎なことが多いため、現時点では capability として公開していません。

AniDB は optional で、`ANIDB_CLIENT` が設定されている場合のみ有効になります。Jikan は**独立した identity database ではありません**。公式 MAL API に存在しないデータを補うためのローカル MAL backend です。Main-card licensors と lazy popularity statistics は別々の local endpoint を使うため、score distribution の取得は initial card path から外れています。

AniSearch は、mappings.db の確認済み `anisearch` edge を使う identity-native Database API source です。公開 API には通常のタイトル query-search endpoint がないため、高速 `/anime <title>` 検索には参加しません。AniSearch は ID と `/full` を同じ厳しい rate-limit group に置いているため、title ごとに cached `/full` を 1 回だけ取得し、heavy fields は initial aggregation には混ぜません。people/characters/episodes はその同じ payload を再利用するため、追加の network wait は発生しません。AniSearch の英語、日本語、ドイツ語、スペイン語、フランス語、イタリア語ローカライズを取り込み、ローカライズされた title/synonym、synopsis、episode title、regional licensor、voice credit に使用します。トークンなしの ID-family request は公式仕様どおり 10 秒間隔（有効な token がある場合は 5 秒）で送信し、AniSearch 由来の synopsis には必須の AniSearch 直接リンクを付けます。

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
      ├── Kitsu
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
/anime kitsu:<id>
```

`/anime <title>` は登録済み search provider を並列に問い合わせ、Telegram pagination の前に bounded な query-scoped result set を構築します。Relevance は title、alias、native/romaji、prefix/token match、transliteration、保守的な similarity fallback を考慮します。

Hard cap によって upstream quota を保護します。最終件数を保証できない場合、UI は未確定件数を正直に表示し、確定値として扱いません。

引数なしの `/anime` は対話式 source selector を開きます。Pending input は user/chat の組み合わせにスコープされ、自動で期限切れになり、`/cancel` でキャンセルできます。

`/anime` は画像による逆引き検索にも対応します。コマンドに画像を添付するか公開画像 URL を渡すと、現在クォータが残っている trace.moe、What Anime Is This、または両方だけが選択肢に表示されます。同一結果は確認済み AniList ID でのみ統合し、通常検索と同じ候補ページを表示します。完全なメタデータカードは **詳細** を選んだ後にだけ開きます。候補には検索元、類似度、話数、タイムスタンプを表示し、**探している作品ではありませんか？** から再検索またはキャンセルできます。アップロード画像は外部検索前に JPEG へ正規化されます。

## Lazy card sections

メインカードは metadata-first のままです。以下の情報は必要になった時だけ読み込みます。

- staff / creators;
- voice actors（言語タグ付き AniSearch dub credit を含む）;
- characters / portraits;
- screenshots;
- detailed popularity / ranking statistics;
- descriptions / source background;
- trailers / promos;
- episodes.

日本語 voice credit は言語 suffix のない original-language baseline のままです。AniSearch の吹き替え credit には `[EN]`、`[DE]`、`[ES]`、`[FR]`、`[IT]` の suffix を付け、オリジナル日本語 credit と区別します。Localization/ADR staff も primary production staff から除外します。

## 必要環境 / OS サポート

Python runtime は **Linux、macOS、native Windows** を対象とし、Python **3.11 / 3.12 / 3.13 / 3.14** をサポートします。GitHub Actions では、対応する全 Python version について 3 OS family すべてで full unit suite を実行します。

- **Linux** — primary production platform。対応 CPython があれば主要 distribution で cross-platform launcher を利用できます。既存の `start.sh` は Linux 向け `tmux` production helper として残します。
- **macOS** — Python launcher をサポートし、便利な wrapper として `start.command` を用意します。`systemd` unit は macOS では使用しません。
- **Windows native** — Python launcher、`start.ps1`、`start.cmd` をサポートし、WSL は必須ではありません。
- **Docker + Docker Compose** — 全 OS で optional。local Jikan supplement にのみ使用します。Docker がなくても公式 MAL は利用でき、Jikan-only 機能だけが無効になります。
- **systemd** — `deploy/systemd/` にある optional Linux-only integration です。

環境の基本互換性は、使用中の Python で `python scripts/project.py doctor` を実行して確認できます。

## Quick start

まず repository を clone します。

```text
git clone git@github.com:Winbil/anime-db-bot.git
cd anime-db-bot
```

Canonical launcher は `scripts/project.py` です。`.venv` の作成、locked dependency の install、既存値を上書きしない example config の初期化を行い、Unix の `bin/python` と Windows の `Scripts/python.exe` を自動で使い分けます。

Linux / macOS:

```bash
python3 scripts/project.py setup
# .env.d/telegram.env に少なくとも BOT_TOKEN を設定します。
python3 scripts/project.py check
python3 scripts/project.py run       # foreground
python3 scripts/project.py start     # background + PID file
```

Windows PowerShell / Command Prompt:

```powershell
py -3 scripts\project.py setup
# .env.d\telegram.env に少なくとも BOT_TOKEN を設定します。
py -3 scripts\project.py check
py -3 scripts\project.py run
.\start.ps1                         # background
```

Command Prompt では `start.cmd`、macOS では `./start.command` も利用できます。Cross-platform launcher で起動した background process は次で管理します。

```text
python scripts/project.py status
python scripts/project.py stop
python scripts/project.py restart
```

Linux production は従来どおり `./start.sh` を使用でき、detached `tmux` workflow を維持します。通常の runtime log は `logs/YYYY.MM.DD/`、generic background launcher の stdout/stderr は `logs/launcher.log` に出力されます。

Runtime log は `logs/YYYY.MM.DD/` 配下で用途別に分割されます。`bot.log` は application/runtime、`users.log` は Telegram user action、`api.log` は outbound source/API/retry/health event、`errors.log` はすべての `ERROR+` record の追加コピーです。runtime の local midnight を越えると、bot を再起動せず次の record から新しい日付ディレクトリへ自動的に切り替わります。

## 設定

Runtime environment parsing は `core/settings.py` に集約されています。新規環境では `.env.example.d/` を `.env.d/` にコピーします。読み込むのは固定された `telegram.env`、`sources.env`、`timestamps.env`、`rate-limits.env`、`mappings.env`、`storage.env`、`logging.env`、`runtime.env` だけで、`backup.env` のような追加ファイルは無視されます。project config file 間の重複 key は起動エラーになり、実際の process environment variable が最優先です。単一の `.env` は移行互換性のためだけに残されています。

### 主な環境変数

| Variable | 必須 | 用途 |
| --- | :---: | --- |
| `BOT_TOKEN` | はい | BotFather から取得した Telegram bot token。 |
| `MAL_CLIENT_ID` | 推奨 | 公式 MyAnimeList search / metadata を有効化。 |
| `ANIDB_CLIENT` | いいえ | AniDB HTTP API metadata/people/episodes を有効化。 |
| `ANIDB_CLIENT_VERSION` | いいえ | 登録済み AniDB HTTP client version。default は `1`。 |
| `ANILIST_ACCESS_TOKEN` | いいえ | Authenticated access が必要な場合の optional AniList token。 |
| `KITSU_API_URL` | いいえ | Kitsu public JSON:API の base URL。default は `https://kitsu.io/api/edge`。 |
| `ADMIN_TELEGRAM_USER_IDS` | いいえ | Telegram 管理者 user ID の一覧。 |
| `TELEGRAM_BOT_API_URL` | いいえ | Custom/self-hosted Telegram Bot API endpoint。 |
| `TELEGRAM_BOT_API_LOCAL_FILE_ROOT` | いいえ | Local Bot API コンテナ内の `/var/lib/telegram-bot-api` に対応する host directory。local `file_path` を読む場合に使用します。 |
| `USER_SETTINGS_DB_PATH` | いいえ | User settings / known-user registry 用 SQLite path。 |
| `BANS_DB_PATH` | いいえ | Moderation ban 用 SQLite path。 |
| `MAPPINGS_DB_PATH` | いいえ | Runtime cross-ID mapping database。 |

`.env`、`.env.d/`、`.proxies.d/`、bot token、access token、password、proxy credentials、private credentials は commit しないでください。

### Source ごとの proxy pool

Outbound proxy は `.proxies.d/` で runtime source ごとに独立して設定できます。各 source には固定 TOML file があり、`telegram.toml` は Telegram bot 自体に適用されます。Template は `.proxies.example.d/` にあります。対応 scheme は `http`, `socks4`, `socks5` です。

```toml
enabled = true

[[proxy]]
name = "primary"
enabled = true
priority = 100
url = "socks5://user:password@127.0.0.1:1080"

[[proxy]]
name = "backup"
enabled = false
priority = 10
url = "http://127.0.0.1:8080"
```

Profile は独立しています。`mal.toml` は MAL のみ、`anilist.toml` は AniList のみに作用します。複数の有効 entry は round-robin で選ばれ、network/proxy failure の場合は残りの有効 proxy を順に試します。同じ URL を異なる `name` で複数登録できるため、同一 endpoint を繰り返して rotation の weight を増やすこともできます。Profile または個別 entry を `enabled = false` で無効化できます。有効 proxy が1つ以上ある profile は、すべて失敗しても **direct connection へ暗黙 fallback しません**。Active proxy がない場合のみ direct access になります。変更は bot restart 後に反映されます。`telegram.toml` に active proxy がある場合、この bot は設定済みの local/shared `telegram-bot-api` を意図的に bypass し、独自 proxy pool 経由で official `api.telegram.org` に接続します。これにより同じ local server を使う他の bot には影響しません。`jikan.toml` も特別扱いで、Python → local Jikan の loopback hop は direct のまま、選択された proxy を Jikan に渡して outbound MyAnimeList scrape に適用します。

固定 profile は `telegram`, `shikimori`, `mal`, `anilist`, `kitsu`, `anidb`, `anisearch`, `jikan`, `aniskip`, `anime_skip`, `bahamut`, `baha_anime_skip`, `skipdb`, `trace_moe`, `whatanimeisthis` です。その他の TOML file は無視されます。`.proxies.d/` は credential を含み得るため gitignored で、`start.sh` は directory を mode `700`、既知 file を `600` に保ちます。

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
/anime kitsu:<id>
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
- `ja` — 日本語;
- `de` — Deutsch;
- `es` — Español;
- `fr` — Français;
- `it` — Italiano.

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
│   ├── providers/       # MAL, AniList, Shikimori, Kitsu, AniDB, AniSearch, Jikan adapters
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

Cross-platform mapping maintenance commands:

```text
python scripts/project.py mappings --status
python scripts/project.py mappings --override-list
python scripts/project.py mappings --override-history
```

既存 deployment 向けの Unix wrapper `./scripts/update-mappings.sh` も残します。

## 開発

全対応 OS で同じ launcher を使用します。

```text
python scripts/project.py setup --dev
python scripts/project.py check
python scripts/project.py doctor
```

Windows では `python` の代わりに `py -3` も利用できます。Unix の `./scripts/setup.sh` と `./scripts/check.sh` は同じ Python implementation を呼ぶ convenience wrapper です。venv の Python は Unix では `.venv/bin/python`、Windows では `.venv\Scripts\python.exe` です。

GitHub Actions では **Ubuntu、macOS、Windows** の各 OS で Python 3.11 / 3.12 / 3.13 / 3.14 の full unit suite 成功を必須とします。各 matrix job は cross-platform launcher doctor も実行します。Linux quality job では Ruff、typed foundation formatter check、mypy、full test suite + coverage gate `>=70%`、Unix wrapper 向け ShellCheck も実行します。

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
- [Kitsu](https://kitsu.app/) — public read-only JSON:API。通常の GET request に OAuth は不要
- [Shikimori](https://shikimori.one/)
- [AniDB](https://anidb.net/)
- [AniSearch](https://www.anisearch.com/) — Database API metadata; attribution and synopsis-link requirements apply
- [SkipDB](https://skipdb.tv/) — skip-segment data under ODbL 1.0 + reciprocity

Cross-ID mapping は複数の community dataset から構築されます。各 upstream service / dataset には、それぞれ独自の terms、rate limit、attribution requirement が適用されます。

Kitsu の public read-only GET request は OAuth credentials なしで利用します。runtime 側では conservative な request limit を適用し、未文書化の server-side rate limit を前提にしません。

AniSearch Database API の読み取り専用メタデータ取得には OAuth は不要です。`ANISEARCH_APP_ID` と `ANISEARCH_APP_SECRET` は将来のユーザー認可機能向けの任意の OAuth アプリ資格情報であり、読み取り専用 API リクエストには送信されません。
