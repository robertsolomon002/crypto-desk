"""`/api/mco` routes (Stage 6.1): MCO's extracted views, private by Decision 6.

- Every route needs a login and answers 404 when MCO is switched off (`features.mco` or
  `MCO_ENABLED`).
- Members get the summarized videos with only `approved` and `edited` wave labels
  (Decision 7); the raw `pivot_labels` in each extract are never returned, so pending labels
  cannot leak through the payload.
- `/api/admin/mco/review` (admin) lists videos with labels still `pending`, matched or not.

Everything here is AI-extracted, untrusted text: the UI renders it as text only.
"""

import datetime as dt
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from desk.api.deps import SessionDep, require_role
from desk.api.schemas import Envelope, Source
from desk.models import McoExtract, McoVideo, McoWaveLabel

VISIBLE = ("approved", "edited")
CHANNEL = "https://www.youtube.com/@MoreCryptoOnline"


def mco_on() -> None:
    from desk.jobs.mco_daily import enabled

    if not enabled():
        raise HTTPException(404, "not found")


router = APIRouter(tags=["mco"], dependencies=[Depends(require_role("member")), Depends(mco_on)])


class McoLevel(BaseModel):
    price: float
    label: str


class McoCoinView(BaseModel):
    coin: str
    bias: Literal["bullish", "bearish", "neutral"]
    wave_position: str
    primary_scenario: str
    alternative_scenario: str
    key_levels: list[McoLevel]
    invalidation: float | None
    targets: list[float]
    timeframe: str
    extraction_confidence: Literal["high", "medium", "low"]


class McoLabel(BaseModel):
    id: int
    coin: str
    label: str
    timeframe: str | None
    status: Literal["pending", "approved", "rejected", "edited"]
    pivot_kind: str | None
    approx_date: dt.date | None
    approx_price: float | None
    pivot_date: dt.date | None  # null when unmatched
    pivot_price: float | None


class McoReviewLabel(McoLabel):
    snap_bars: int | None
    snap_pct: float | None
    match_note: str | None


class McoVideoBase(BaseModel):
    video_id: str
    title: str
    url: str
    published_at: dt.datetime
    low_detail: bool
    model: str
    prompt_version: str
    summary: str | None
    checks: list[str]
    coins: list[McoCoinView]


class McoVideoItem(McoVideoBase):
    labels: list[McoLabel]


class McoReviewItem(McoVideoBase):
    labels: list[McoReviewLabel]


def _sources(rows: list) -> list[Source]:
    last = max((v.published_at.date() for v, _ in rows), default=None)
    return [
        Source(
            name="More Crypto Online (YouTube)",
            detail="AI-extracted from public videos",
            url=CHANNEL,
            last_date=last,
        )
    ]


def _latest_extracts(
    session: Session, coin: str | None, limit: int, video_id: str | None = None
) -> list[tuple[McoVideo, McoExtract]]:
    q = (
        select(McoVideo, McoExtract)
        .join(McoExtract, McoExtract.video_id == McoVideo.video_id)
        .where(McoVideo.status == "done")
        .order_by(McoVideo.published_at.desc(), McoExtract.id.desc())
    )
    if video_id:
        q = q.where(McoVideo.video_id == video_id)
    out, seen = [], set()
    for v, ex in session.execute(q):
        if v.video_id in seen:  # newest extract per video
            continue
        coins = [c["coin"] for c in (ex.payload or {}).get("coins", [])]
        if coin and coin.upper() not in coins:
            continue
        seen.add(v.video_id)
        out.append((v, ex))
        if len(out) >= limit:
            break
    return out


def _base(v: McoVideo, ex: McoExtract) -> dict:
    payload = ex.payload or {}
    coins = [
        McoCoinView(**{k: c[k] for k in McoCoinView.model_fields}) for c in payload.get("coins", [])
    ]  # drops pivot_labels
    return dict(
        video_id=v.video_id,
        title=v.title,
        url=v.url,
        published_at=v.published_at,
        low_detail=v.low_detail,
        model=ex.model,
        prompt_version=ex.prompt_version,
        summary=ex.summary,
        checks=list(payload.get("checks", [])),
        coins=coins,
    )


def _labels(session: Session, extract_id: int, statuses: tuple[str, ...]) -> list[McoWaveLabel]:
    return list(
        session.scalars(
            select(McoWaveLabel)
            .where(McoWaveLabel.extract_id == extract_id, McoWaveLabel.status.in_(statuses))
            .order_by(McoWaveLabel.coin, McoWaveLabel.approx_date, McoWaveLabel.id)
        )
    )


def _label(row: McoWaveLabel, model: type[McoLabel]) -> McoLabel:
    return model.model_validate(row, from_attributes=True)


@router.get(
    "/mco/videos", response_model=Envelope[list[McoVideoItem]], operation_id="listMcoVideos"
)
def list_videos(
    session: SessionDep,
    coin: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Envelope[list[McoVideoItem]]:
    """Summarized MCO videos, newest first, with approved wave labels only."""
    rows = _latest_extracts(session, coin, limit)
    items = [
        McoVideoItem(
            **_base(v, ex), labels=[_label(r, McoLabel) for r in _labels(session, ex.id, VISIBLE)]
        )
        for v, ex in rows
    ]
    return Envelope(
        as_of=items[0].published_at.date() if items else None, sources=_sources(rows), data=items
    )


@router.get(
    "/mco/videos/{video_id}", response_model=Envelope[McoVideoItem], operation_id="getMcoVideo"
)
def get_video(video_id: str, session: SessionDep) -> Envelope[McoVideoItem]:
    """One summarized video with approved wave labels only."""
    rows = _latest_extracts(session, None, 1, video_id)
    if not rows:
        raise HTTPException(404, "video not found")
    v, ex = rows[0]
    item = McoVideoItem(
        **_base(v, ex), labels=[_label(r, McoLabel) for r in _labels(session, ex.id, VISIBLE)]
    )
    return Envelope(as_of=v.published_at.date(), sources=_sources(rows), data=item)


@router.get(
    "/admin/mco/review",
    response_model=Envelope[list[McoReviewItem]],
    operation_id="listMcoReview",
    dependencies=[Depends(require_role("admin"))],
)
def list_review(
    session: SessionDep, limit: Annotated[int, Query(ge=1, le=100)] = 50
) -> Envelope[list[McoReviewItem]]:
    """Videos whose wave labels still await Rob's review, newest first (admin)."""
    items, rows = [], []
    for v, ex in _latest_extracts(session, None, 500):
        pending = _labels(session, ex.id, ("pending",))
        if not pending:
            continue
        rows.append((v, ex))
        items.append(
            McoReviewItem(**_base(v, ex), labels=[_label(r, McoReviewLabel) for r in pending])
        )
        if len(items) >= limit:
            break
    return Envelope(
        as_of=items[0].published_at.date() if items else None, sources=_sources(rows), data=items
    )
