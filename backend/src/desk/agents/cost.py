"""Server-key spend tracking and the $8/month cap (Decision 9, D45).

Every LLM call on Rob's server key goes through here: `check_budget` before a run, `record`
after each model call (one `llm_spend` row). User keys are never recorded, because friends pay
their own provider directly.

- The cap is `budget.server_llm_cap_usd_per_month` in `config/settings.yaml`, per UTC calendar
  month. At or over it, server-key runs are refused (`BudgetExceeded`).
- From `budget.degrade_at_fraction` of the cap, the budget reports `degraded`; chat then moves
  to `server.chat_degraded` at low effort with fewer output tokens (Decision 9, step 1). MCO
  (step 2) and the brief writer (step 3) read the same flag in their own stages.
- A run that starts under the cap may finish slightly over it; the next run is refused.
"""

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from desk.config import load_app_settings, load_models_config
from desk.models import LlmSpend

MTOK = Decimal(1_000_000)
SOURCES = ("chat", "desk", "brief", "mco")


class BudgetExceeded(Exception):
    """The server key's monthly cap is used up."""


class UnknownPrice(KeyError):
    """A server-key model has no price in `config/models.yaml`, so its spend can't be capped."""


@dataclass(frozen=True)
class Budget:
    cap: Decimal
    spent: Decimal
    degrade_at: Decimal

    @property
    def exhausted(self) -> bool:
        return self.spent >= self.cap

    @property
    def degraded(self) -> bool:
        return self.spent >= self.degrade_at

    @property
    def remaining(self) -> Decimal:
        return max(Decimal(0), self.cap - self.spent)


def month_start(today: dt.date | None = None) -> dt.date:
    today = today or dt.datetime.now(dt.UTC).date()
    return today.replace(day=1)


def month_spend(session: Session, today: dt.date | None = None) -> Decimal:
    total = session.scalar(
        select(func.coalesce(func.sum(LlmSpend.cost), 0)).where(LlmSpend.date >= month_start(today))
    )
    return Decimal(total or 0)


def budget(session: Session, today: dt.date | None = None) -> Budget:
    cfg = load_app_settings().get("budget") or {}
    cap = Decimal(str(cfg.get("server_llm_cap_usd_per_month", 8.0)))
    fraction = Decimal(str(cfg.get("degrade_at_fraction", 0.8)))
    return Budget(cap=cap, spent=month_spend(session, today), degrade_at=cap * fraction)


def check_budget(session: Session, today: dt.date | None = None) -> Budget:
    """The current budget; raises `BudgetExceeded` when the cap is used up."""
    b = budget(session, today)
    if b.exhausted:
        raise BudgetExceeded(f"server LLM spend ${b.spent:.2f} has reached the ${b.cap:.2f} cap")
    return b


def call_cost(model: str, tokens_in: int, tokens_out: int) -> Decimal:
    """USD for one call at `config/models.yaml` prices (per million tokens)."""
    prices = (load_models_config().get("prices") or {}).get(model)
    if not prices:
        raise UnknownPrice(model)
    long = prices.get("long_above") is not None and tokens_in > int(prices["long_above"])
    p_in = Decimal(str(prices["long_input" if long else "input"]))
    p_out = Decimal(str(prices["long_output" if long else "output"]))
    cost = (Decimal(tokens_in) * p_in + Decimal(tokens_out) * p_out) / MTOK
    return cost.quantize(Decimal("0.000001"))


def record(
    session: Session,
    source: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    day: dt.date | None = None,
) -> Decimal:
    """Write one `llm_spend` row for a server-key call and commit it. Returns the cost."""
    assert source in SOURCES, source
    cost = call_cost(model, tokens_in, tokens_out)
    session.add(
        LlmSpend(
            date=day or dt.datetime.now(dt.UTC).date(),
            source=source,
            model=model,
            tokens_in=int(tokens_in),
            tokens_out=int(tokens_out),
            cost=cost,
        )
    )
    session.commit()
    return cost
