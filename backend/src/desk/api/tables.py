"""The Data tab's table allowlist (D37). Only tables listed here can be browsed or exported.

Visibility:
- `member`: every signed-in user sees all rows.
- `own`: members see only their own rows (`owner` column); admins see all.
- `admin`: admins only. MCO-derived tables are here (Decision 6: no MCO in member exports),
  and are hidden for everyone when MCO is switched off.
"""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Column, Table

from desk.config import get_settings
from desk.models import Base

Visibility = Literal["member", "own", "admin"]


@dataclass(frozen=True)
class TableSpec:
    name: str
    description: str
    visibility: Visibility
    fresh: str | None = None  # column whose max() shows freshness
    owner: str | None = None  # for `own`
    hidden: tuple[str, ...] = ()  # never returned
    mco: bool = False

    @property
    def table(self) -> Table:
        return Base.metadata.tables[self.name]

    def columns(self) -> list[Column]:
        return [c for c in self.table.columns if c.name not in self.hidden]

    def visible_to(self, is_admin: bool) -> bool:
        if self.mco and not get_settings().mco_enabled:
            return False
        return is_admin or self.visibility != "admin"


TABLES: dict[str, TableSpec] = {
    t.name: t
    for t in [
        TableSpec("coins", "Coins tracked by the desk (core and watchlist)", "member", "added_at"),
        TableSpec("candles_daily", "Closed daily candles (Coinbase; BTC backfill from Coin "
                  "Metrics is close-only)", "member", "date"),
        TableSpec("candles_4h", "4H candles resampled from Coinbase 1h", "member", "ts"),
        TableSpec("series", "Daily series: Fear & Greed, FRED, Coin Metrics, dominance",
                  "member", "date"),
        TableSpec("news", "RSS headlines (untrusted text)", "member", "published_at"),
        TableSpec("calendar_events", "Macro calendar (FOMC, CPI)", "member", "date"),
        TableSpec("signals", "Weekly signals (append-only, hash-chained)", "member",
                  "created_at"),
        TableSpec("signal_outcomes", "Resolved signal outcomes", "member", "resolved_at"),
        TableSpec("briefs", "Weekly briefs", "member", "created_at"),
        TableSpec("conversations", "Your agent conversations", "own", "created_at", "user_id"),
        TableSpec("messages", "Your agent messages", "own", "created_at", "user_id"),
        TableSpec("agent_snapshots", "Exact data behind each agent tool call", "own",
                  "created_at", "user_id"),
        TableSpec("users", "Users and roles", "admin", "created_at"),
        TableSpec("job_runs", "Scheduled job runs", "admin", "started_at"),
        TableSpec("llm_spend", "Server-key LLM spend", "admin", "created_at"),
        TableSpec("analytics_cache", "Stored analytics results", "admin", "computed_at"),
        TableSpec("mco_videos", "MCO videos (private)", "admin", "published_at", mco=True),
        TableSpec("mco_extracts", "MCO extracts (private)", "admin", "created_at", mco=True),
        TableSpec("mco_wave_labels", "MCO wave labels (private, all statuses)", "admin",
                  mco=True),
        TableSpec("external_views", "External analyst views", "admin", "created_at", mco=True),
    ]
}  # fmt: skip
