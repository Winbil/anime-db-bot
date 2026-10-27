<?php

declare(strict_types=1);

require dirname(__DIR__) . '/vendor/autoload.php';

use Composer\InstalledVersions;
use Jikan\MyAnimeList\MalClient;
use Jikan\Request\Anime\AnimeEpisodeRequest;
use Jikan\Request\Anime\AnimeEpisodesRequest;

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

if (preg_match('#^/anime/(\d+)/episodes$#', $path, $match)) {
    $malId = (int) $match[1];
    $page = max(1, (int) ($_GET['page'] ?? 1));
    try {
        $result = withActivity(function () use ($malId, $page) {
            $client = new MalClient();
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
            $client = new MalClient();
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
