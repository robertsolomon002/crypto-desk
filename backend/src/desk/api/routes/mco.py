"""`/api/mco` routes: MCO's extracted views, private by Decision 6 (Stage 6.1, D48, D49).

- Every route needs a login and answers 404 when MCO is switched off (`features.mco` or
  `MCO_ENABLED`).
- Each video gives per coin a primary and an alternative scenario with their own levels,
  targets, invalidation and trigger (extract v2). Extracts stored as v1 are converted.
- No wave labels: Rob dropped chart wave counts (D49, Decision 7 updated), so neither the
  `mco_wave_labels` rows nor any label in a stored payload is ever returned.

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
from desk.mco.schemas import load_payload
from desk.models import McoExtract, McoVideo

CHANNEL = "https://www.youtube.com/@MoreCryptoOnline"
Bias = Literal["bullish", "bearish", "neutral"]


def mco_on() -> None:
    from desk.jobs.mco_daily import enabled

    if not enabled():
        raise HTTPException(404, "not found")


router = APIRouter(tags=["mco"], dependencies=[Depends(require_role("member")), Depends(mco_on)])


class McoLevel(BaseModel):
    price: float
    label: str


class McoScenario(BaseModel):
    name: Literal["primary", "alternative"]
    color: str | None
    bias: Bias
    description: str
    levels: list[McoLevel]
    targets: list[float]
    invalidation: float | None
    trigger: str | None


class McoCoinView(BaseModel):
    coin: str
    bias: Bias  # the primary scenario's
    wave_position: str
    timeframe: str
    key_levels: list[McoLevel]
    scenarios: list[McoScenario]
    extraction_confidence: Literal["high", "medium", "low"]


class McoVideoItem(BaseModel):
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


def _latest(
    session: Session, coin: str | None, limit: int, video_id: str | None = None
) -> list[McoVideoItem]:
    q = (
        select(McoVideo, McoExtract)
        .join(McoExtract, McoExtract.video_id == McoVideo.video_id)
        .where(McoVideo.status == "done")
        .order_by(McoVideo.published_at.desc(), McoExtract.id.desc())
    )
    if video_id:
        q = q.where(McoVideo.video_id == video_id)
    out: list[McoVideoItem] = []
    seen: set[str] = set()
    for v, ex in session.execute(q):
        if v.video_id in seen:  # newest extract per video
            continue
        seen.add(v.video_id)
        try:
            extract = load_payload(ex.payload or {}, ex.prompt_version)
        except ValueError:
            continue
        if coin and coin.upper() not in {c.coin for c in extract.coins}:
            continue
        coins = [McoCoinView.model_validate(c.model_dump()) for c in extract.coins]
        out.append(McoVideoItem(
            video_id=v.video_id, title=v.title, url=v.url, published_at=v.published_at,
            low_detail=v.low_detail, model=ex.model, prompt_version=ex.prompt_version,
            summary=ex.summary, checks=extract.checks, coins=coins,
        ))  # fmt: skip
        if len(out) >= limit:
            break
    return out


def _sources(items: list[McoVideoItem]) -> list[Source]:
    last = max((i.published_at.date() for i in items), default=None)
    return [Source(name="More Crypto Online (YouTube)", detail="AI-extracted from public videos",
                   url=CHANNEL, last_date=last)]  # fmt: skip


@router.get("/mco/videos", response_model=Envelope[list[McoVideoItem]],
            operation_id="listMcoVideos")  # fmt: skip
def list_videos(
    session: SessionDep,
    coin: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Envelope[list[McoVideoItem]]:
    """Summarized MCO videos, newest first, optionally only those that discuss `coin`."""
    items = _latest(session, coin, limit)
    return Envelope(as_of=items[0].published_at.date() if items else None,
                    sources=_sources(items), data=items)  # fmt: skip


@router.get("/mco/videos/{video_id}", response_model=Envelope[McoVideoItem],
            operation_id="getMcoVideo")  # fmt: skip
def get_video(video_id: str, session: SessionDep) -> Envelope[McoVideoItem]:
    """One summarized video."""
    items = _latest(session, None, 1, video_id)
    if not items:
        raise HTTPException(404, "video not found")
    return Envelope(as_of=items[0].published_at.date(), sources=_sources(items), data=items[0])
