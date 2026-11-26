"""Track `kalshi`: paper maker bids on the favorite side of Kalshi contracts.

Fills are counted only when a later trade prints strictly through our price,
so we never assume queue priority we would not have had. Fees are charged as
if maker fees applied to every series, rounded up per order. Bets settled in
the same run are averaged into one evidence factor, which keeps the e-value a
valid test supermartingale whatever the dependence between contracts.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import evidence
from .sources import cents, trade_ts


def parse_ts(value: str) -> Optional[float]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def maker_fee_cents(contracts: int, price_cents: float) -> int:
    p = price_cents / 100.0
    return int(math.ceil(round(0.0175 * contracts * p * (1.0 - p) * 100.0, 9)))


def quotes(market: Dict[str, Any]) -> Dict[str, Optional[float]]:
    yes_bid, yes_ask = cents(market, "yes_bid"), cents(market, "yes_ask")
    no_bid, no_ask = cents(market, "no_bid"), cents(market, "no_ask")
    if no_ask is None and yes_bid is not None:
        no_ask = 100.0 - yes_bid
    if no_bid is None and yes_ask is not None:
        no_bid = 100.0 - yes_ask
    return {"yes_bid": yes_bid, "yes_ask": yes_ask, "no_bid": no_bid, "no_ask": no_ask}


def candidate(market: Dict[str, Any], now: float, spec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    elig = spec["eligible"]
    if elig.get("exclude_multivariate_combos") and market.get("mve_collection_ticker"):
        return None
    closes = parse_ts(market.get("close_time", ""))
    if closes is None:
        return None
    days = (closes - now) / 86400.0
    if not (elig["days_to_close_min"] <= days <= elig["days_to_close_max"]):
        return None
    q = quotes(market)
    lo, hi = 100.0 * elig["favorite_ask_min"], 100.0 * elig["favorite_ask_max"]
    for side in ("yes", "no"):
        ask, bid = q[f"{side}_ask"], q[f"{side}_bid"]
        if ask is None or bid is None or bid <= 0:
            continue
        if lo <= ask <= hi:
            if ask - bid > float(elig.get("max_spread_cents", 100)):
                return None
            price = bid + 1.0
            if price >= ask:
                return None
            return {"ticker": market["ticker"], "event": market.get("event_ticker", ""), "side": side,
                    "price_c": price, "ask_c": ask, "bid_c": bid, "close_ts": closes}
    return None


def filled_by(trades: List[Dict[str, Any]], side: str, price_c: float, until_ts: float = float("inf")) -> Optional[Dict[str, Any]]:
    """First trade, before `until_ts`, that printed strictly through our price on our side."""
    for trade in sorted(trades, key=trade_ts):
        if trade_ts(trade) > until_ts:
            break
        printed = cents(trade, f"{side}_price")
        if printed is None:
            other = cents(trade, "no_price" if side == "yes" else "yes_price")
            printed = None if other is None else 100.0 - other
        if printed is not None and printed < price_c:
            return trade
    return None


def step(state: Dict[str, Any], src: Any, now: float, spec: Dict[str, Any], halted: bool) -> Dict[str, Any]:
    orders: Dict[str, Dict[str, Any]] = state.setdefault("orders", {})
    positions: Dict[str, Dict[str, Any]] = state.setdefault("positions", {})
    state.setdefault("log_e", 0.0)
    state.setdefault("pnl_usd", 0.0)
    state.setdefault("settled_contracts", 0)
    state.setdefault("batches", 0)
    rules = spec["order"]
    events: List[Dict[str, Any]] = []

    # 1. Fills and expiries for resting orders. Only trades inside the order's life count,
    #    so the run schedule can never stretch an order beyond its registered lifetime.
    life = 3600.0 * float(rules["expire_hours"])
    for ticker in sorted(list(orders)):
        order = orders[ticker]
        until = order["placed_ts"] + life
        trade = filled_by(src.trades(ticker, int(order["placed_ts"])), order["side"], order["price_c"], until)
        if trade is not None:
            order["filled_ts"] = trade_ts(trade)
            positions[ticker] = order
            del orders[ticker]
            events.append({"fill": ticker, "side": order["side"], "price_c": order["price_c"]})
        elif now > until:
            del orders[ticker]
            events.append({"expire": ticker})

    # 2. Settlement of filled positions, averaged into one evidence factor.
    bets: List[Tuple[float, float]] = []
    for ticker in sorted(list(positions)):
        pos = positions[ticker]
        market = src.market(ticker)
        result = str(market.get("result", "")).lower()
        status = str(market.get("status", "")).lower()
        qty = pos["contracts"]
        if result in ("yes", "no"):
            payoff = 1.0 if result == pos["side"] else 0.0
            q_eff = (pos["price_c"] + pos["fee_c"] / qty) / 100.0
            bets.append((payoff, q_eff))
            pnl = qty * payoff - qty * pos["price_c"] / 100.0 - pos["fee_c"] / 100.0
            state["pnl_usd"] += pnl
            state["settled_contracts"] += qty
            state.setdefault("returns", []).append(pnl / (qty * pos["price_c"] / 100.0 + pos["fee_c"] / 100.0))
            del positions[ticker]
            events.append({"settle": ticker, "result": result, "pnl_usd": round(pnl, 4)})
        elif status in ("settled", "finalized", "voided") or result == "void":
            del positions[ticker]
            events.append({"void": ticker, "status": status})
    if bets:
        factor = evidence.batch_factor(bets, float(spec["lambda"]))
        state["log_e"] = evidence.update(state["log_e"], factor)
        state["batches"] += 1
        events.append({"evidence_factor": round(factor, 6), "bets": len(bets)})

    # 3. New resting bids, earliest-closing first, unless halted.
    placed = 0
    if not halted:
        elig = spec["eligible"]
        held = set(orders) | set(positions)
        held_events = {o.get("event", "") for o in list(orders.values()) + list(positions.values())}
        room = max(0, int(rules["max_open"]) - len(orders) - len(positions))
        window = (int(now + 86400 * elig["days_to_close_min"]), int(now + 86400 * elig["days_to_close_max"]))
        found = [c for c in (candidate(m, now, spec) for m in src.open_markets(*window)) if c and c["ticker"] not in held]
        found.sort(key=lambda c: (c["close_ts"], c["ticker"]))
        picks = []
        for c in found:
            if rules.get("one_order_per_event") and c["event"] and c["event"] in held_events:
                continue
            held_events.add(c["event"])
            picks.append(c)
        for pick in picks[: min(room, int(rules["max_new_per_run"]))]:
            qty = int(rules["contracts"])
            pick.update({"contracts": qty, "fee_c": maker_fee_cents(qty, pick["price_c"]), "placed_ts": now})
            orders[pick["ticker"]] = pick
            placed += 1
        if placed:
            events.append({"placed": placed})

    state["e_value"] = math.exp(state["log_e"])
    return {"events": events, "open_orders": len(orders), "open_positions": len(positions)}
