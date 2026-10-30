<?php

declare(strict_types=1);

require dirname(__DIR__) . '/vendor/autoload.php';

use Composer\InstalledVersions;
use Jikan\MyAnimeList\MalClient;
use Jikan\Request\Anime\AnimeCharactersAndStaffRequest;
use Jikan\Request\Anime\AnimeEpisodeRequest;
use Jikan\Request\Anime\AnimeEpisodesRequest;
use Jikan\Request\Anime\AnimeRequest;
use Jikan\Request\Anime\AnimeStatsRequest;
use Jikan\Request\Anime\AnimeVideosRequest;
use Symfony\Component\HttpClient\CurlHttpClient;

const ACTIVE_LOCK = '/tmp/anime-db-bot-jikan-active.lock';

function respond(array $payload, int $status = 200): never
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
    exit;
}

function jikanVersion(): string
{
    return InstalledVersions::getPrettyVersion('jikan-me/jikan') ?? 'unknown';
}

function isoDate(?DateTimeImmutable $value): ?string
{
    return $value?->format(DATE_ATOM);
}

function withActivity(callable $callback): mixed
{
    file_put_contents(ACTIVE_LOCK, (string) getmypid(), LOCK_EX);
    try {
        return $callback();
    } finally {
        @unlink(ACTIVE_LOCK);
    }
}

function upstreamProxyUrl(): ?string
{
    $encoded = trim((string) ($_SERVER['HTTP_X_ANIME_DB_BOT_PROXY'] ?? ''));
    if ($encoded === '') {
        return null;
    }
    $padding = strlen($encoded) % 4;
    if ($padding !== 0) {
        $encoded .= str_repeat('=', 4 - $padding);
    }
    $decoded = base64_decode(strtr($encoded, '-_', '+/'), true);
    if ($decoded === false || $decoded === '') {
        throw new InvalidArgumentException('Invalid upstream proxy header encoding.');
    }
    $parts = parse_url($decoded);
    $scheme = strtolower((string) ($parts['scheme'] ?? ''));
    $host = (string) ($parts['host'] ?? '');
    $port = (int) ($parts['port'] ?? 0);
    if (!in_array($scheme, ['http', 'socks4', 'socks5'], true) || $host === '' || $port <= 0) {
        throw new InvalidArgumentException('Invalid upstream proxy URL.');
    }
    return $decoded;
}

function upstreamUserAgent(): ?string
{
    $encoded = trim((string) ($_SERVER['HTTP_X_ANIME_DB_BOT_USER_AGENT'] ?? ''));
    if ($encoded === '') {
        return null;
    }
    $padding = strlen($encoded) % 4;
    if ($padding !== 0) {
        $encoded .= str_repeat('=', 4 - $padding);
    }
    $decoded = base64_decode(strtr($encoded, '-_', '+/'), true);
    if ($decoded === false || $decoded === '' || str_contains($decoded, "\r") || str_contains($decoded, "\n")) {
        throw new InvalidArgumentException('Invalid upstream User-Agent header encoding.');
    }
    return $decoded;
}

function malClient(): MalClient
{
    $proxy = upstreamProxyUrl();
    $userAgent = upstreamUserAgent();
    if ($proxy === null && $userAgent === null) {
        return new MalClient();
    }
    $options = [];
    if ($proxy !== null) {
        $options['proxy'] = $proxy;
    }
    if ($userAgent !== null) {
        $options['headers'] = ['User-Agent: '.$userAgent];
    }
    return new MalClient(new CurlHttpClient($options));
}

function episodeListItemToArray(object $item): array
{
    return [
        'number' => $item->getMalId(),
        'title' => $item->getTitle(),
        'title_japanese' => $item->getTitleJapanese(),
        'title_romaji' => $item->getTitleRomanji(),
        'aired_at' => isoDate($item->getAired()),
        'score' => $item->getScore(),
        'filler' => $item->isFiller(),
        'recap' => $item->isRecap(),
        'url' => $item->getUrl(),
        'forum_url' => $item->getForumUrl(),
    ];
}

function episodeDetailToArray(object $item): array
{
    return [
        'number' => $item->getMalId(),
        'title' => $item->getTitle(),
        'title_japanese' => $item->getTitleJapanese(),
        'title_romaji' => $item->getTitleRomanji(),
        'aired_at' => isoDate($item->getAired()),
        'duration_seconds' => $item->getDuration(),
        'filler' => $item->isFiller(),
        'recap' => $item->isRecap(),
        'synopsis' => $item->getSynopsis(),
        'url' => $item->getUrl(),
    ];
}

function personMetaToArray(object $person): array
{
    return [
        'mal_id' => $person->getMalId(),
        'name' => $person->getName(),
        'url' => $person->getUrl(),
        'image_url' => $person->getImages()->getJpg()->getImageUrl(),
    ];
}

function peopleToArray(object $result): array
{
    $staff = [];
    foreach ($result->getStaff() as $item) {
        $staff[] = [
            'person' => personMetaToArray($item->getPerson()),
            'roles' => array_values($item->getPositions()),
        ];
    }

    $characters = [];
    $voices = [];
    foreach ($result->getCharacters() as $characterItem) {
        $character = $characterItem->getCharacter();
        $characters[] = [
            'character' => [
                'mal_id' => $character->getMalId(),
                'name' => $character->getName(),
                'url' => $character->getUrl(),
                'image_url' => $character->getImages()->getJpg()->getImageUrl(),
            ],
            'role' => $characterItem->getRole(),
            'favorites' => $characterItem->getFavorites(),
        ];
        foreach ($characterItem->getVoiceActors() as $voiceActor) {
            if (strcasecmp($voiceActor->getLanguage(), 'Japanese') !== 0) {
                continue;
            }
            $voices[] = [
                'person' => personMetaToArray($voiceActor->getPerson()),
                'character' => $character->getName(),
            ];
        }
    }

    return ['staff' => $staff, 'voices' => $voices, 'characters' => $characters];
}

function promoToArray(object $item): array
{
    $trailer = $item->getTrailer();
    $images = $trailer->getImages();
    return [
        'title' => $item->getTitle(),
        'youtube_id' => $trailer->getYoutubeId(),
        'url' => $trailer->getUrl(),
        'embed_url' => $trailer->getEmbedUrl(),
        'thumbnail' => $images->getMaximumImageUrl()
            ?? $images->getLargeImageUrl()
            ?? $images->getMediumImageUrl()
            ?? $images->getImageUrl(),
    ];
}

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';

if ($method !== 'GET') {
    respond(['error' => 'method_not_allowed'], 405);
}

if ($path === '/health') {
    respond([
        'ok' => true,
        'service' => 'anime-db-bot-Jikan',
        'jikan_version' => jikanVersion(),
    ]);
}

if ($path === '/version') {
    respond(['jikan_version' => jikanVersion()]);
}

if ($path === '/activity') {
    respond(['active' => file_exists(ACTIVE_LOCK)]);
}

if (preg_match('#^/anime/(\d+)/licensors$#', $path, $match)) {
    $malId = (int) $match[1];
    try {
        $anime = withActivity(function () use ($malId) {
            $client = malClient();
            return $client->getAnime(new AnimeRequest($malId));
        });

        $licensors = [];
        foreach ($anime->getLicensors() as $licensor) {
            $name = trim($licensor->getName());
            if ($name !== '') {
                $licensors[] = $name;
            }
        }

        respond([
            'source' => 'mal',
            'backend' => 'jikan',
            'data' => [
                'licensors' => array_values(array_unique($licensors)),
            ],
        ]);
    } catch (Throwable $error) {
        respond([
            'error' => 'jikan_request_failed',
            'type' => $error::class,
            'message' => $error->getMessage(),
        ], 502);
    }
}

if (preg_match('#^/anime/(\d+)/popularity$#', $path, $match)) {
    $malId = (int) $match[1];
    try {
        $stats = withActivity(function () use ($malId) {
            $client = malClient();
            return $client->getAnimeStats(new AnimeStatsRequest($malId));
        });

        $scoreDistribution = [];
        foreach ($stats->getScores() as $score) {
            $scoreDistribution[(string) $score->getScore()] = $score->getVotes();
        }

        respond([
            'source' => 'mal',
            'backend' => 'jikan',
            'data' => [
                'score_distribution' => $scoreDistribution,
            ],
        ]);
    } catch (Throwable $error) {
        respond([
            'error' => 'jikan_request_failed',
            'type' => $error::class,
            'message' => $error->getMessage(),
        ], 502);
    }
}

if (preg_match('#^/anime/(\d+)/supplement$#', $path, $match)) {
    $malId = (int) $match[1];
    try {
        [$anime, $stats] = withActivity(function () use ($malId) {
            $client = malClient();
            return [
                $client->getAnime(new AnimeRequest($malId)),
                $client->getAnimeStats(new AnimeStatsRequest($malId)),
            ];
        });

        $licensors = [];
        foreach ($anime->getLicensors() as $licensor) {
            $name = trim($licensor->getName());
            if ($name !== '') {
                $licensors[] = $name;
            }
        }

        $scoreDistribution = [];
        foreach ($stats->getScores() as $score) {
            $scoreDistribution[(string) $score->getScore()] = $score->getVotes();
        }

        respond([
            'source' => 'mal',
            'backend' => 'jikan',
            'data' => [
                'licensors' => array_values(array_unique($licensors)),
                'score_distribution' => $scoreDistribution,
            ],
        ]);
    } catch (Throwable $error) {
        respond([
            'error' => 'jikan_request_failed',
            'type' => $error::class,
            'message' => $error->getMessage(),
        ], 502);
    }
}

if (preg_match('#^/anime/(\d+)/people$#', $path, $match)) {
    $malId = (int) $match[1];
    try {
        $result = withActivity(function () use ($malId) {
            $client = malClient();
            return $client->getAnimeCharactersAndStaff(new AnimeCharactersAndStaffRequest($malId));
        });
        respond([
            'source' => 'mal',
            'backend' => 'jikan',
            'data' => peopleToArray($result),
        ]);
    } catch (Throwable $error) {
        respond([
            'error' => 'jikan_request_failed',
            'type' => $error::class,
            'message' => $error->getMessage(),
        ], 502);
    }
}

if (preg_match('#^/anime/(\d+)/trailers$#', $path, $match)) {
    $malId = (int) $match[1];
    try {
        $result = withActivity(function () use ($malId) {
            $client = malClient();
            return $client->getAnimeVideos(new AnimeVideosRequest($malId));
        });
        respond([
            'source' => 'mal',
            'backend' => 'jikan',
            'data' => array_map('promoToArray', $result->getPromos()),
        ]);
    } catch (Throwable $error) {
        respond([
            'error' => 'jikan_request_failed',
            'type' => $error::class,
            'message' => $error->getMessage(),
        ], 502);
    }
}

if (preg_match('#^/anime/(\d+)/episodes$#', $path, $match)) {
    $malId = (int) $match[1];
    $page = max(1, (int) ($_GET['page'] ?? 1));
    try {
        $result = withActivity(function () use ($malId, $page) {
            $client = malClient();
            return $client->getAnimeEpisodes(new AnimeEpisodesRequest($malId, $page));
        });
        respond([
            'source' => 'mal',
            'backend' => 'jikan',
            'page' => $page,
            'last_visible_page' => $result->getLastVisiblePage(),
            'has_next_page' => $result->hasNextPage(),
            'data' => array_map('episodeListItemToArray', $result->getResults()),
        ]);
    } catch (Throwable $error) {
        respond([
            'error' => 'jikan_request_failed',
            'type' => $error::class,
            'message' => $error->getMessage(),
        ], 502);
    }
}

if (preg_match('#^/anime/(\d+)/episodes/(\d+)$#', $path, $match)) {
    $malId = (int) $match[1];
    $episode = (int) $match[2];
    try {
        $result = withActivity(function () use ($malId, $episode) {
            $client = malClient();
            return $client->getAnimeEpisode(new AnimeEpisodeRequest($malId, $episode));
        });
        respond([
            'source' => 'mal',
            'backend' => 'jikan',
            'data' => episodeDetailToArray($result),
        ]);
    } catch (Throwable $error) {
        respond([
            'error' => 'jikan_request_failed',
            'type' => $error::class,
            'message' => $error->getMessage(),
        ], 502);
    }
}

respond(['error' => 'not_found'], 404);
