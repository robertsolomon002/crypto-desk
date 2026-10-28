"""Stage 0.3 source probe: checks every free data source the roadmap depends on.

Run from `backend/`:  uv run python scripts/probe_sources.py [--only ccxt,fred] [--json out.json]

Prints one line per check and never prints a key. MCO's feed is probed for the channel id and a
video count only: no titles or descriptions are printed (Decision 6), because CI logs are public.
If GITHUB_STEP_SUMMARY is set, a Markdown table of the results is appended to it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

import ccxt
import feedparser
import httpx
import yaml

from desk.config import get_settings

UA = {"User-Agent": "crypto-desk-probe/0.3 (+https://github.com/robertsolomon002/crypto-desk)"}
TIMEOUT = httpx.Timeout(30.0)
COINS = ["BTC", "ETH", "SOL"]
MCO_HANDLE = "MoreCryptoOnline"


@dataclass
class Result:
    source: str
    check: str
    ok: bool
    detail: str
    data: dict[str, Any] = field(default_factory=dict)


RESULTS: list[Result] = []


def record(source: str, check: str, ok: bool, detail: str, **data: Any) -> None:
    RESULTS.append(Result(source, check, ok, detail, data))
    print(f"[{'PASS' if ok else 'FAIL'}] {source} | {check} | {detail}", flush=True)


def iso(ms: int | float) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%d")


def guarded(source: str, check: str, fn: Callable[[], None]) -> None:
    try:
        fn()
    except Exception as exc:  # a probe reports failures, it never stops on them
        record(source, check, False, f"{type(exc).__name__}: {str(exc)[:200]}")


# --- ccxt -----------------------------------------------------------------------------------


def earliest_daily(ex: ccxt.Exchange, symbol: str) -> tuple[str | None, int]:
    """Walk 300-day windows forward from 2010 until candles appear; return (first date, calls)."""
    day = 86_400_000
    since = int(datetime(2010, 1, 1, tzinfo=UTC).timestamp() * 1000)
    now = int(time.time() * 1000)
    calls = 0
    while since < now:
        candles = ex.fetch_ohlcv(symbol, "1d", since=since, limit=300)
        calls += 1
        candles = [c for c in candles if c[0] >= since]
        if candles:
            return iso(candles[0][0]), calls
        since += 300 * day
    return None, calls


def probe_ccxt() -> None:
    for ex_id in ["coinbase", "coinbaseexchange", "bitstamp"]:

        def run(ex_id: str = ex_id) -> None:
            ex = getattr(ccxt, ex_id)({"enableRateLimit": True})
            ex.load_markets()
            tfs = sorted((ex.timeframes or {}).keys())
            has4h = "4h" in tfs
            record(
                f"ccxt:{ex_id}",
                "timeframes",
                True,
                f"4h={'yes' if has4h else 'no'}; 6h={'yes' if '6h' in tfs else 'no'}; "
                f"rateLimit={ex.rateLimit}ms; all={','.join(tfs)}",
                timeframes=tfs,
                rate_limit_ms=ex.rateLimit,
            )
            if has4h:
                c = ex.fetch_ohlcv("BTC/USD", "4h", limit=10)
                record(f"ccxt:{ex_id}", "4h fetch BTC/USD", bool(c), f"{len(c)} candles")
            for coin in COINS:
                sym = f"{coin}/USD"
                if sym not in ex.markets:
                    record(f"ccxt:{ex_id}", f"{sym} daily", False, "market not listed")
                    continue
                first, calls = earliest_daily(ex, sym)
                record(
                    f"ccxt:{ex_id}",
                    f"{sym} daily history",
                    first is not None,
                    f"earliest={first} ({calls} calls)",
                    earliest=first,
                )

        guarded(f"ccxt:{ex_id}", "exchange", run)


# --- Coin Metrics community -----------------------------------------------------------------

CM = "https://community-api.coinmetrics.io/v4"
CM_METRICS = ["PriceUSD", "CapMrktCurUSD", "CapRealUSD", "CapMVRVCur", "AdrActCnt", "HashRate"]


def probe_coinmetrics() -> None:
    with httpx.Client(headers=UA, timeout=TIMEOUT) as c:
        r = c.get(f"{CM}/catalog-v2/asset-metrics", params={"assets": "btc,eth"})
        r.raise_for_status()
        limits = {k: v for k, v in r.headers.items() if "ratelimit" in k.lower()}
        record("coinmetrics", "rate-limit headers", True, json.dumps(limits) or "none")
        catalog: dict[str, set[str]] = {}
        for asset in r.json().get("data", []):
            catalog[asset["asset"]] = {m["metric"] for m in asset.get("metrics", [])}
        for asset, metrics in catalog.items():
            record("coinmetrics", f"{asset} free catalog", True, ",".join(sorted(metrics)))
        for asset in ["btc", "eth"]:
            for metric in CM_METRICS:
                if metric not in catalog.get(asset, set()):
                    record("coinmetrics", f"{asset} {metric}", False, "not in community catalog")
                    continue
                q = c.get(
                    f"{CM}/timeseries/asset-metrics",
                    params={
                        "assets": asset,
                        "metrics": metric,
                        "frequency": "1d",
                        "page_size": 1,
                        "start_time": "2009-01-01",
                        "paging_from": "start",
                    },
                )
                rows = q.json().get("data", []) if q.status_code == 200 else []
                start = rows[0]["time"][:10] if rows else None
                record(
                    "coinmetrics",
                    f"{asset} {metric}",
                    bool(rows),
                    f"HTTP {q.status_code}; starts {start}",
                    start=start,
                )
                time.sleep(0.7)


# --- FRED -----------------------------------------------------------------------------------


def probe_fred() -> None:
    key = get_settings().fred_api_key
    if key is None:
        record("fred", "key", False, "FRED_API_KEY not set")
        return
    with httpx.Client(headers=UA, timeout=TIMEOUT) as c:
        for sid in ["DTWEXBGS", "DGS10", "DFF", "M2SL"]:
            r = c.get(
                "https://api.stlouisfed.org/fred/series",
                params={"series_id": sid, "api_key": key.get_secret_value(), "file_type": "json"},
            )
            if r.status_code != 200:
                record("fred", sid, False, f"HTTP {r.status_code}")
                continue
            s = r.json()["seriess"][0]
            record(
                "fred",
                sid,
                True,
                f"{s['frequency_short']} {s['observation_start']}..{s['observation_end']}; "
                f"units={s['units_short']}",
                start=s["observation_start"],
                end=s["observation_end"],
                frequency=s["frequency_short"],
            )


# --- Fear & Greed ---------------------------------------------------------------------------


def probe_fng() -> None:
    with httpx.Client(headers=UA, timeout=TIMEOUT) as c:
        r = c.get("https://api.alternative.me/fng/", params={"limit": 0, "format": "json"})
        r.raise_for_status()
        rows = r.json()["data"]
        first = iso(int(rows[-1]["timestamp"]) * 1000)
        last = iso(int(rows[0]["timestamp"]) * 1000)
        record("fng", "full history", True, f"{len(rows)} days {first}..{last}", start=first)


# --- CoinGecko Demo -------------------------------------------------------------------------

CG = "https://api.coingecko.com/api/v3"


def probe_coingecko() -> None:
    key = get_settings().coingecko_demo_key
    if key is None:
        record("coingecko", "key", False, "COINGECKO_DEMO_KEY not set")
        return
    headers = {**UA, "x-cg-demo-api-key": key.get_secret_value()}
    with httpx.Client(headers=headers, timeout=TIMEOUT) as c:
        r = c.get(f"{CG}/global")
        dom = r.json().get("data", {}).get("market_cap_percentage", {}) if r.is_success else {}
        limits = {k: v for k, v in r.headers.items() if "limit" in k.lower()}
        record(
            "coingecko",
            "/global dominance",
            r.is_success and "btc" in dom,
            f"HTTP {r.status_code}; btc={dom.get('btc', 0):.2f}% eth={dom.get('eth', 0):.2f}%; "
            f"limit headers={json.dumps(limits) or 'none'}",
        )
        # Dominance history: /global/market_cap_chart is documented as paid-only; confirm.
        r = c.get(f"{CG}/global/market_cap_chart", params={"vs_currency": "usd", "days": 365})
        record(
            "coingecko",
            "/global/market_cap_chart (history)",
            r.is_success,
            f"HTTP {r.status_code}; {r.text[:120]!r}",
        )
        # Fallback for BTC dominance history: BTC market cap history (Demo: 365 days max).
        r = c.get(f"{CG}/coins/bitcoin/market_chart", params={"vs_currency": "usd", "days": 365})
        n = len(r.json().get("market_caps", [])) if r.is_success else 0
        record(
            "coingecko",
            "/coins/bitcoin/market_chart 365d",
            r.is_success,
            f"HTTP {r.status_code}; {n} points",
        )
        r = c.get(f"{CG}/coins/bitcoin/market_chart", params={"vs_currency": "usd", "days": "max"})
        record(
            "coingecko",
            "/coins/bitcoin/market_chart max",
            r.is_success,
            f"HTTP {r.status_code}; {r.text[:120]!r}" if not r.is_success else "full history ok",
        )


# --- RSS ------------------------------------------------------------------------------------

RSS_ALTERNATES = {
    "CoinDesk": ["https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml"],
    "Cointelegraph": ["https://cointelegraph.com/feed"],
    "Decrypt": ["https://decrypt.co/feed/"],
    "The Block": ["https://www.theblock.co/rss.xml", "https://www.theblock.co/rss"],
}


def fetch_feed(c: httpx.Client, url: str) -> tuple[int, Any]:
    r = c.get(url, follow_redirects=True)
    return r.status_code, feedparser.parse(r.content) if r.is_success else None


def probe_rss() -> None:
    cfg = yaml.safe_load((get_settings().config_dir / "feeds.yaml").read_text(encoding="utf-8"))
    with httpx.Client(headers=UA, timeout=TIMEOUT) as c:
        for feed in cfg["feeds"]:
            name = feed["name"]
            for url in [feed["url"], *RSS_ALTERNATES.get(name, [])]:
                status, parsed = fetch_feed(c, url)
                items = len(parsed.entries) if parsed else 0
                ok = status == 200 and items > 0
                record("rss", f"{name} {url}", ok, f"HTTP {status}; {items} items", url=url)
                if ok:
                    break


def probe_mco() -> None:
    with httpx.Client(headers={**UA, "Accept-Language": "en"}, timeout=TIMEOUT) as c:
        r = c.get(f"https://www.youtube.com/@{MCO_HANDLE}", follow_redirects=True)
        canonical = r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{22})"'
        m = re.search(canonical, r.text)
        m = m or re.search(r'"(?:channelId|externalId)":"(UC[\w-]{22})"', r.text)
        if not m:
            record("mco", "channel id", False, f"HTTP {r.status_code}; id not found on page")
            return
        cid = m.group(1)
        record("mco", "channel id", True, cid, channel_id=cid)
        status, parsed = fetch_feed(c, f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}")
        n = len(parsed.entries) if parsed else 0
        newest = parsed.entries[0].get("published", "")[:10] if n else None
        # Count only: no titles or descriptions in output (Decision 6).
        record("mco", "channel RSS", n > 0, f"HTTP {status}; {n} videos; newest {newest}")


# --- Hyperliquid (optional) ------------------------------------------------------------------


def probe_hyperliquid() -> None:
    start = int((time.time() - 3 * 86_400) * 1000)
    with httpx.Client(headers=UA, timeout=TIMEOUT) as c:
        for coin in COINS:
            r = c.post(
                "https://api.hyperliquid.xyz/info",
                json={"type": "fundingHistory", "coin": coin, "startTime": start},
            )
            rows = r.json() if r.is_success else []
            record(
                "hyperliquid",
                f"{coin} funding",
                bool(rows),
                f"HTTP {r.status_code}; {len(rows)} rows in 3 days (hourly)",
            )


PROBES: dict[str, Callable[[], None]] = {
    "ccxt": probe_ccxt,
    "coinmetrics": probe_coinmetrics,
    "fred": probe_fred,
    "fng": probe_fng,
    "coingecko": probe_coingecko,
    "rss": probe_rss,
    "mco": probe_mco,
    "hyperliquid": probe_hyperliquid,
}


def write_summary(path: str) -> None:
    lines = ["## Source probe", "", "| | Source | Check | Detail |", "|---|---|---|---|"]
    for r in RESULTS:
        detail = r.detail.replace("|", "\\|")
        lines.append(f"| {'✅' if r.ok else '❌'} | {r.source} | {r.check} | {detail} |")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="comma-separated subset of: " + ",".join(PROBES))
    parser.add_argument("--json", help="write results to this JSON file")
    args = parser.parse_args()
    names = args.only.split(",") if args.only else list(PROBES)
    for name in names:
        print(f"--- {name}", flush=True)
        guarded(name, "probe", PROBES[name])
    print(f"\n{sum(r.ok for r in RESULTS)}/{len(RESULTS)} checks passed")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump([asdict(r) for r in RESULTS], fh, indent=2)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        write_summary(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
