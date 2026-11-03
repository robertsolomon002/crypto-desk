"""`/api/views` and `/api/admin/views` (Stage 6.2, D50): outside analysts' views on a coin.

Two kinds, merged newest first:
- `mco`: MCO's video extracts (v2 scenarios, D49), read live from `mco_extracts` so they never
  go stale. Only while MCO is switched on (Decision 6); dated by the video's publication.
- `manual`: views Rob adds in Settings (`external_views` rows: source, coin, bias, levels,
  invalidation, link), from any analyst.

`as_of` keeps the look-ahead rule: only views published (MCO) or created (manual) by the end of
that UTC day. The same function backs `get_external_views` in desk-mcp and the Overview's MCO
bias, so the rules are defined once (D44). Everything here is untrusted text for the UI and for
any model that reads it.
"""

import datetime as dt
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, HttpUrl, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from desk.api.common import get_coin
from desk.api.deps import AsOfDep, SessionDep, UserDep, require_role
from desk.api.routes.mco import McoLevel, McoScenario
from desk.api.schemas import Envelope, Source
from desk.mco.schemas import load_payload
from desk.models import ExternalView, McoExtract, McoVideo

Bias = Literal["bullish", "bearish", "neutral"]
MCO_SOURCE = "More Crypto Online"

router = APIRouter(tags=["views"], dependencies=[Depends(require_role("member"))])


class View(BaseModel):
    id: str  # `mco:<video id>` or `manual:<row id>`
    kind: Literal["mco", "manual"]
    source: str
    coin: str
    published_at: dt.datetime
    bias: Bias
    wave_position: str | None
    levels: list[McoLevel]
    invalidation: float | None
    targets: list[float]
    scenarios: list[McoScenario]  # MCO only; empty for manual views
    confidence: Literal["high", "medium", "low"] | None  # extraction confidence (MCO)
    low_detail: bool
    url: str | None


def _end_of(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day + dt.timedelta(days=1), dt.time(), dt.UTC)


def mco_views(session: Session, coin: str | None, as_of: dt.date | None, limit: int) -> list[View]:
    from desk.jobs.mco_daily import enabled

    if not enabled():
        return []
    q = (
        select(McoVideo, McoExtract)
        .join(McoExtract, McoExtract.video_id == McoVideo.video_id)
        .where(McoVideo.status == "done")
        .order_by(McoVideo.published_at.desc(), McoExtract.id.desc())
    )
    if as_of is not None:
        q = q.where(McoVideo.published_at < _end_of(as_of))
    out: list[View] = []
    seen: set[str] = set()
    for v, ex in session.execute(q):
        if v.video_id in seen:  # the newest extract per video
            continue
        seen.add(v.video_id)
        try:
            extract = load_payload(ex.payload or {}, ex.prompt_version)
        except ValueError:
            continue
        for c in extract.coins:
            if coin and c.coin != coin:
                continue
            primary = next((s for s in c.scenarios if s.name == "primary"), None)
            out.append(
                View(
                    id=f"mco:{v.video_id}",
                    kind="mco",
                    source=MCO_SOURCE,
                    coin=c.coin,
                    published_at=v.published_at,
                    bias=c.bias,
                    wave_position=c.wave_position,
                    levels=[McoLevel(**lv.model_dump()) for lv in c.key_levels],
                    invalidation=primary.invalidation if primary else None,
                    targets=primary.targets if primary else [],
                    scenarios=[McoScenario.model_validate(s.model_dump()) for s in c.scenarios],
                    confidence=c.extraction_confidence,
                    low_detail=v.low_detail,
                    url=v.url,
                )
            )
        if len(out) >= limit:
            break
    return out[:limit]


def manual_views(
    session: Session, coin: str | None, as_of: dt.date | None, limit: int
) -> list[View]:
    q = select(ExternalView).where(ExternalView.extract_id.is_(None))
    if coin:
        q = q.where(ExternalView.coin == coin)
    if as_of is not None:
        q = q.where(ExternalView.created_at < _end_of(as_of))
    rows = session.scalars(q.order_by(ExternalView.created_at.desc()).limit(limit))
    return [_manual(r) for r in rows]


def _manual(r: ExternalView) -> View:
    return View(
        id=f"manual:{r.id}",
        kind="manual",
        source=r.source,
        coin=r.coin,
        published_at=r.created_at,
        bias=r.bias,
        wave_position=None,
        levels=[McoLevel(**lv) for lv in (r.levels or [])],
        invalidation=r.invalidation,
        targets=[],
        scenarios=[],
        confidence=None,
        low_detail=False,
        url=r.url,
    )


def list_views(
    session: Session, as_of: dt.date | None, coin: str | None = None, limit: int = 10
) -> Envelope[list[View]]:
    """Newest views first, MCO and manual merged (the route, desk-mcp and the Overview)."""
    symbol = get_coin(session, coin).symbol if coin else None
    views = sorted(
        mco_views(session, symbol, as_of, limit) + manual_views(session, symbol, as_of, limit),
        key=lambda v: v.published_at,
        reverse=True,
    )[:limit]
    sources = sorted({v.source for v in views})
    return Envelope(
        as_of=as_of or (views[0].published_at.date() if views else None),
        sources=[
            Source(
                name=s,
                detail="AI-extracted from public videos" if s == MCO_SOURCE else "manual view",
            )
            for s in sources
        ],
        data=views,
    )


def latest_mco_bias(session: Session, coin: str, as_of: dt.date | None) -> View | None:
    views = mco_views(session, coin, as_of, 1)
    return views[0] if views else None


@router.get("/views", response_model=Envelope[list[View]], operation_id="listViews")
def get_views(
    session: SessionDep,
    as_of: AsOfDep,
    coin: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> Envelope[list[View]]:
    """Outside analysts' views (MCO extracts and Rob's manual views), newest first."""
    return list_views(session, as_of, coin, limit)


# --- Admin: manual views ----------------------------------------------------------------------


class ManualLevel(BaseModel):
    price: float = Field(gt=0)
    label: str = Field(min_length=1, max_length=64)


class ManualViewIn(BaseModel):
    source: str = Field(min_length=1, max_length=64, description="Analyst or channel name")
    coin: str
    bias: Bias
    levels: list[ManualLevel] = Field(default_factory=list, max_length=20)
    invalidation: float | None = Field(default=None, gt=0)
    url: HttpUrl | None = None

    @field_validator("source")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("source must not be blank")
        return v


@router.post(
    "/admin/views",
    response_model=View,
    status_code=201,
    operation_id="addView",
    dependencies=[Depends(require_role("admin"))],
)
def add_view(body: ManualViewIn, session: SessionDep, user: UserDep) -> View:
    """Add a manual view from any analyst (admin). It is visible to members right away."""
    if body.url is not None and body.url.scheme not in ("http", "https"):
        raise HTTPException(422, "url must be http(s)")
    coin = get_coin(session, body.coin).symbol
    row = ExternalView(
        source=body.source,
        coin=coin,
        bias=body.bias,
        levels=[lv.model_dump() for lv in body.levels],
        invalidation=body.invalidation,
        url=str(body.url) if body.url else None,
        created_by=user.id,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _manual(row)


@router.delete(
    "/admin/views/{view_id}",
    status_code=204,
    operation_id="deleteView",
    dependencies=[Depends(require_role("admin"))],
)
def delete_view(view_id: int, session: SessionDep) -> Response:
    """Delete a manual view (admin). MCO views come from extracts and cannot be deleted here."""
    row = session.get(ExternalView, view_id)
    if row is None or row.extract_id is not None:
        raise HTTPException(404, "view not found")
    session.delete(row)
    session.commit()
    return Response(status_code=204)
