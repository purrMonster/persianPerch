# The image that runs purrbrews-containers' OWN test suite on a copy of the pinned fleet clone with
# integration/ applied (M6 gate). Python 3.13 like the nodes. The fleet's tests skip their main
# classes under root ("the scripts refuse to run as root"), so they run once as the unprivileged
# user `fleet` and once as root (the real-backup test needs root, restic, sqlite3 and setpriv).
# Built and run by scripts/test.ps1; every container it starts carries the project label.
FROM python:3.13-slim@sha256:7c61056e61ac89e852de05f3dc6fa51a6dd2181797bceed46aa725dd7cb2cd3b
RUN apt-get update \
 && apt-get install -y --no-install-recommends git openssl bash restic sqlite3 util-linux rsync \
 && rm -rf /var/lib/apt/lists/* \
 && git config --system --add safe.directory '*' \
 && useradd --create-home --uid 1000 fleet
ENV PYTHONDONTWRITEBYTECODE=1
USER fleet
WORKDIR /home/fleet
