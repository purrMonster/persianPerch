# The test image: perch's base plus git (catTree and tests S5/S6/S8 read tracked files)
# and the dev requirements. Built by scripts/test.ps1; the source is mounted at /src.
FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-dev.txt /tmp/req/
RUN pip install --no-cache-dir -r /tmp/req/requirements-dev.txt
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 RUFF_CACHE_DIR=/tmp/ruff PYTEST_ADDOPTS="-p no:cacheprovider"
WORKDIR /src
