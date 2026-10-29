"""On-chain valuation from Coin Metrics community metrics (D21: `CapRealUSD` is not free).

realized cap = market cap / MVRV; realized price = realized cap / supply;
NUPL = (market cap - realized cap) / market cap = 1 - 1 / MVRV.
"""

import datetime as dt

import pandas as pd

from desk.analytics._frames import truncate


def onchain_metrics(onchain: pd.DataFrame, as_of: dt.date | None = None) -> pd.DataFrame:
    """Per day: MVRV, market cap, realized cap and price, NUPL, supply, active addresses, hash
    rate. Days without both market cap and MVRV are dropped."""
    d = truncate(onchain, as_of).dropna(subset=["CapMrktCurUSD", "CapMVRVCur"])
    mvrv = d["CapMVRVCur"]
    realized_cap = d["CapMrktCurUSD"] / mvrv
    return pd.DataFrame(
        {
            "mvrv": mvrv,
            "market_cap": d["CapMrktCurUSD"],
            "realized_cap": realized_cap,
            "realized_price": realized_cap / d["SplyCur"],
            "nupl": 1 - 1 / mvrv,
            "supply": d["SplyCur"],
            "active_addresses": d["AdrActCnt"],
            "hash_rate": d["HashRate"],
        }
    )
