FROM php:8.4-cli

RUN apt-get update \
    && apt-get install -y --no-install-recommends unzip \
    && rm -rf /var/lib/apt/lists/*

COPY --from=composer:2 /usr/bin/composer /usr/local/bin/composer

WORKDIR /app
COPY jikan_service/composer.json /app/composer.json
RUN composer install --no-dev --prefer-dist --no-interaction --no-progress --classmap-authoritative

COPY jikan_service/public /app/public

ENV JIKAN_PORT=8091
EXPOSE 8091
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD php -r '$p=getenv("JIKAN_PORT") ?: "8091"; $j=@json_decode(@file_get_contents("http://127.0.0.1:".$p."/health"), true); exit(($j["ok"]??false) ? 0 : 1);'

CMD ["sh", "-c", "php -S 127.0.0.1:${JIKAN_PORT:-8091} -t public public/router.php"]
