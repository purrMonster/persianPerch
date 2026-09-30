# perch: persianPerch's one container (dev plan 1-2). Runs as a non-root user; the
# fleet repo is mounted read-only at PERCH_REPO_DIR, scentTrail lives in /data.
# Base image pinned by tag and digest (runbook, M0 entry); bump both together.
FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

# git: catTree lists the fleet repo with `git ls-files` (tracked files only).
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --user-group --home-dir /nonexistent --shell /usr/sbin/nologin perch \
 && mkdir -p /data && chown perch:perch /data

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY perch ./perch

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PERCH_TRAIL_DB=/data/scentTrail.db \
    PERCH_REPO_DIR=/opt/purrbrews
USER perch
VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4)"]
CMD ["python", "-m", "perch"]
