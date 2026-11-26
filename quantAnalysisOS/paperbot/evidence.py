"""Anytime-valid evidence: test supermartingales and Ville's inequality.

Under the null (no edge), each factor has conditional expectation at most 1,
so the running product E_t is a nonnegative supermartingale and
P(sup_t E_t >= 1/alpha) <= alpha. The account may be checked at any time.
"""

from __future__ import annotations

import math
from typing import Iterable, List, Tuple


def batch_factor(bets: Iterable[Tuple[float, float]], lam: float) -> float:
    """One factor for a batch of bets settled together.

    Each bet is (payoff per contract Y in {0, 1}, effective price q_eff in (0, 1]).
    The mean of (1 + lam * (Y / q_eff - 1)) has expectation <= 1 under the null
    whatever the dependence between the bets, which is why bets settled together
    are averaged rather than multiplied.
    """
    terms: List[float] = []
    for payoff, q_eff in bets:
        if not (0.0 < q_eff <= 1.0):
            raise ValueError(f"effective price must be in (0, 1], got {q_eff}")
        terms.append(1.0 + lam * (payoff / q_eff - 1.0))
    if not terms:
        return 1.0
    return sum(terms) / len(terms)


def update(log_e: float, factor: float) -> float:
    if factor <= 0.0:
        raise ValueError("factor must stay positive; lambda must be below 1")
    return log_e + math.log(factor)


def ratio_e(strategy_nav_per_unit: float, benchmark_nav_per_unit: float) -> float:
    """E for an equity strategy: NAV per unit relative to the benchmark's."""
    return strategy_nav_per_unit / benchmark_nav_per_unit


def verdict(e_value: float, pass_at: float = 20.0) -> str:
    if e_value >= pass_at:
        return "evidence threshold reached"
    if e_value <= 1.0 / pass_at:
        return "strong evidence against the strategy"
    return "accumulating"
