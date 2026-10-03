# The image for kitten's real-inotifywait tests (M5, ADR 0010): the nodes' Python (3.13, the same pinned digest as
# scripts/test.ps1) plus the Debian package the nodes get at M6. Built and run by scripts/test.ps1.
FROM python:3.13-slim@sha256:7c61056e61ac89e852de05f3dc6fa51a6dd2181797bceed46aa725dd7cb2cd3b
RUN apt-get update \
 && apt-get install -y --no-install-recommends inotify-tools git \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
