"""Spend guard for the Stage 0.3 LLM probe (hard cap, USD).

Prices are USD per million tokens, checked on 2026-10-28 against the official pricing pages
(recorded in docs/DATA_SOURCES.md). Gemini runs on the free tier, so its paid-tier price is
tracked as "paid-equivalent" only and never counts against the cap.
"""

from __future__ import annotations

from dataclasses import dataclass, field

PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50),  # prompts <= 100K tokens
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "anthropic/claude-haiku-5.5": (0.10, 0.50),  # OpenRouter
    "gemini-3.8-flash": (0.75, 3.75),  # paid tier through 2026-12-31; free tier used
    "gemini-3.6-flash": (0.75, 3.75),
    "gemini-3.5-flash-lite": (0.30, 2.50),
}
FREE_TIER = {"gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"}


class SpendCapError(RuntimeError):
    pass


def cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = PRICES[model]
    return (input_tokens * pin + output_tokens * pout) / 1_000_000


@dataclass
class CostGuard:
    cap_usd: float
    spent_usd: float = 0.0
    paid_equivalent_usd: float = 0.0
    lines: list[str] = field(default_factory=list)

    def check(self, model: str, max_input_tokens: int, max_output_tokens: int) -> float:
        """Raise before a call whose worst case would push spend over the cap."""
        if model in FREE_TIER:
            return 0.0
        worst = cost(model, max_input_tokens, max_output_tokens)
        if self.spent_usd + worst > self.cap_usd:
            raise SpendCapError(
                f"{model}: worst case ${worst:.4f} would exceed cap "
                f"(spent ${self.spent_usd:.4f} of ${self.cap_usd:.2f})"
            )
        return worst

    def charge(self, model: str, input_tokens: int, output_tokens: int) -> float:
        c = cost(model, input_tokens, output_tokens)
        if model in FREE_TIER:
            self.paid_equivalent_usd += c
        else:
            self.spent_usd += c
        self.lines.append(f"{model}: in={input_tokens} out={output_tokens} ${c:.5f}")
        return c
