# Playwright's image carries the browsers but not the Python package; add the matching one.
FROM mcr.microsoft.com/playwright/python:v1.56.0-noble@sha256:a7f6cf3ae520c9d670ad956572c13747ed5abdbba5123a01526f873ed1662528
RUN python3 -m pip install --no-cache-dir --break-system-packages playwright==1.56.0
