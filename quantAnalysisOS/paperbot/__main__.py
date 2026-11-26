"""python3 -m paperbot <command> [--book DIR] [--fixtures DIR] [--now ISO]

    run      advance both tracks once: fills, contributions, settlements, new paper orders
    status   print the current state and evidence
    verify   check the ledger's hash chain and the registration's hash
    halt     stop all new paper orders and rebalances (marks and settlements continue)
    resume   lift a halt; needs --by and --reason

Paper only. There is no broker client in this package.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from . import core_index, evidence, kalshi_maker
from .ledger import Ledger, canonical, now_iso, read_json, sha256, write_json_atomic
from .sources import Fixture, Live, SourceError

HERE = Path(__file__).resolve().parent
REGISTRATION = HERE / "registration.json"


def registration() -> Dict[str, Any]:
    with open(REGISTRATION) as handle:
        reg = json.load(handle)
    reg["_hash"] = sha256(canonical(reg))
    return reg


def paths(book: Path) -> Dict[str, Path]:
    return {"state": book / "state.json", "ledger": book / "ledger.jsonl", "halt": book / "HALT", "status": book / "STATUS.md"}


def load_state(book: Path, reg: Dict[str, Any]) -> Dict[str, Any]:
    state = read_json(paths(book)["state"], None)
    if state is None:
        state = {"registration": reg["registration"], "registration_hash": reg["_hash"], "core": {}, "kalshi": {}}
    if state["registration_hash"] != reg["_hash"]:
        raise SystemExit("refused: registration.json changed after this book started. A changed rule is a new registration and a new book.")
    return state


def render_status(state: Dict[str, Any], halted: bool) -> str:
    core, kal = state.get("core", {}), state.get("kalshi", {})
    lines = [f"# Paper book: {state['registration']}", "", f"Updated {state.get('updated', '?')}." + (" **HALTED.**" if halted else ""), ""]
    if core.get("last_date"):
        s, b = core["arms"]["strategy"], core["arms"]["benchmark"]
        price = core["last_price"]
        lines += [
            "## Core: volatility-managed index vs buy-and-hold",
            "",
            "| | Strategy | Benchmark |",
            "| --- | --- | --- |",
            f"| NAV | ${core_index.nav(s, price):,.2f} | ${core_index.nav(b, price):,.2f} |",
            f"| NAV per unit | {core['nav_per_unit']['strategy']:.4f} | {core['nav_per_unit']['benchmark']:.4f} |",
            f"| Contributed | ${s['contributed']:,.2f} | ${b['contributed']:,.2f} |",
            f"| Costs paid | ${s['costs']:,.2f} | ${b['costs']:,.2f} |",
            "",
            f"Last close {core['last_date']} at {price:.2f}. Target weight {core['target_weight']:.3f}. "
            f"E-value {core['e_value']:.4f}: {evidence.verdict(core['e_value'])}.",
            "",
        ]
    else:
        lines += ["## Core", "", "No prices yet.", ""]
    if "log_e" in kal:
        lines += [
            "## Kalshi: favorite-side maker",
            "",
            f"Open paper orders {len(kal.get('orders', {}))}, open positions {len(kal.get('positions', {}))}, "
            f"settled contracts {kal.get('settled_contracts', 0)}, net P&L ${kal.get('pnl_usd', 0.0):,.2f}. "
            f"E-value {kal['e_value']:.4f} over {kal.get('batches', 0)} settlement batches: {evidence.verdict(kal['e_value'])}.",
            "",
        ]
    else:
        lines += ["## Kalshi", "", "No data yet.", ""]
    for name in ("core", "kalshi"):
        err = state.get("errors", {}).get(name)
        if err:
            lines += [f"Last {name} error: {err}", ""]
    return "\n".join(lines)


def cmd_run(args: argparse.Namespace) -> int:
    reg = registration()
    book = Path(args.book)
    p = paths(book)
    state = load_state(book, reg)
    ledger = Ledger(p["ledger"])
    if not ledger.read():
        ledger.append("register", {"registration": reg["registration"], "hash": reg["_hash"]})
    halted = p["halt"].exists()
    now = datetime.fromisoformat(args.now).timestamp() if args.now else datetime.now(timezone.utc).timestamp()
    src = Fixture(Path(args.fixtures)) if args.fixtures else Live()
    state.setdefault("errors", {})
    ok = 0

    spec = reg["tracks"]["core"]
    try:
        out = core_index.step(state["core"], src.daily_closes(spec.get("stooq_symbol", "spy.us")), spec, halted)
        ledger.append("core", out)
        state["errors"].pop("core", None)
        ok += 1
    except SourceError as exc:
        state["errors"]["core"] = str(exc)
        ledger.append("core-blocked", {"error": str(exc)})

    spec = reg["tracks"]["kalshi"]
    try:
        out = kalshi_maker.step(state["kalshi"], src, now, spec, halted)
        ledger.append("kalshi", out)
        state["errors"].pop("kalshi", None)
        ok += 1
    except SourceError as exc:
        state["errors"]["kalshi"] = str(exc)
        ledger.append("kalshi-blocked", {"error": str(exc)})

    state["updated"] = now_iso()
    write_json_atomic(p["state"], state)
    p["status"].write_text(render_status(state, halted) + "\n")
    print(render_status(state, halted))
    return 0 if ok else 2


def cmd_status(args: argparse.Namespace) -> int:
    reg = registration()
    book = Path(args.book)
    state = load_state(book, reg)
    print(render_status(state, paths(book)["halt"].exists()))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    book = Path(args.book)
    good, detail = Ledger(paths(book)["ledger"]).verify()
    reg = registration()
    state = read_json(paths(book)["state"], {})
    reg_ok = not state or state.get("registration_hash") == reg["_hash"]
    print(f"ledger: {detail}")
    print(f"registration: {'matches the book' if reg_ok else 'CHANGED since the book started'} ({reg['_hash'][:12]})")
    return 0 if good and reg_ok else 1


def cmd_halt(args: argparse.Namespace) -> int:
    p = paths(Path(args.book))
    p["halt"].parent.mkdir(parents=True, exist_ok=True)
    p["halt"].write_text(f"halted {now_iso()} by {args.by}: {args.reason}\n")
    Ledger(p["ledger"]).append("halt", {"by": args.by, "reason": args.reason})
    print("halted: no new paper orders or rebalances until resume")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    p = paths(Path(args.book))
    if p["halt"].exists():
        p["halt"].unlink()
    Ledger(p["ledger"]).append("resume", {"by": args.by, "reason": args.reason})
    print("resumed")
    return 0


def main(argv: Any = None) -> int:
    parser = argparse.ArgumentParser(prog="paperbot", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "status", "verify", "halt", "resume"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--book", default=str(HERE.parent / "paperbook"))
        if name == "run":
            cmd.add_argument("--fixtures", default="")
            cmd.add_argument("--now", default="")
        if name in ("halt", "resume"):
            cmd.add_argument("--by", required=True)
            cmd.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    return {"run": cmd_run, "status": cmd_status, "verify": cmd_verify, "halt": cmd_halt, "resume": cmd_resume}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
