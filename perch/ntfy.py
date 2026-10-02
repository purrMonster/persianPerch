"""ntfy: the one module that knows how to publish to ntfy (05 plan M3, A6, A7, A11).

Built against ntfy's publish API (docs.ntfy.sh/publish, read 2026-10-02; the fleet runs v2.28.0):

- JSON publishing: ``POST {base}`` with ``{"topic", "title", "message", "priority", "tags", "actions"}``
  (priority 1 to 5, 3 is the default, 4 is "high"; tags is a list; at most three actions). A JSON body
  keeps a title with any character out of the HTTP headers.
- An access token goes in ``Authorization: Bearer tk_...``; the ntfy.sh critical topic needs none.
- An ``http`` action is a button: ``{"action": "http", "label", "url", "method"}``; the method defaults
  to POST, and ``clear`` removes the notification after the tap. The phone sends exactly that request.

The URL is ``https://<host>/<topic>`` (what the fleet's secrets hold); it carries the real domain or a
secret topic, so it is never logged or shown, and no error message here repeats it.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx2


class PushError(Exception):
    """A push that didn't go. The message says why in words that never include the URL or a token."""


class Ntfy:
    def __init__(
        self, url: str, token: str = "", *, transport: "httpx2.AsyncBaseTransport | None" = None, timeout: float = 10.0
    ) -> None:
        parts = urlsplit(url)
        topic = parts.path.rstrip("/").rpartition("/")[2]
        if parts.scheme not in ("http", "https") or not parts.netloc or not topic:
            raise ValueError("the push URL must look like https://host/topic")
        self.topic = topic
        self._base = urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/").rpartition("/")[0] + "/", "", ""))
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._http = httpx2.AsyncClient(
            timeout=httpx2.Timeout(timeout, connect=min(timeout, 5.0)), transport=transport, follow_redirects=False
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def send(
        self,
        *,
        title: str,
        message: str,
        priority: int = 3,
        tags: "tuple[str, ...]" = (),
        actions: "tuple[dict[str, Any], ...]" = (),
    ) -> None:
        body: dict[str, Any] = {"topic": self.topic, "title": title, "message": message, "priority": priority}
        if tags:
            body["tags"] = list(tags)
        if actions:
            body["actions"] = list(actions)
        try:
            response = await self._http.post(self._base, json=body, headers=self._headers)
        except httpx2.TimeoutException as exc:
            raise PushError("timed out") from exc
        except httpx2.HTTPError as exc:
            raise PushError("couldn't connect") from exc
        if response.status_code >= 300:
            raise PushError(f"answered HTTP {response.status_code}")
