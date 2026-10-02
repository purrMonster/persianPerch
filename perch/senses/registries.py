"""registries: "is a newer release of this pinned image out?" (05 plan M4, binocs).

Anonymous reads of three public registry APIs, nothing else, and perch never pulls an image:

- **Docker Hub's registry** (images with no registry host, e.g. ``traefik:v3.7.13``, ``n8nio/n8n:2.39.7``;
  official images live under ``library/``) and **ghcr.io** speak the same OCI distribution API
  (``GET /v2/<name>/tags/list?n=<int>``), so one code path reads both. Anonymous access to public images works
  by the registry's token challenge: the first request is answered ``401`` with ``WWW-Authenticate: Bearer
  realm=..., service=..., scope=...``; perch asks the realm for a token (no credential) and repeats. Tags come
  in lexical order and a ``Link: <...>; rel="next"`` header says there are more, so the whole list is read (up
  to 20 pages of 1000). A realm is followed only when it is the registry's own token service (ghcr.io's
  ``ghcr.io``, Docker's ``auth.docker.io``), never a host the header names on its own.
- **Not Docker Hub's REST API** (its ``/v2/namespaces/<ns>/repositories/<repo>/tags`` route): the OpenAPI spec
  Docker publishes declares it bearer-authenticated, documents only ``page`` and ``page_size`` for it (no
  ordering), and makes no promise to anonymous clients, so perch does not depend on it (runbook 2026-10-03).
- Rate limits: Docker documents ``429`` with ``Retry-After`` and an abuse limit per IP address; perch makes one
  list per repository a week with a pause between requests, and a 429 from any registry stops the run until
  its ``Retry-After``.
- **lscr.io** (``lscr.io/linuxserver/<image>``) is LinuxServer's name for ``ghcr.io/linuxserver/<image>``
  (their documentation says the registries behind it are GitHub's and Docker Hub's); perch asks ghcr.io.

A tag is comparable only when it is a release: ``[v]MAJOR.MINOR.PATCH`` (at least three numbers) with an
optional flavour (``-alpine``, ``-omnibus``, ``-apache``) and, for LinuxServer, a ``-lsNNN`` rebuild counter
that is ignored (a rebuild is not a release). A newer release has the same flavour and the same number of
parts. ``stable``, ``latest``, ``main``, a digest pin, or a line pin such as ``postgres:16`` or
``v1.10`` can't be compared and are reported as such, never guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx2

HUB_HOST = "registry-1.docker.io"
GHCR_HOST = "ghcr.io"
PAGES = 20
# the token service each registry sends anonymous clients to; any other realm is refused
TOKEN_HOSTS = {HUB_HOST: "auth.docker.io", GHCR_HOST: "ghcr.io"}
_TAG = re.compile(r"^v?(?P<ver>\d+(?:\.\d+){2,})(?:-(?P<flavour>[A-Za-z0-9._-]+))?$")
_REBUILD = re.compile(r"(?:^|-)ls\d+$")
_CHALLENGE = re.compile(r'(\w+)="([^"]*)"')


class RegistryError(RuntimeError):
    """A registry can't be read right now. ``retryAfter`` is set when it asked perch to wait (HTTP 429)."""

    def __init__(self, message: str, retryAfter: int | None = None) -> None:
        super().__init__(message)
        self.retryAfter = retryAfter


@dataclass(frozen=True)
class Image:
    registry: str  # registry-1.docker.io or ghcr.io
    repo: str  # namespace/name, "library/<name>" for an official Docker Hub image
    tag: str
    ref: str  # as written in the compose file

    @property
    def key(self) -> str:
        return f"{self.registry}/{self.repo}"


@dataclass(frozen=True)
class Release:
    numbers: tuple[int, ...]
    flavour: str

    def newerThan(self, other: Release) -> bool:
        return (
            self.flavour == other.flavour and len(self.numbers) == len(other.numbers) and self.numbers > other.numbers
        )

    def text(self) -> str:
        return ".".join(map(str, self.numbers)) + (f"-{self.flavour}" if self.flavour else "")


def parseTag(tag: str) -> Release | None:
    match = _TAG.match(tag)
    if not match:
        return None
    flavour = _REBUILD.sub("", match["flavour"] or "")
    return Release(tuple(int(n) for n in match["ver"].split(".")), flavour)


def parseImage(ref: str) -> Image | None:
    """The image as a registry knows it, or None for a pin that can't be compared (a digest, no tag, a
    moving tag, a line, a local build, a registry perch doesn't read)."""
    if "@" in ref or ":" not in ref.rsplit("/", 1)[-1]:
        return None
    name, _, tag = ref.rpartition(":")
    parts = name.split("/")
    if "." in parts[0] or ":" in parts[0] or parts[0] == "localhost":
        host, rest = parts[0].lower(), parts[1:]
        if host in ("lscr.io", GHCR_HOST):
            host = GHCR_HOST
        elif host in ("docker.io", "index.docker.io", "registry-1.docker.io"):
            host = HUB_HOST
        else:
            return None
        repo = "/".join(rest)
    else:
        host = HUB_HOST
        repo = "/".join(parts) if len(parts) > 1 else f"library/{parts[0]}"
    if parseTag(tag) is None or repo.count("/") != 1:
        return None
    return Image(host, repo, tag, ref)


class Registries:
    def __init__(self, *, transport: "httpx2.AsyncBaseTransport | None" = None, timeout: float = 15.0) -> None:
        self._http = httpx2.AsyncClient(
            timeout=httpx2.Timeout(timeout, connect=min(timeout, 5.0)),
            transport=transport,
            follow_redirects=False,
            headers={"accept": "application/json", "user-agent": "persianPerch-binocs"},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def tags(self, image: Image) -> list[str]:
        return await self._oci(image.registry, image.repo)

    # -- OCI distribution (Docker Hub's registry and ghcr.io) ---------------------------------------------------------

    async def _oci(self, host: str, repo: str) -> list[str]:
        url: str | None = f"https://{host}/v2/{repo}/tags/list"
        params: dict[str, str] | None = {"n": "1000"}
        token: str | None = None
        tags: list[str] = []
        for _ in range(PAGES):
            answer, link, token = await self._ociPage(host, url, params, token)
            tags.extend(t for t in answer.get("tags") or [] if isinstance(t, str))
            if not link:
                break
            url, params = f"https://{host}{link}" if link.startswith("/") else link, None
            if urlparse(url).hostname != host:
                break
        return tags

    async def _ociPage(self, host: str, url, params, token):
        for attempt in range(2):
            headers = {"authorization": f"Bearer {token}"} if token else {}
            response = await self._get(url, params, headers)
            if response.status_code == 401 and attempt == 0:
                token = await self._token(host, response.headers.get("www-authenticate", ""))
                continue
            return self._decode(response, url), _nextLink(response.headers.get("link", "")), token
        raise RegistryError(f"{host} refused an anonymous read")

    async def _token(self, host: str, challenge: str) -> str:
        fields = dict(_CHALLENGE.findall(challenge))
        realm = fields.get("realm", "")
        if urlparse(realm).hostname != TOKEN_HOSTS.get(host):  # only the registry's own token service
            raise RegistryError(f"{host} sent a token challenge for another host; not followed")
        params = {k: fields[k] for k in ("service", "scope") if k in fields}
        answer = self._decode(await self._get(realm, params, {}), realm)
        token = answer.get("token") or answer.get("access_token")
        if not isinstance(token, str) or not token:
            raise RegistryError(f"{host} gave no anonymous token")
        return token

    # -- shared -----------------------------------------------------------------------------

    async def _get(self, url, params, headers) -> httpx2.Response:
        try:
            return await self._http.get(url, params=params, headers=headers)
        except httpx2.HTTPError as exc:
            raise RegistryError(f"can't reach {urlparse(str(url)).hostname}: {type(exc).__name__}") from None

    async def _json(self, url, params) -> dict:
        return self._decode(await self._get(url, params, {}), url)

    @staticmethod
    def _decode(response: httpx2.Response, url) -> dict:
        host = urlparse(str(url)).hostname
        if response.status_code == 429:
            wait = response.headers.get("retry-after", "")
            raise RegistryError(f"{host} is rate limiting perch", int(wait) if wait.isdigit() else 3600)
        if response.status_code >= 400:
            raise RegistryError(f"{host} answered HTTP {response.status_code}")
        try:
            answer = response.json()
        except ValueError:
            raise RegistryError(f"{host} did not answer JSON") from None
        if not isinstance(answer, dict):
            raise RegistryError(f"{host} answered something other than an object")
        return answer


def _nextLink(header: str) -> str | None:
    match = re.search(r'<([^>]+)>\s*;\s*rel="?next"?', header)
    return match.group(1) if match else None


def newestRelease(current: Release, tags: list[str]) -> Release | None:
    """The highest release in ``tags`` that is newer than ``current``, or None."""
    best: Release | None = None
    for tag in tags:
        found = parseTag(tag)
        if found and found.newerThan(current) and (best is None or found.numbers > best.numbers):
            best = found
    return best
