# Security Policy

## Supported versions

Security fixes are made against the current `main` branch. Older commits, forks, and private deployments are not maintained as separate supported release lines unless a release policy is introduced later.

## Reporting a vulnerability

Do **not** open a public issue for a vulnerability, leaked credential, authentication bypass, or other security-sensitive report.

Preferred reporting path:

1. use GitHub's private vulnerability reporting / security advisory flow for this repository when it is available;
2. if that flow is unavailable, contact the maintainer through a private channel shown on the maintainer's GitHub profile.

Include enough detail to reproduce and evaluate the issue:

- affected commit or version;
- impact and attack preconditions;
- minimal reproduction steps or proof of concept;
- relevant logs with secrets and personal data removed;
- any suggested mitigation, if known.

Please do not test a suspected vulnerability in a way that disrupts Telegram, MyAnimeList, AniList, Shikimori, AniDB, Jikan, or any other third-party service.

## Security-sensitive areas

Reports are especially useful for issues involving:

- Telegram admin authorization or callback ownership checks;
- credential/token exposure or insufficient log redaction;
- unsafe handling of self-hosted Telegram Bot API endpoints;
- SSRF, injection, path traversal, or unsafe file/database handling;
- cross-user state leakage;
- mapping mutations that bypass authorization or confirmation controls;
- dependency or build-chain compromise that affects distributed code.

Third-party service vulnerabilities are out of scope unless `anime-db-bot` introduces or amplifies the security issue through its own behavior.

## Disclosure

Please allow reasonable time for triage and remediation before public disclosure. There is currently no guaranteed response-time SLA, but confirmed security issues will be prioritized over normal feature work.
