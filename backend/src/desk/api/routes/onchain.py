"""`/api/onchain` routes (BTC and ETH, from free Coin Metrics community data, D21)."""

import datetime as dt

from fastapi import APIRouter, Depends

from desk.api.common import run_analytics
from desk.api.deps import AsOfDep, SessionDep, require_role
from desk.api.schemas import AnalyticsData, Envelope

router = APIRouter(tags=["onchain"], dependencies=[Depends(require_role("member"))])


@router.get("/onchain/{coin}", response_model=Envelope[AnalyticsData], operation_id="getOnchain")
def get_onchain(
    coin: str, session: SessionDep, as_of: AsOfDep, start: dt.date | None = None
) -> Envelope[AnalyticsData]:
    """MVRV, realized cap and price (derived), NUPL, supply, active addresses, hash rate."""
    return run_analytics(session, "onchain", coin, as_of, start)
