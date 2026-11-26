"""Track `core`: volatility-managed index exposure against buy-and-hold.

Both arms receive the same $100 a week and the same fills and costs. Returns
are measured per unit, like a fund, so contributions never count as
performance. The e-value is the strategy's NAV per unit over the benchmark's.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Dict, List, Optional


def iso_week(day: str) -> str:
    year, week, _ = date.fromisoformat(day).isocalendar()
    return f"{year}-W{week:02d}"


def weeks_between(last_week: Optional[str], day: str) -> int:
    """Contributions owed: one per ISO week from the week after `last_week` through `day`'s week."""
    if last_week is None:
        return 1
    y0, w0 = (int(x) for x in last_week.split("-W"))
    start = date.fromisocalendar(y0, w0, 1)
    current = date.fromisoformat(day)
    end = date.fromisocalendar(*current.isocalendar()[:2], 1)
    return max(0, (end - start).days // 7)


def realized_var_annual(closes: List[float], window: int) -> Optional[float]:
    if len(closes) < window + 1:
        return None
    tail = closes[-(window + 1):]
    rets = [math.log(b / a) for a, b in zip(tail[:-1], tail[1:])]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return var * 252.0


def target_weight(closes: List[float], spec: Dict[str, Any]) -> float:
    var = realized_var_annual(closes, int(spec["variance_window_days"]))
    if var is None or var <= 0.0:
        return 1.0
    return min(1.0, float(spec["vol_target_annual"]) ** 2 / var)


def new_arm() -> Dict[str, Any]:
    return {"cash": 0.0, "shares": 0.0, "units": 0.0, "pending_weight": None, "pending_since": None, "costs": 0.0, "contributed": 0.0}


def nav(arm: Dict[str, Any], price: float) -> float:
    return arm["cash"] + arm["shares"] * price


def nav_per_unit(arm: Dict[str, Any], price: float) -> float:
    return nav(arm, price) / arm["units"] if arm["units"] > 0 else 1.0


def weight(arm: Dict[str, Any], price: float) -> float:
    total = nav(arm, price)
    return arm["shares"] * price / total if total > 0 else 0.0


def fill(arm: Dict[str, Any], price: float, bps: float) -> Optional[Dict[str, Any]]:
    w = arm["pending_weight"]
    if w is None:
        return None
    total = nav(arm, price)
    c, s = bps * 1e-4, arm["shares"]
    # Size so that, after paying the cost, the position is exactly w of what is left:
    # no hidden borrowing to pay commissions.
    want = w * (total + s * price * c) / (price * (1.0 + w * c))
    if want < s:
        want = w * (total - s * price * c) / (price * (1.0 - w * c))
    trade = want - s
    cost = abs(trade) * price * c
    arm["shares"] = want
    arm["cash"] -= trade * price + cost
    arm["costs"] += cost
    arm["pending_weight"] = None
    arm["pending_since"] = None
    return {"shares": trade, "price": price, "cost": cost}


def contribute(arm: Dict[str, Any], amount: float, price: float) -> None:
    per_unit = nav_per_unit(arm, price)
    arm["units"] += amount / per_unit
    arm["cash"] += amount
    arm["contributed"] += amount


def step(state: Dict[str, Any], closes: List[Dict[str, Any]], spec: Dict[str, Any], halted: bool) -> Dict[str, Any]:
    """Advance the track to the latest close. Returns the events of this step."""
    if not closes:
        return {"events": [], "note": "no prices"}
    closes = sorted(closes, key=lambda r: r["date"])
    last = closes[-1]
    day, price = last["date"], float(last["close"])
    events: List[Dict[str, Any]] = []
    arms = state.setdefault("arms", {"strategy": new_arm(), "benchmark": new_arm()})
    bps = float(spec["cost_bps_per_side"])

    if state.get("last_date") == day:
        return {"events": [], "note": f"no new close since {day}"}

    # 1. Orders decided on an earlier close fill at this, the next close we see.
    for name, arm in arms.items():
        if arm["pending_weight"] is not None and arm["pending_since"] is not None and arm["pending_since"] < day:
            done = fill(arm, price, bps)
            if done:
                events.append({"arm": name, "fill": done, "date": day})

    # 2. Contributions: one per ISO week, priced at this close.
    owed = weeks_between(state.get("last_contribution_week"), day)
    if owed:
        amount = owed * float(spec["contribution_usd_per_week"])
        for name, arm in arms.items():
            contribute(arm, amount, price)
        state["last_contribution_week"] = iso_week(day)
        events.append({"contribution": amount, "weeks": owed, "date": day})

    # 3. Decide the next target on data through this close.
    history = [float(r["close"]) for r in closes]
    targets = {"strategy": target_weight(history, spec), "benchmark": 1.0}
    if not halted:
        for name, arm in arms.items():
            drift = abs(weight(arm, price) - targets[name])
            if drift > float(spec["rebalance_band"]) or (arm["shares"] == 0.0 and arm["cash"] > 0):
                arm["pending_weight"] = targets[name]
                arm["pending_since"] = day
                events.append({"arm": name, "order_weight": round(targets[name], 6), "decided": day})

    state["last_date"] = day
    state["last_price"] = price
    s, b = arms["strategy"], arms["benchmark"]
    state["nav_per_unit"] = {"strategy": nav_per_unit(s, price), "benchmark": nav_per_unit(b, price)}
    state["e_value"] = state["nav_per_unit"]["strategy"] / state["nav_per_unit"]["benchmark"]
    state["target_weight"] = targets["strategy"]
    return {"events": events, "date": day, "price": price}
