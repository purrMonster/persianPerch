"""A real perch on a loopback port, for the tests that need a socket: the live scentTrail (a server-sent events
stream never ends, and starlette's TestClient waits for a response to end) and the M5 gate (kitten really posts
to it). Plus a small reader for the stream."""

from __future__ import annotations

import asyncio
import threading
import time
import urllib.request
from collections.abc import Iterator

import uvicorn


class LiveServer:
    def __init__(self, app) -> None:
        self.app = app
        config = uvicorn.Config(
            app, host="127.0.0.1", port=0, log_level="warning", lifespan="on", timeout_graceful_shutdown=2
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True, name="live-perch")
        self.url = ""

    def __enter__(self) -> LiveServer:
        self.thread.start()
        end = time.time() + 15
        while not self.server.started:
            if time.time() > end or not self.thread.is_alive():
                raise RuntimeError("the test perch did not start")
            time.sleep(0.02)
        port = self.server.servers[0].sockets[0].getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"
        return self

    def __exit__(self, *exc) -> None:
        self.server.should_exit = True
        self.thread.join(15)

    def get(self, path: str, headers: dict | None = None, timeout: float = 10) -> tuple[int, str]:
        request = urllib.request.Request(self.url + path, headers=headers or {})  # noqa: S310 - loopback
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.status, response.read().decode()


class Stream:
    """One open ``text/event-stream``: ``frames()`` yields what arrives, each as a dict of its fields."""

    def __init__(self, server: LiveServer, path: str, headers: dict | None = None, timeout: float = 8) -> None:
        request = urllib.request.Request(server.url + path, headers=headers or {})  # noqa: S310
        self.response = urllib.request.urlopen(request, timeout=timeout)  # noqa: S310
        self.headers = self.response.headers

    def frames(self) -> Iterator[dict]:
        """Frames until the stream ends or a read waits longer than the timeout."""
        frame: dict = {"data": [], "comment": []}
        while True:
            try:
                raw = self.response.readline()
            except (TimeoutError, OSError):
                return
            if not raw:
                return
            line = raw.decode().rstrip("\n")
            if line == "":
                if frame["data"] or frame["comment"] or len(frame) > 2:
                    yield {**frame, "data": "\n".join(frame["data"])}
                frame = {"data": [], "comment": []}
            elif line.startswith(":"):
                frame["comment"].append(line[1:].strip())
            else:
                key, _, value = line.partition(":")
                value = value[1:] if value.startswith(" ") else value
                if key == "data":
                    frame["data"].append(value)
                else:
                    frame[key] = value

    def close(self) -> None:
        self.response.close()


class OtherLoop:
    """An asyncio loop on its own thread: where the fake Home Assistant lives, away from perch's loop."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True, name="other-loop")
        self.thread.start()

    def run(self, coro, timeout: float = 10):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def close(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)
        self.loop.close()
