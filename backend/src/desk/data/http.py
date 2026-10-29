"""Shared HTTP client settings for the data sources."""

import httpx

USER_AGENT = "crypto-desk (+https://github.com/robertsolomon002/crypto-desk)"


def make_client(base_url: str = "", headers: dict[str, str] | None = None) -> httpx.Client:
    """An httpx client with our User-Agent, a 30 s timeout and 3 connection retries."""
    return httpx.Client(
        base_url=base_url,
        headers={"User-Agent": USER_AGENT, **(headers or {})},
        timeout=httpx.Timeout(30.0),
        transport=httpx.HTTPTransport(retries=3),
        follow_redirects=True,
    )
