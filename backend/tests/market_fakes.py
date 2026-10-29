"""A fake ccxt exchange for market-data tests (no network)."""

import datetime as dt

import ccxt

DAY_MS = 86_400_000


def ms(day: dt.date) -> int:
    return int(dt.datetime(day.year, day.month, day.day, tzinfo=dt.UTC).timestamp() * 1000)


def make_candles(first: dt.date, last: dt.date, base: float = 100.0) -> list[list[float]]:
    out = []
    day, i = first, 0
    while day <= last:
        c = base + i
        out.append([ms(day), c - 0.5, c + 1.0, c - 1.0, c, 10.0 + i])
        day += dt.timedelta(days=1)
        i += 1
    return out


class FakeExchange:
    """Serves candles like Coinbase: `limit` per call, end inclusive, so windows overlap."""

    def __init__(self, candles: list[list[float]], fail_first: int = 0) -> None:
        self.candles = candles
        self.calls: list[int] = []
        self.fail_first = fail_first

    def fetch_ohlcv(self, symbol: str, timeframe: str, since: int, limit: int) -> list[list[float]]:
        assert timeframe == "1d"
        self.calls.append(since)
        if self.fail_first > 0:
            self.fail_first -= 1
            raise ccxt.NetworkError("simulated timeout")
        end = since + limit * DAY_MS
        return [c for c in self.candles if since <= c[0] <= end]
