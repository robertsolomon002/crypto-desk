"""Check cycle anchors against an independent price source (Section 9 quality bar, D35).

Anchors found in Coinbase candles are compared with Coin Metrics `PriceUSD`; anchors in the
Coin Metrics backfill (the 2013 cycle) with Bitstamp daily closes via ccxt. An anchor passes
when the independent extreme in the same window is within 5% of our price and either within 2
days of our date or a near-tie: the independent close on our date is within 1% of its own
extreme (a double bottom such as 2022-11-09 / 2022-11-21 flips on cents). Network calls:
run it by hand (`desk analytics verify-anchors`), not in unit tests.
"""

import datetime as dt
from dataclasses import dataclass

import ccxt
import httpx
import pandas as pd

from desk.analytics.cycles import CycleConfig, resolve_anchors
from desk.data import coinmetrics, market

MAX_DAYS = 2
MAX_PRICE_DIFF = 0.05
NEAR_TIE = 0.01


@dataclass(frozen=True)
class AnchorCheck:
    coin: str
    cycle: str
    kind: str
    date: dt.date
    price: float
    source: str
    ref_source: str
    ref_date: dt.date | None
    ref_price: float | None
    ref_on_date: float | None  # the independent close on our anchor date

    @property
    def near_tie(self) -> bool:
        if self.ref_on_date is None or self.ref_price is None:
            return False
        return abs(self.ref_on_date / self.ref_price - 1) <= NEAR_TIE

    @property
    def ok(self) -> bool:
        if self.ref_date is None or self.ref_price is None:
            return False
        close_in_time = abs((self.date - self.ref_date).days) <= MAX_DAYS
        return abs(self.price / self.ref_price - 1) <= MAX_PRICE_DIFF and (
            close_in_time or self.near_tie
        )


def _coinmetrics_closes(client: httpx.Client, coin: str, window) -> pd.Series:
    points = coinmetrics.fetch_asset_metric(
        client, coinmetrics.ASSETS[coin], "PriceUSD", window[0], window[1]
    )
    return pd.Series({d: p for d, p in points}, dtype="float64")


def _bitstamp_closes(exchange: ccxt.Exchange, window) -> pd.Series:
    end = dt.datetime.combine(window[1] + dt.timedelta(days=1), dt.time(), tzinfo=dt.UTC)
    candles = market.fetch_daily(exchange, "BTC/USD", window[0], now=end)
    return pd.Series({market._to_date(c[0]): float(c[4]) for c in candles}, dtype="float64")


def verify_anchors(
    daily: dict[str, pd.DataFrame], config: dict[str, list[CycleConfig]]
) -> list[AnchorCheck]:
    checks = []
    exchange = ccxt.bitstamp({"enableRateLimit": True})
    with coinmetrics.make_client() as cm:
        for coin, cycles in config.items():
            frame = daily.get(coin)
            if frame is None or frame.empty:
                continue
            for cfg, cycle in zip(cycles, resolve_anchors(frame, cycles), strict=True):
                for kind, window in (("bottom", cfg.bottom_window), ("top", cfg.top_window)):
                    anchor = cycle.anchor(kind)
                    if anchor is None:
                        continue
                    source = str(frame.loc[pd.Timestamp(anchor.date, tz="UTC"), "source"])
                    if source == "coinmetrics":
                        ref_source, ref = "bitstamp", _bitstamp_closes(exchange, window)
                    else:
                        ref_source, ref = "coinmetrics", _coinmetrics_closes(cm, coin, window)
                    ref_date, ref_price = None, None
                    if not ref.empty:
                        ref_date = ref.idxmin() if kind == "bottom" else ref.idxmax()
                        ref_price = float(ref[ref_date])
                    on_date = ref.get(anchor.date)
                    checks.append(
                        AnchorCheck(coin, cycle.name, kind, anchor.date, anchor.price, source,
                                    ref_source, ref_date, ref_price,
                                    None if on_date is None else float(on_date))
                    )  # fmt: skip
    return checks
