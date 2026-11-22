#!/usr/bin/env python3
"""What happens when assistants pass results to each other?

This is a model, not a measurement. No real assistant took part.

Twelve assistants reuse sixty results. Every result depends on a few files, and
the files keep changing. An assistant that needs a result for the first time
either works it out itself or takes a copy from an assistant that already has
one. Each later time it follows one rule:

  trust      repeat the copy
  timer      rerun when the copy is older than a set number of steps
  standing   compare the fingerprints of the files the copy says it stood on
             and rerun only when one of them changed
  recheck    rerun every time

A copy passed between assistants carries those fingerprints and the time of its
last rerun, so the receiver applies its own rule to what the copy stood on.

For every rule the model counts outdated results, computations and
fingerprint comparisons. Computations include both first runs and refreshes
of copies. Each input independently has a 100, 90, 75, 50, 25 or 0 percent
chance of being declared, because a fingerprint check sees only declared files.

    python3 evals/exchange_simulation.py            print the table
    python3 evals/exchange_simulation.py --write    store the result
    python3 evals/exchange_simulation.py --verify   recompute and compare

Standard library only. Every random draw is an integer from the SplitMix64
generator written out below, so the table can be reproduced in any language.
All rules replay the same sequence of edits and reuses.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RESULT = Path(__file__).resolve().parent / "results" / "exchange_simulation.json"
MASK = (1 << 64) - 1

# Fixed before the first run. Rates are whole numbers so no rounding is hidden.
PARAMETERS = {
    "seed": 20261122,
    "worlds": 40,
    "steps": 240,
    "files": 80,
    "results": 60,
    "assistants": 12,
    "max_inputs": 6,
    "change_per_file_per_step_ppm": 1500,
    "edit_changes_result_percent": 70,
    "use_per_step_percent": 50,
    "secondhand_percent": 50,
    "popularity_power": 2,
    "timer_steps": [5, 10, 20, 40, 80, 160],
    "declared_percent": [100, 90, 75, 50, 25, 0],
}

# Each variation changes one setting and reruns a smaller number of worlds.
VARIATION_WORLDS = 10
VARIATIONS = [
    ("files change half as often", {"change_per_file_per_step_ppm": 750}),
    ("files change twice as often", {"change_per_file_per_step_ppm": 3000}),
    ("no copy is taken from another assistant", {"secondhand_percent": 0}),
    ("a first copy is always taken from another assistant when one exists", {"secondhand_percent": 100}),
    ("every edit changes the result", {"edit_changes_result_percent": 100}),
    ("four edits in ten change the result", {"edit_changes_result_percent": 40}),
    ("every result is reused equally often", {"popularity_power": 1}),
]

# Written before the first run. Each is scored on the main table.
PREDICTIONS = [
    (
        "With every input declared, checking fingerprints first never repeats an outdated result. "
        "This is true by construction: a failure would mean a mistake in the model.",
        lambda get: get("standing", 100)["outdated_uses"] == 0,
    ),
    (
        "With every input declared, checking fingerprints first reruns less than half as often as rerunning every time.",
        lambda get: 2 * get("standing", 100)["reruns"] < get("recheck")["reruns"],
    ),
    (
        "With half the inputs declared, it repeats fewer than half as many outdated results as repeating the copy.",
        lambda get: 2 * get("standing", 50)["outdated_uses"] < get("trust")["outdated_uses"],
    ),
    (
        "With three quarters of the inputs declared, no timer setting does at least as well on both counts.",
        lambda get: not get("standing", 75)["beaten_by_timer"],
    ),
    (
        "With a quarter of the inputs declared, some timer setting does at least as well on both counts.",
        lambda get: bool(get("standing", 25)["beaten_by_timer"]),
    ),
]

DOES_NOT_COVER = [
    "No real assistant took part. The rates of editing and reuse are invented; the variations show how the table moves when they change.",
    "Every rerun is taken to give the right answer, and a fingerprint check is taken to cost far less than a rerun.",
    "A copy is taken to report truthfully what it stood on. A sender that misreports is not modelled.",
    "Edits arrive independently of each other and are never undone.",
    "Each input is declared or left out independently of the others.",
]


class SplitMix64:
    """The SplitMix64 generator (Steele, Lea and Flood, 2014)."""

    def __init__(self, seed: int) -> None:
        self.state = seed & MASK

    def next(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK
        return z ^ (z >> 31)

    def below(self, n: int) -> int:
        """An integer from 0 to n - 1: the high 64 bits of a draw multiplied by n."""
        return (self.next() * n) >> 64


def variants(p: dict) -> list:
    """Every rule and setting, in the order of the table."""
    out = [("trust", 0, "repeat the copy")]
    out += [("timer", n, f"rerun when the copy is older than {n} steps") for n in p["timer_steps"]]
    out += [("standing", c, f"check fingerprints first, {c}% of inputs declared") for c in p["declared_percent"]]
    out.append(("recheck", 0, "rerun every time"))
    return out


def simulate_world(seed: int, p: dict) -> tuple:
    """One world. Returns requests, then outdated, computations, checks and unchanged refreshes per rule.

    Order of draws. For each result: the number of inputs, then files until that
    many distinct ones are found, then one number from 0 to 99 for each input (the
    input is declared at a setting when the number is below the setting). For each
    step: one draw per file to decide whether it changes and, for a changed file,
    one draw per result that uses it to decide whether the result changes. Then
    one draw per assistant to decide whether it reuses a result, one for which
    result, and for a first use with a holder present, one for whether to take a
    copy and one for whose.
    """
    rng = SplitMix64(seed)
    files, results, assistants = p["files"], p["results"], p["assistants"]
    levels = p["declared_percent"]
    rules = variants(p)
    count = len(rules)
    kind = [("trust", "timer", "standing", "recheck").index(rule) for rule, _, _ in rules]
    setting = [value for _, value, _ in rules]
    level_of = [levels.index(setting[v]) if kind[v] == 2 else 0 for v in range(count)]

    users = [[] for _ in range(files)]
    for result in range(results):
        wanted = 1 + rng.below(p["max_inputs"])
        chosen = []
        while len(chosen) < wanted:
            f = rng.below(files)
            if f not in chosen:
                chosen.append(f)
        for f in chosen:
            users[f].append((result, rng.below(100)))

    value = [0] * results
    declared_changes = [[0] * results for _ in levels]
    has = [False] * (assistants * results)
    holders = [[] for _ in range(results)]
    seen = [[0] * (assistants * results) for _ in range(count)]
    mark = [[0] * (assistants * results) for _ in range(count)]
    outdated, reruns, checks, needless = ([0] * count for _ in range(4))
    uses = 0
    change, effect = p["change_per_file_per_step_ppm"], p["edit_changes_result_percent"]
    use, secondhand, power = p["use_per_step_percent"], p["secondhand_percent"], p["popularity_power"]

    for step in range(p["steps"]):
        for f in range(files):
            if rng.below(1000000) < change:
                for result, draw in users[f]:
                    for i, level in enumerate(levels):
                        if draw < level:
                            declared_changes[i][result] += 1
                    if rng.below(100) < effect:
                        value[result] += 1
        for a in range(assistants):
            if rng.below(100) >= use:
                continue
            result = (rng.below(1000) ** power * results) // (1000 ** power)
            here = a * results + result
            giver, fresh = -1, False
            if not has[here]:
                if holders[result] and rng.below(100) < secondhand:
                    giver = holders[result][rng.below(len(holders[result]))] * results + result
                else:
                    fresh = True
                has[here] = True
                holders[result].append(a)
            uses += 1
            now = value[result]
            for v in range(count):
                k = kind[v]
                stamp = step if k == 1 else declared_changes[level_of[v]][result] if k == 2 else 0
                s, m = seen[v], mark[v]
                if fresh:  # the assistant works the result out itself
                    reruns[v] += 1
                    s[here], m[here] = now, stamp
                    continue
                if giver >= 0:  # the copy arrives with what it stood on
                    s[here], m[here] = s[giver], m[giver]
                if k == 0:
                    rerun = False
                elif k == 1:
                    rerun = step - m[here] > setting[v]
                elif k == 2:
                    checks[v] += 1
                    rerun = m[here] != stamp
                else:
                    rerun = True
                if rerun:
                    reruns[v] += 1
                    if s[here] == now:
                        needless[v] += 1
                    s[here], m[here] = now, stamp
                elif s[here] != now:
                    outdated[v] += 1
    return uses, outdated, reruns, checks, needless


def per(part: int, whole: int, scale: int) -> int:
    """part / whole on the given scale, rounded half up, in whole numbers."""
    return (part * scale + whole // 2) // whole if whole else 0


def run(p: dict, worlds: int) -> tuple:
    """Total requests and one row per rule over the given number of worlds."""
    rules = variants(p)
    master = SplitMix64(p["seed"])
    total = 0
    sums = [[0] * len(rules) for _ in range(4)]
    lowest, highest = [None] * len(rules), [None] * len(rules)
    for _ in range(worlds):
        uses, *tallies = simulate_world(master.next(), p)
        total += uses
        for v in range(len(rules)):
            for i in range(4):
                sums[i][v] += tallies[i][v]
            share = per(tallies[0][v], uses, 10000)
            lowest[v] = share if lowest[v] is None else min(lowest[v], share)
            highest[v] = share if highest[v] is None else max(highest[v], share)
    rows = []
    for v, (rule, setting, label) in enumerate(rules):
        rows.append(
            {
                "rule": rule,
                "setting": setting,
                "label": label,
                "outdated_uses": sums[0][v],
                "outdated_per_10000_uses": per(sums[0][v], total, 10000),
                "lowest_world_per_10000": lowest[v],
                "highest_world_per_10000": highest[v],
                "reruns": sums[1][v],
                "reruns_per_1000_uses": per(sums[1][v], total, 1000),
                "fingerprint_checks": sums[2][v],
                "needless_reruns": sums[3][v],
            }
        )
    timers = [row for row in rows if row["rule"] == "timer"]
    for row in rows:
        if row["rule"] == "standing":
            row["beaten_by_timer"] = [
                timer["setting"]
                for timer in timers
                if timer["outdated_uses"] <= row["outdated_uses"]
                and timer["reruns"] <= row["reruns"]
                and (timer["outdated_uses"] < row["outdated_uses"] or timer["reruns"] < row["reruns"])
            ]
    return total, rows


def build() -> dict:
    """The whole stored result."""
    uses, rows = run(PARAMETERS, PARAMETERS["worlds"])

    def get(rule: str, setting: int = 0) -> dict:
        return next(row for row in rows if row["rule"] == rule and row["setting"] == setting)

    variations = []
    for name, change in VARIATIONS:
        v_uses, v_rows = run(dict(PARAMETERS, **change), VARIATION_WORLDS)
        keep = ("rule", "setting", "outdated_per_10000_uses", "reruns_per_1000_uses")
        variations.append(
            {
                "change": name,
                "setting_changed": change,
                "worlds": VARIATION_WORLDS,
                "uses": v_uses,
                "rows": [{key: row[key] for key in keep} for row in v_rows],
            }
        )
    return {
        "question": "What happens when assistants pass results to each other?",
        "kind": "model, not a measurement",
        "generator": "SplitMix64, integer draws only",
        "parameters": PARAMETERS,
        "uses": uses,
        "rows": rows,
        "predictions": [{"text": text, "held": bool(test(get))} for text, test in PREDICTIONS],
        "variations": variations,
        "does_not_cover": DOES_NOT_COVER,
    }


def table(result: dict) -> str:
    """The main table as plain text."""
    first = next(row["reruns"] for row in result["rows"] if row["rule"] == "trust")
    lines = [
        f"{result['uses']:,} requests in {result['parameters']['worlds']} simulated worlds",
        f"{first:,} first computations and {result['uses'] - first:,} requests with a held or received copy",
        "",
        f"{'rule':<52}{'outdated':>10}{'computations per 100':>22}{'unchanged refreshes':>22}{'comparisons':>14}",
    ]
    for row in result["rows"]:
        share, redo = row["outdated_per_10000_uses"], row["reruns_per_1000_uses"]
        label = row["label"]
        if row["rule"] == "standing":
            label = f"compare fingerprints, {row['setting']}% declaration chance"
        lines.append(
            f"{label:<52}{share // 100:>6}.{share % 100:02d}%{redo // 10:>20}.{redo % 10}"
            f"{row['needless_reruns']:>22,}{row['fingerprint_checks']:>14,}"
        )
    lines.append("")
    lines.append("Saved predictions (per-input declaration chances and the six tested timer thresholds)")
    for item in result["predictions"]:
        lines.append(("held      " if item["held"] else "NOT HELD  ") + item["text"])
    return "\n".join(lines)


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="store the result")
    parser.add_argument("--verify", action="store_true", help="recompute and compare with the stored result")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args(argv)
    result = build()
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.write:
        RESULT.parent.mkdir(parents=True, exist_ok=True)
        RESULT.write_text(text, encoding="utf-8")
        print(f"wrote results/{RESULT.name}")
        return 0
    if args.verify:
        if not RESULT.exists():
            print("no stored result: run with --write first", file=sys.stderr)
            return 1
        if json.loads(RESULT.read_text(encoding="utf-8")) != result:
            print("the stored result differs from this run", file=sys.stderr)
            return 1
        print(
            f"exchange simulation reproduced: {len(result['rows'])} rules, "
            f"{result['parameters']['worlds']} worlds, {result['uses']:,} requests"
        )
        return 0
    print(text if args.json else table(result), end="" if args.json else "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
