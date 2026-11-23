"""Scripted decisions and real command evidence for the optional transit branch."""

import json
import re

SUCCESSOR = "service-auditor"
RULE = "open-trip-line"
SESSION = "BUS-2 | Tuesday follow-up"
LIMIT = ("The rule checks the form of one line. Comparing its IDs with the timetable "
         "and dispatch records establishes which trips are actually unresolved.")
CASES = {"missing": "successor-count", "repaired": "successor-count",
         "holdout_stale": "changed-count", "holdout_repaired": "changed-count", "retired": "changed-count"}


def readings(r, key, expected=0):
    t = r.taos
    t(key + "-handoff", "handoff", "latest", "BUS-2", "--print")
    t(key + "-check", "atoms", "check", expected=expected)


def review(r, fixture):
    t = r.taos
    atom_file = r.tmp / "trip-line.json"
    atom_file.write_bytes((fixture / "trip-line.json").read_bytes())

    def propose(key):
        result = t(key, "propose", "--agent", "claude", "--kind", "atom", "--title", "Name the open trips",
                   "--body", "Give the next shift a line of trip IDs it can check against dispatch.",
                   "--evidence", "tuesday-dispatch.csv", "--atom-json", str(atom_file))
        return re.search(r"\bprop_[0-9a-f]{10}\b", result).group()

    declined = propose("offer-declined")
    r.file("pending-receipt", r.paths.proposals_dir / (declined + ".json"))
    readings(r, "pending")
    t("person-declines", "proposals", "decide", declined, "--status", "rejected", "--by", "human")
    t("decline-stands", "atoms", "promote", declined, "--by", "human", expected=1)
    r.file("declined-receipt", r.paths.proposals_dir / (declined + ".json"))
    readings(r, "declined")

    accepted = propose("offer-accepted")
    t("assistant-refused", "atoms", "promote", accepted, "--by", "claude", expected=1)
    t("person-accepts", "proposals", "decide", accepted, "--status", "accepted", "--by", "human")
    t("person-promotes", "atoms", "promote", accepted, "--by", "human")
    r.file("accepted-receipt", r.paths.proposals_dir / (accepted + ".json"))
    readings(r, "missing", expected=1)


def continue_audit(r):
    t = r.taos
    t("successor-check", "atoms", "check", expected=1)
    successor_note = r.tmp / "successor.md"
    template = t("successor-template", "handoff", "template", "BUS-2", "--from", SUCCESSOR,
                 "--to", "claude", "--session", SESSION)
    # Change only the risk section when filling in the trip IDs.
    sections = iter(("Tuesday's rate is pending.", "Reconciled the dispatch log against the timetable.",
                     "tuesday-schedule.csv and tuesday-dispatch.csv.", "Dispatch is incomplete.",
                     "python3 -B count.py count tuesday"))
    body = re.sub(r"(?m)^<[^\n]+>$", lambda _: next(sections), template)

    def write_note(key, trips=()):
        note = body
        if trips:
            note = note.replace("Dispatch is incomplete.", "Dispatch is incomplete.\nOpen trips: " + ", ".join(trips))
        successor_note.write_text(note, encoding="utf-8")
        t(key, "handoff", "write", "BUS-2", "--from", SUCCESSOR, "--to", "claude",
          "--session", SESSION, "--file", str(successor_note))

    # Verify the next command from the actual handoff before executing the known fixture command.
    received = r.records["read-handoff"]["output"]
    if received.split("## Next command\n")[-1].strip() != "python3 -B count.py count tuesday":
        raise ValueError("expected the transit counter as the literal next command")
    tuesday = json.loads(r.count("successor-count", "count", "tuesday"))
    write_note("write-repaired", tuesday["missing_trips"])
    readings(r, "repaired")

    # Change exactly one unresolved timetable ID. Keep the handoff and dispatch fixed for the first read.
    schedule = r.work / "tuesday-schedule.csv"
    r.file("original-timetable", schedule)
    rows = schedule.read_bytes()
    if rows.count(b"T11,06:34") != 1:
        raise ValueError("the changed trip must be a single timetable row")
    schedule.write_bytes(rows.replace(b"T11,06:34", b"T27,06:34"))
    r.file("changed-timetable", schedule)
    changed = json.loads(r.count("changed-count", "count", "tuesday"))
    readings(r, "holdout_stale")
    write_note("write-changed", changed["missing_trips"])
    readings(r, "holdout_repaired")

    t("person-retires", "atoms", "retire", RULE, "--by", "human",
      "--reason", "A formatted line alone cannot certify which trips are missing.")
    write_note("write-after-retirement")
    readings(r, "retired")


def observations(records):
    def receipt(key):
        return json.loads(records[key]["output"])

    statuses = {}
    for stage in ("pending", "declined", "missing", "repaired", "holdout_stale", "holdout_repaired", "retired"):
        result = re.search(r"^(ok|FAIL)\s+" + RULE + r"\s+", records[stage + "-check"]["output"], re.M)
        statuses[stage] = {"ok": "passes", "FAIL": "fails"}[result[1]] if result else "inactive"

    cases = {}
    for stage, count_key in CASES.items():
        note_key = stage + "-handoff"
        line = re.search(r"^Open trips: (.+)$", records[note_key]["output"], re.M)
        named = line[1].split(", ") if line else []
        missing = receipt(count_key)["missing_trips"]
        cases[stage] = {"missing_trips": missing, "named_trips": named, "matches_dispatch": sorted(named) == missing,
                        "handoff_evidence": note_key, "count_evidence": count_key}
    claims = receipt("capsule")["claims"]
    successor, = {claim["agent"] for claim in claims if "task:BUS-2" in claim["scopes"]}
    accepted = receipt("accepted-receipt")
    return {"rule_id": accepted["atom"]["id"], "successor": successor, "proposer": accepted["proposed_by"],
            "checks": statuses, "cases": cases, "limit": LIMIT}
