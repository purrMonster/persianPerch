"""Run perch: ``python -m perch`` (the container's command)."""

import os

import uvicorn

from .windowsill.app import createApp


def main() -> None:
    uvicorn.run(
        createApp(),
        host=os.environ.get("PERCH_HOST", "0.0.0.0"),  # noqa: S104 - inside its container
        port=int(os.environ.get("PERCH_PORT", "8080")),
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get("PERCH_TRUSTED_PROXIES", "127.0.0.1"),
        access_log=False,
    )


if __name__ == "__main__":
    main()
