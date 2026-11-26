"""Where the bot reads the world. Live HTTP, or a fixture directory for tests.

Every fetch is stamped with the time we saw it (knowledge time). Nothing here
authenticates, and nothing here can send an order.

FRED's CSV endpoint and Kalshi's public market-data endpoints need no key. Its field names have moved
from integer cents (`yes_bid`) toward dollar strings (`yes_bid_dollars`); both
are read, and a market missing both is skipped rather than guessed.
"""

from __future__ import annotations

import csv
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv"
USER_AGENT = "paperbot/0.1 (research, paper only)"


class SourceError(Exception):
    pass


def _get(url: str, timeout: float = 30.0, retries: int = 8) -> bytes:
    """GET with backoff on rate limits (HTTP 429) and brief server errors."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    last: Exception = SourceError("no attempt made")
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (429, 500, 502, 503, 504):
                time.sleep(min(30.0, 1.5 * (attempt + 1)))
                continue
            break
        except Exception as exc:  # network policy, DNS, resets: all become one refusal
            last = exc
            break
    raise SourceError(f"could not fetch {url.split('?')[0]}: {last}") from last


def cents(obj: Dict[str, Any], key: str) -> Optional[float]:
    """Price in cents from either `key` (int cents) or `key_dollars` (string dollars)."""
    dollars = obj.get(f"{key}_dollars")
    if dollars not in (None, ""):
        return round(float(dollars) * 100.0, 4)
    value = obj.get(key)
    if value in (None, ""):
        return None
    return float(value)


class Live:
    """The real world, read-only."""

    def __init__(self, pause: float = 0.12) -> None:
        self.pause = pause

    def daily_closes(self, series: str) -> List[Dict[str, Any]]:
        """Daily closes from FRED's public CSV (no key). Missing days ('.' or blank) are dropped."""
        url = FRED + "?" + urllib.parse.urlencode({"id": series})
        text = _get(url).decode("utf-8", "replace")
        rows = list(csv.reader(io.StringIO(text)))
        if len(rows) < 2 or len(rows[0]) < 2 or rows[0][1].strip() != series:
            raise SourceError(f"FRED returned no table for {series}")
        out = []
        for row in rows[1:]:
            if len(row) >= 2 and row[1].strip() not in ("", "."):
                out.append({"date": row[0].strip(), "close": float(row[1])})
        return out

    def open_markets(self, min_close_ts: int = 0, max_close_ts: int = 0, max_pages: int = 200) -> List[Dict[str, Any]]:
        """Every open single (non-combo) market closing inside the window. Raises if the scan is incomplete."""
        markets: List[Dict[str, Any]] = []
        cursor = ""
        for _ in range(max_pages):
            params: Dict[str, Any] = {"status": "open", "limit": 1000, "mve_filter": "exclude"}
            if min_close_ts:
                params["min_close_ts"] = int(min_close_ts)
            if max_close_ts:
                params["max_close_ts"] = int(max_close_ts)
            if cursor:
                params["cursor"] = cursor
            data = json.loads(_get(f"{KALSHI}/markets?" + urllib.parse.urlencode(params)))
            markets.extend(data.get("markets", []))
            cursor = data.get("cursor") or ""
            if not cursor:
                return markets
            time.sleep(self.pause)
        raise SourceError(f"market scan incomplete after {max_pages} pages; selection would depend on API order")

    def market(self, ticker: str) -> Dict[str, Any]:
        time.sleep(self.pause)
        return json.loads(_get(f"{KALSHI}/markets/{urllib.parse.quote(ticker)}")).get("market", {})

    def trades(self, ticker: str, min_ts: int) -> List[Dict[str, Any]]:
        time.sleep(self.pause)
        params = {"ticker": ticker, "min_ts": int(min_ts), "limit": 1000}
        return json.loads(_get(f"{KALSHI}/markets/trades?" + urllib.parse.urlencode(params))).get("trades", [])


class Fixture:
    """A recorded world, for tests and dry runs. Layout:

    closes_<series>.json   [{"date": "YYYY-MM-DD", "close": float}, ...]
    markets.json           [market, ...]              (open markets)
    market_<ticker>.json   market                     (single-market lookups)
    trades_<ticker>.json   [trade, ...]
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _load(self, name: str, default: Any) -> Any:
        path = self.root / name
        if not path.exists():
            return default
        with open(path) as handle:
            return json.load(handle)

    def daily_closes(self, series: str) -> List[Dict[str, Any]]:
        rows = self._load(f"closes_{series}.json", None)
        if rows is None:
            raise SourceError(f"fixture has no closes for {series}")
        return rows

    def open_markets(self, min_close_ts: int = 0, max_close_ts: int = 0, max_pages: int = 200) -> List[Dict[str, Any]]:
        return self._load("markets.json", [])

    def market(self, ticker: str) -> Dict[str, Any]:
        return self._load(f"market_{ticker}.json", {})

    def trades(self, ticker: str, min_ts: int) -> List[Dict[str, Any]]:
        return [t for t in self._load(f"trades_{ticker}.json", []) if trade_ts(t) >= min_ts]


def trade_ts(trade: Dict[str, Any]) -> int:
    """Unix seconds of a trade, from `ts` or ISO `created_time`."""
    if trade.get("ts") is not None:
        return int(trade["ts"])
    from datetime import datetime

    created = str(trade.get("created_time", "")).replace("Z", "+00:00")
    return int(datetime.fromisoformat(created).timestamp()) if created else 0
