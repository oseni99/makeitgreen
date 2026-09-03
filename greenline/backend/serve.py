"""Supported production launcher with explicit trusted-proxy configuration."""

from __future__ import annotations

import os

import uvicorn

import operations


def main() -> None:
    proxies = operations.trusted_proxy_cidrs(os.environ)
    os.environ["GREENLINE_PROCESS_ROLE"] = "api"
    os.environ["GREENLINE_PROXY_HEADERS_CONFIGURED"] = "1"
    uvicorn.run(
        "app:app",
        host=os.getenv("GREENLINE_HOST", "0.0.0.0"),
        port=int(os.getenv("GREENLINE_PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips=list(proxies),
        server_header=False,
        access_log=False,
        timeout_graceful_shutdown=75,
    )


if __name__ == "__main__":
    main()
