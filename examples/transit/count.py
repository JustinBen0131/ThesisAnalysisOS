"""Reconcile fictional scheduled trips against dispatch and check the saved Monday report."""

import argparse
import csv
import json
from pathlib import Path


def read_rows(path, value):
    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        if rows.fieldnames != ["trip", value]:
            raise ValueError(f"{path.name} needs trip,{value}")
        result = {}
        for row in rows:
            trip = row["trip"]
            if not trip or trip in result or not row[value] or None in row:
                raise ValueError(f"malformed or duplicate trip in {path.name}: {trip!r}")
            result[trip] = row[value]
        return result


def reconcile(root, day):
    schedule = read_rows(root / f"{day}-schedule.csv", "scheduled_at")
    dispatch = read_rows(root / f"{day}-dispatch.csv", "disposition")
    if not schedule or set(dispatch) - set(schedule):
        raise ValueError("empty timetable or dispatch record for an unscheduled trip")
    if set(dispatch.values()) - {"on_time", "late", "canceled"}:
        raise ValueError("unrecognized disposition")
    missing = sorted(schedule.keys() - dispatch.keys())
    canceled = sorted(trip for trip, state in dispatch.items() if state == "canceled")
    recorded = len(dispatch) - len(canceled)
    on_time = sum(state == "on_time" for state in dispatch.values())
    return {
        "scheduled": len(schedule), "recorded": recorded, "on_time": on_time,
        "canceled": len(canceled), "canceled_trips": canceled, "missing_trips": missing,
        "logged_percent": round(100 * on_time / recorded) if recorded and not missing else None,
        "scheduled_percent": round(100 * on_time / len(schedule)) if not missing else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["count", "draft", "write", "check"])
    parser.add_argument("day", choices=["monday", "tuesday"])
    args = parser.parse_args()
    day = args.day
    counts = reconcile(Path("."), day)
    if args.action == "count":
        print(json.dumps(counts, sort_keys=True))
        return 0
    if counts["missing_trips"]:
        print("Rate pending. Missing dispatch records: " + ", ".join(counts["missing_trips"]))
        return 3
    report = Path(f"{day}-report.json")
    # 'draft' deliberately recreates the departure-log-only calculation in the film.
    denominator = counts["recorded"] if args.action == "draft" else counts["scheduled"]
    rate = counts["logged_percent"] if args.action == "draft" else counts["scheduled_percent"]
    expected = {"day": day, "on_time": counts["on_time"], "denominator": denominator, "percent": rate}
    if args.action == "check":
        saved = json.loads(report.read_text(encoding="utf-8")) if report.is_file() else None
        print(json.dumps({"expected": expected, "saved": saved}, sort_keys=True))
        return int(saved != expected)
    report.write_text(json.dumps(expected, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(expected, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
