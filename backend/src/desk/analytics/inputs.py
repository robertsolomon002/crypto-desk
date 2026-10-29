"""The data an analytics run needs, and loading it from the database (the only DB-aware part
of `desk.analytics` besides `cache`)."""

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass, field

import pandas as pd
from sqlalchemy.orm import Session

from desk.analytics.cycles import CyclesConfig, load_config


@dataclass(frozen=True)
class Inputs:
    daily: dict[str, pd.DataFrame]  # coin -> market.load_daily frame
    onchain: dict[str, pd.DataFrame] = field(default_factory=dict)  # coin -> load_onchain frame
    cycles: CyclesConfig = field(default_factory=load_config)


def load_inputs(session: Session, coins: Iterable[str], as_of: dt.date | None = None) -> Inputs:
    """Daily candles for `coins` and on-chain metrics where Coin Metrics has them."""
    from desk.data import coinmetrics, market

    coins = [c.upper() for c in coins]
    daily = {c: market.load_daily(session, c, as_of) for c in coins}
    onchain = {
        c: coinmetrics.load_onchain(session, c, as_of) for c in coins if c in coinmetrics.ASSETS
    }
    return Inputs(daily, onchain)
