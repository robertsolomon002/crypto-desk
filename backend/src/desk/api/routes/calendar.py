"""`/api/calendar` routes: macro events (FOMC, CPI) from `config/calendar.yaml`."""

import datetime as dt
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from desk.api.deps import AsOfDep, SessionDep, require_role
from desk.api.schemas import Envelope, Source
from desk.data import calendar

router = APIRouter(tags=["calendar"], dependencies=[Depends(require_role("member"))])


class Event(BaseModel):
    date: dt.date
    time_utc: dt.time | None
    kind: str
    title: str
    source_url: str | None


@router.get("/calendar", response_model=Envelope[list[Event]], operation_id="listCalendar")
def list_calendar(
    session: SessionDep,
    as_of: AsOfDep,
    days_ahead: Annotated[int, Query(ge=0, le=400)] = 7,
    days_behind: Annotated[int, Query(ge=0, le=400)] = 0,
    kind: Annotated[list[Literal["fomc", "cpi"]] | None, Query()] = None,
) -> Envelope[list[Event]]:
    """Scheduled events from `as_of - days_behind` to `as_of + days_ahead` (default today)."""
    day = as_of or dt.datetime.now(dt.UTC).date()
    rows = calendar.load_events(session, day, days_ahead, days_behind, kind)
    src = Source(name="calendar.yaml", detail="Federal Reserve and BLS schedules")
    return Envelope(as_of=day, sources=[src], data=[Event(**e) for e in rows])
