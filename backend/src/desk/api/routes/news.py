"""`/api/news` routes. Headlines are untrusted text: the UI renders them as text only."""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from desk.api.common import get_coin
from desk.api.deps import AsOfDep, SessionDep, require_role
from desk.api.schemas import Envelope, Source
from desk.data import news

router = APIRouter(tags=["news"], dependencies=[Depends(require_role("member"))])


class Headline(BaseModel):
    source: str
    title: str
    url: str
    published_at: dt.datetime
    coins: list[str]


@router.get("/news", response_model=Envelope[list[Headline]], operation_id="listNews")
def list_news(
    session: SessionDep,
    as_of: AsOfDep,
    coin: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Envelope[list[Headline]]:
    """Newest headlines published by the end of `as_of` (UTC), optionally tagged with a coin."""
    symbol = get_coin(session, coin).symbol if coin else None
    items = [Headline(**n) for n in news.load_news(session, as_of, symbol, limit)]
    feeds = sorted({n.source for n in items})
    sources = [Source(name=f, detail="rss") for f in feeds] or [Source(name="rss")]
    last = items[0].published_at.date() if items else None
    return Envelope(as_of=as_of or last, sources=sources, data=items)
