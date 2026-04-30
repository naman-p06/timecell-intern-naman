"""
Timecell AI — Task 01: Portfolio Risk Calculator
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal


# ──────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────

@dataclass
class Asset:
    name: str
    allocation_pct: float
    expected_crash_pct: float  # negative number, e.g. -80 means -80%

    @property
    def value_inr(self) -> float:
        return self._total_value * (self.allocation_pct / 100)

    def set_total(self, total: float) -> None:
        self._total_value = total

    def crash_loss_magnitude(self) -> float:
        """allocation_pct × |crash_pct| — used to rank risk contribution."""
        return self.allocation_pct * abs(self.expected_crash_pct)

    def post_crash_value(self, crash_multiplier: float = 1.0) -> float:
        """
        crash_multiplier = 1.0 → full (severe) crash scenario
        crash_multiplier = 0.5 → moderate crash (50% of expected crash)
        """
        effective_crash = self.expected_crash_pct * crash_multiplier
        return self.value_inr * (1 + effective_crash / 100)


@dataclass
class Portfolio:
    total_value_inr: float
    monthly_expenses_inr: float
    assets: list[Asset] = field(default_factory=list)

    def __post_init__(self) -> None:
        for asset in self.assets:
            asset.set_total(self.total_value_inr)
        self._validate()

    def _validate(self) -> None:
        total_alloc = sum(a.allocation_pct for a in self.assets)
        if abs(total_alloc - 100) > 0.01:
            raise ValueError(
                f"Allocations must sum to 100%. Got {total_alloc:.2f}%"
            )
        if self.total_value_inr <= 0:
            raise ValueError("Portfolio value must be positive.")
        if self.monthly_expenses_inr < 0:
            raise ValueError("Monthly expenses cannot be negative.")


# ──────────────────────────────────────────────
# Core risk computation
# ──────────────────────────────────────────────

def compute_risk_metrics(
    portfolio_dict: dict,
    crash_multiplier: float = 1.0,
) -> dict:
    """
    Compute risk metrics for a given portfolio under a crash scenario.

    Args:
        portfolio_dict: Raw portfolio dictionary (matches spec format).
        crash_multiplier: 1.0 = severe crash, 0.5 = moderate crash.

    Returns:
        Dictionary of computed risk metrics.
    """
    assets = [
        Asset(
            name=a["name"],
            allocation_pct=a["allocation_pct"],
            expected_crash_pct=a["expected_crash_pct"],
        )
        for a in portfolio_dict["assets"]
    ]

    portfolio = Portfolio(
        total_value_inr=portfolio_dict["total_value_inr"],
        monthly_expenses_inr=portfolio_dict["monthly_expenses_inr"],
        assets=assets,
    )

    # ── Core metrics ──────────────────────────

    post_crash_value = sum(
        a.post_crash_value(crash_multiplier) for a in portfolio.assets
    )

    monthly_expenses = portfolio.monthly_expenses_inr
    if monthly_expenses == 0:
        runway_months = float("inf")
    else:
        runway_months = post_crash_value / monthly_expenses

    ruin_test: Literal["PASS", "FAIL"] = (
        "PASS" if runway_months > 12 else "FAIL"
    )

    largest_risk_asset = max(
        portfolio.assets, key=lambda a: a.crash_loss_magnitude()
    ).name

    concentration_warning = any(
        a.allocation_pct > 40 for a in portfolio.assets
    )

    # ── Per-asset breakdown (useful for display) ──
    asset_breakdown = [
        {
            "name": a.name,
            "allocation_pct": a.allocation_pct,
            "value_before_inr": round(a.value_inr, 2),
            "value_after_inr": round(a.post_crash_value(crash_multiplier), 2),
            "loss_inr": round(
                a.value_inr - a.post_crash_value(crash_multiplier), 2
            ),
            "risk_score": round(a.crash_loss_magnitude(), 2),
        }
        for a in portfolio.assets
    ]

    return {
        "scenario": "severe" if crash_multiplier == 1.0 else "moderate",
        "crash_multiplier": crash_multiplier,
        "post_crash_value": round(post_crash_value, 2),
        "runway_months": round(runway_months, 2),
        "ruin_test": ruin_test,
        "largest_risk_asset": largest_risk_asset,
        "concentration_warning": concentration_warning,
        "asset_breakdown": asset_breakdown,
    }


def compute_both_scenarios(portfolio_dict: dict) -> dict:
    """Returns metrics for both severe and moderate crash scenarios."""
    return {
        "severe": compute_risk_metrics(portfolio_dict, crash_multiplier=1.0),
        "moderate": compute_risk_metrics(portfolio_dict, crash_multiplier=0.5),
    }


# ──────────────────────────────────────────────
# CLI display helpers (no external libraries)
# ──────────────────────────────────────────────

BAR_WIDTH = 40  # characters

COLOURS = {
    "red":    "\033[91m",
    "yellow": "\033[93m",
    "green":  "\033[92m",
    "cyan":   "\033[96m",
    "bold":   "\033[1m",
    "reset":  "\033[0m",
}


def _colour(text: str, colour: str) -> str:
    return f"{COLOURS.get(colour, '')}{text}{COLOURS['reset']}"


def _fmt_inr(value: float) -> str:
    """Format a number in Indian style (lakhs/crores)."""
    if value >= 1_00_00_000:
        return f"₹{value / 1_00_00_000:.2f} Cr"
    if value >= 1_00_000:
        return f"₹{value / 1_00_000:.2f} L"
    return f"₹{value:,.0f}"


def render_allocation_bar_chart(portfolio_dict: dict) -> None:
    """Render a simple ASCII bar chart of asset allocations."""
    assets = portfolio_dict["assets"]
    print(_colour("\n  PORTFOLIO ALLOCATION", "bold"))
    print("  " + "─" * (BAR_WIDTH + 20))
    for asset in sorted(assets, key=lambda a: a["allocation_pct"], reverse=True):
        pct = asset["allocation_pct"]
        filled = int(BAR_WIDTH * pct / 100)
        bar = "█" * filled + "░" * (BAR_WIDTH - filled)
        colour = "red" if pct > 40 else "yellow" if pct > 25 else "green"
        label = f"{asset['name']:<10}"
        print(f"  {label} {_colour(bar, colour)} {pct:5.1f}%")
    print("  " + "─" * (BAR_WIDTH + 20))


def render_scenario_table(metrics: dict) -> None:
    """Print a formatted summary for one crash scenario."""
    scenario_label = metrics["scenario"].upper()
    crash_pct = int(metrics["crash_multiplier"] * 100)

    tag = _colour(f"[{scenario_label} CRASH — {crash_pct}% of expected]", "cyan")
    print(f"\n  {tag}")
    print("  " + "─" * 52)

    pcv = _fmt_inr(metrics["post_crash_value"])
    print(f"  {'Post-crash portfolio value':<30} {_colour(pcv, 'bold')}")

    runway = metrics["runway_months"]
    runway_str = f"{runway:.1f} months" if runway != float("inf") else "∞"
    runway_colour = "green" if runway > 24 else "yellow" if runway > 12 else "red"
    print(f"  {'Runway':<30} {_colour(runway_str, runway_colour)}")

    ruin = metrics["ruin_test"]
    ruin_colour = "green" if ruin == "PASS" else "red"
    print(f"  {'Ruin test (>12 months)':<30} {_colour(ruin, ruin_colour)}")

    print(f"  {'Largest risk contributor':<30} {metrics['largest_risk_asset']}")

    warn = metrics["concentration_warning"]
    warn_str = "⚠ YES — rebalancing advised" if warn else "✓ NO"
    warn_colour = "red" if warn else "green"
    print(f"  {'Concentration warning (>40%)':<30} {_colour(warn_str, warn_colour)}")

    print("\n  Per-asset crash impact:")
    print(f"  {'Asset':<10} {'Before':>12} {'After':>12} {'Loss':>12}  Risk Score")
    print("  " + "─" * 62)
    for a in metrics["asset_breakdown"]:
        loss_str = f"-{_fmt_inr(a['loss_inr'])}" if a["loss_inr"] > 0 else _fmt_inr(0)
        print(
            f"  {a['name']:<10} "
            f"{_fmt_inr(a['value_before_inr']):>12} "
            f"{_fmt_inr(a['value_after_inr']):>12} "
            f"{loss_str:>12}  "
            f"{a['risk_score']:.1f}"
        )


def render_side_by_side(both: dict) -> None:
    """Render severe vs moderate scenarios in a comparison layout."""
    severe = both["severe"]
    moderate = both["moderate"]

    print(_colour("\n  ┌─────────────────────────────────────────────┐", "cyan"))
    print(_colour("  │     TIMECELL — PORTFOLIO RISK DASHBOARD      │", "cyan"))
    print(_colour("  └─────────────────────────────────────────────┘", "cyan"))

    render_scenario_table(severe)
    render_scenario_table(moderate)

    # Quick comparison line
    delta = severe["post_crash_value"] - moderate["post_crash_value"]
    print(
        f"\n  Severe vs Moderate crash difference: "
        f"{_colour(_fmt_inr(delta), 'yellow')} additional loss in severe scenario."
    )


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

SAMPLE_PORTFOLIO = {
    "total_value_inr": 10_000_000,
    "monthly_expenses_inr": 80_000,
    "assets": [
        {"name": "BTC",     "allocation_pct": 30, "expected_crash_pct": -80},
        {"name": "NIFTY50", "allocation_pct": 40, "expected_crash_pct": -40},
        {"name": "GOLD",    "allocation_pct": 20, "expected_crash_pct": -15},
        {"name": "CASH",    "allocation_pct": 10, "expected_crash_pct":   0},
    ],
}


if __name__ == "__main__":
    render_allocation_bar_chart(SAMPLE_PORTFOLIO)
    both_scenarios = compute_both_scenarios(SAMPLE_PORTFOLIO)
    render_side_by_side(both_scenarios)
    print()