"""Record and verify the fictional service-report example with the public TAOS CLI."""

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from taos_core import demo
from taos_core.paths import Paths
from examples.transit.adaptation import replay as adaptation

FIXTURE = ROOT / "examples" / "transit"
DEFAULT_RECORD = FIXTURE / "workflow.json"
ADAPTATION = FIXTURE / "adaptation"
ADAPTATION_RECORD = ADAPTATION / "workflow.json"
INPUTS = ("count.py", "monday-schedule.csv", "monday-dispatch.csv", "tuesday-schedule.csv",
          "tuesday-dispatch.csv", "style.txt")
STANDARD = "Account for every scheduled trip in the morning service report."
CORRECTION = "Check every scheduled bus before reporting."
NEXT = "Find the dispatch records for T04 and T11 before reporting Tuesday's rate."
SESSIONS = {"report": "BUS-1 | Monday report", "audit": "BUS-2 | Log audit", "next": "BUS-2 | Tuesday follow-up"}
SCOPE = "service/report"
SCENES = {
    "standard": ("standard-add", "standard-rule", "scope-report"),
    "team": ("report-task", "create-audit", "audit-task", "related-tasks", "report-start", "audit-start", "claims", "overlap"),
    "correction": ("monday-count", "draft", "draft-check", "correct-rule", "old-day", "current-rule", "unrelated",
                   "lesson-add", "propose-check", "proposal", "write-report", "passing-check"),
    "handoff": ("tuesday-count", "tuesday-refusal", "next-action", "audit-evidence", "save-handoff", "resume",
                "capsule", "lesson-at-join", "read-handoff"),
    "change": ("fleet-instruction", "fleet-rule", "report-after-fleet-rule", "baseline-style", "style-edit",
               "style-why", "style-check", "restore-why", "baseline-dispatch",
               "source-dispatch", "source-count", "source-why", "source-check", "failed-why", "rebuild",
               "repaired-check", "repaired-why"),
    "review": ("report-evidence", "report-review", "before-acceptance", "agent-refusal", "human-accept",
               "baseline-why", "accepted-task", "acceptance-receipt", "style-why", "source-why", "repaired-why"),
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def record_digest(record):
    contents = {key: value for key, value in record.items() if key != "record_sha256"}
    return sha256(json.dumps(contents, sort_keys=True, separators=(",", ":")).encode())


def sources():
    files = [Path(__file__).resolve(), ROOT / "taos", ROOT / "bootstrap/answers.example.json",
             ROOT / "bootstrap/answers.schema.json", ROOT / "kernels/KERNEL_INDEX.json"]
    files.extend(sorted((ROOT / "taos_core").glob("*.py")))
    files.extend(FIXTURE / name for name in INPUTS)
    return {file.relative_to(ROOT).as_posix(): sha256(file.read_bytes()) for file in files}


def check(value, message):
    if not value:
        raise ValueError(message)


def create_home(tmp):
    """Run in a new process whose user home is empty before TAOS imports its usage adapters."""
    paths = demo.scratch_home(tmp, workspace=tmp / "transit", project="Morning service", prefix="BUS",
                              gates=[], tasks=[{
                                  "title": "Prepare the Monday service report",
                                  "goal": "Report the on-time share of all scheduled trips.",
                                  "next_action": "Reconcile the schedule with dispatch.",
                                  "done_when": "The Monday report accounts for every scheduled trip and passes the count check.",
                                  "verification": "python3 -B count.py check monday",
                              }])
    demo.configure(paths, gates=[{"name": "Monday report", "command": "python3 -B count.py check monday",
                                  "depends_on": ["monday"]}],
                   basis={"domains": {"monday": ["monday-*.csv", "monday-report.json", "count.py"],
                                      "tuesday": ["tuesday-*.csv"], "presentation": ["style.txt"]},
                          "ignore": ["AGENTS.md", "CLAUDE.md", ".taos-link.json"]})


class Recorder:
    """Execute subprocesses and keep their stdout/stderr, aliasing only run-local identifiers."""

    def __init__(self, tmp):
        self.tmp = tmp
        self.work = tmp / "transit"
        self.work.mkdir()
        for name in INPUTS:
            shutil.copyfile(FIXTURE / name, self.work / name)
        self.paths = Paths(tmp / "os")
        user_home = tmp / "user"
        user_home.mkdir()
        self.env = {"HOME": str(user_home), "TAOS_HOME": str(self.paths.home), "PYTHONDONTWRITEBYTECODE": "1",
                    "PATH": os.pathsep.join((str(Path(sys.executable).parent), os.defpath)), "PYTHONUTF8": "1"}
        setup = "from evals.transit_workflow import create_home; from pathlib import Path; import sys; create_home(Path(sys.argv[1]))"
        subprocess.run([sys.executable, "-B", "-c", setup, str(tmp)], cwd=ROOT, env=self.env, check=True, timeout=60)
        self.records = {}
        self.aliases = {}

    def alias(self, match):
        raw = match.group()
        prefix = match.group(1)
        values = self.aliases.setdefault(prefix, {})
        if raw not in values:
            values[raw] = f"{prefix}{len(values) + 1}"
        return values[raw]

    def normalize(self, text):
        text = text.replace(str(self.tmp), "<scratch>")
        text = re.sub(r"(control:   episode closed, j=)-?[0-9.]+", r"\1<runtime score>", text)
        # Preserve the distinct gate receipts even when the engine ran two in one second.
        text = re.sub(r"(\.taos/gates/BUS-\d+_)\d{8}T\d{6}Z(?:_\d+)?(?=\.json)", self.alias, text)
        text = re.sub(r"(\.taos/handoffs/)\d{8}T\d{12}Z(?=_BUS-)", self.alias, text)
        text = re.sub(r"\b(clm_|rule_|les_|prop_|ep_)[0-9a-f]{10}\b", self.alias, text)
        text = re.sub(r"\d{8}T\d{6}(?:\.\d+)?Z", "<run-time>", text)
        text = re.sub(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|\+00:00)", "<run-time>", text)
        return re.sub(r"((?:accepted it|moved it to (?:review|done)) on )\d{4}-\d\d-\d\d", r"\1<run-day>", text)

    def run(self, key, args, expected=0):
        is_taos = args[0] == "./taos"
        argv = ([sys.executable, "-B", str(self.paths.launcher)] + list(args[1:]) if is_taos
                else [sys.executable, "-B"] + list(args[2:]))
        result = subprocess.run(argv, cwd=self.paths.home if is_taos else self.work,
                                env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=60, check=False)
        cmd = shlex.join(args)
        check(result.returncode == expected,
              f"{key}: {cmd} exited {result.returncode}; expected {expected}\n{result.stdout}")
        check(key not in self.records, f"duplicate evidence identifier {key}")
        self.records[key] = {"command": self.normalize(cmd), "exit": result.returncode,
                             "output": self.normalize(result.stdout.rstrip())}
        return result.stdout

    def taos(self, key, *args, expected=0):
        return self.run(key, ["./taos", *args], expected)

    def count(self, key, action, day, expected=0):
        return self.run(key, ["python3", "-B", "count.py", action, day], expected)

    def file(self, key, path):
        self.run(key, ["python3", "-B", "-c",
                       "from pathlib import Path; import sys; print(Path(sys.argv[1]).read_text(encoding='utf-8'), end='')",
                       str(path)])

    def control(self, key, edited_file=None, edited_trip=None):
        why = json.loads(self.taos(key + "-why", "why", "BUS-1", "--json"))
        parts = {part["kind"]: part for part in why["parts"]}
        monday = json.loads(self.count(key + "-control-count", "count", "monday"))
        report = self.work / "monday-report.json"
        return {"check": parts["check"]["state"], "artifact": parts["artifact"]["state"],
                "acceptance": parts["acceptance"]["state"], "edited_file": edited_file, "edited_trip": edited_trip,
                "report_percent": json.loads(report.read_bytes())["percent"], "source_percent": monday["scheduled_percent"],
                "report_sha256": sha256(report.read_bytes()), "style_sha256": sha256((self.work / "style.txt").read_bytes()),
                "dispatch_sha256": sha256((self.work / "monday-dispatch.csv").read_bytes()), "evidence": key + "-why"}


def decoded(records, key):
    return json.loads(records[key]["output"])


def run_history(r, successor="codex"):
    t = r.taos
    t("standard-add", "rule", "add", "--by", "human", "--scope", SCOPE, "--said-on", "2026-01-04", "--quote", STANDARD)
    original, = json.loads(t("standard-rule", "rule", "governing", SCOPE, "--on", "2026-01-04", "--json"))
    t("scope-report", "task", "update", "BUS-1", "--agent", "human", "--set", "labels=" + SCOPE)
    t("report-task", "task", "show", "BUS-1", "--json")
    t("create-audit", "task", "create", "--agent", "human", "--title", "Audit the service logs",
      "--goal", "Reconcile each scheduled trip with the dispatch record.",
      "--next-action", "Reconcile the schedule with dispatch.",
      "--done-when", "Both days have a dispatch disposition for every scheduled trip.",
      "--verification", "python3 -B count.py count tuesday", "--label", SCOPE, "--json")
    t("audit-task", "task", "show", "BUS-2", "--json")
    t("related-tasks", "task", "relate", "BUS-1", "relatedTo", "BUS-2", "--agent", "human")
    for role, task, actor in (("report", "BUS-1", "codex"), ("audit", "BUS-2", "claude")):
        t(role + "-start", "start", "--agent", actor, "--task", task, "--session", SESSIONS[role])
    t("claims", "claim", "status", "--json")
    t("overlap", "claim", "check", "--agent", "codex", "--scope", "task:BUS-2", expected=4)

    r.count("monday-count", "count", "monday")
    r.count("draft", "draft", "monday")
    def gate(key, expected=0):
        return t(key, "gate", "run", "--task", "BUS-1", "--agent", "codex", expected=expected)
    gate("draft-check", 1)
    t("correct-rule", "rule", "add", "--by", "human", "--scope", SCOPE, "--said-on", "2026-01-05",
      "--supersedes", original["id"], "--quote", CORRECTION)
    for key, scope, day in (("old-day", SCOPE, "2026-01-04"), ("current-rule", SCOPE, "2026-01-06"),
                            ("unrelated", "fleet/maintenance", "2026-01-06")):
        t(key, "rule", "governing", scope, "--on", day, "--json")
    t("lesson-add", "lesson", "add", "--by", "human", "--scope", "BUS-2", "--said-on", "2026-01-05",
      "--title", "Keep cancellations in the denominator", "--words", "Those two canceled trips were scheduled.",
      "--mistake", "The draft counted only the 18 logged departures.", "--why",
      "The displayed rate rose from 80% to 89% when the cancellations disappeared.", "--moment", "join")
    t("propose-check", "propose", "--agent", "claude", "--kind", "other", "--title",
      "Check every service day before publication", "--body",
      "Apply the schedule-to-dispatch reconciliation to each new day's report; hold the rate while any trip lacks a record.",
      "--evidence", "tuesday-dispatch.csv")
    t("proposal", "proposals", "list", "--json")
    r.count("write-report", "write", "monday")
    gate("passing-check")
    t("report-evidence", "task", "evidence", "BUS-1", "--agent", "codex", "--ref", "monday-report.json",
      "--artifact", "--depends-on", "monday-schedule.csv", "--depends-on", "monday-dispatch.csv", "--depends-on", "count.py",
      "--note", "Monday numerical report checked against dispatch and the full timetable.")
    t("report-review", "finish", "--agent", "codex", "--task", "BUS-1", "--state", "review",
      "--reason", "Monday reconciled.", "--evidence", "monday-report.json", "--session", SESSIONS["report"])
    t("before-acceptance", "why", "BUS-1", "--json")
    t("agent-refusal", "task", "accept", "BUS-1", "--by", "codex", expected=1)
    t("human-accept", "task", "accept", "BUS-1", "--by", "human", "--note", "Reviewed Monday at 16 of 20.")
    task = json.loads(t("accepted-task", "task", "show", "BUS-1", "--json"))
    r.file("acceptance-receipt", r.paths.state / "acceptance" / task["acceptance"]["receipt"])
    controls = {"baseline": r.control("baseline")}
    t("fleet-instruction", "rule", "add", "--by", "human", "--scope", "fleet/maintenance",
      "--said-on", "2026-01-06", "--quote", "Record each tire inspection in the fleet log.")
    t("fleet-rule", "rule", "governing", "fleet/maintenance", "--on", "2026-01-06", "--json")
    t("report-after-fleet-rule", "why", "BUS-1", "--json")

    r.count("tuesday-count", "count", "tuesday")
    r.count("tuesday-refusal", "write", "tuesday", 3)
    check(not (r.work / "tuesday-report.json").exists(), "Tuesday refusal left a report")
    t("next-action", "task", "update", "BUS-2", "--agent", "claude", "--set", "next_action=" + NEXT)
    t("audit-evidence", "task", "evidence", "BUS-2", "--agent", "claude", "--ref", "tuesday-dispatch.csv",
      "--note", "Missing T04 and T11 from Tuesday's schedule. Monday verified in BUS-1.")
    handoff_file = r.tmp / "audit-handoff.md"
    risk = ("T04 and T11 have no dispatch record. Their outcomes remain unknown." if successor == "codex"
            else "Some scheduled trips have no dispatch record. Their outcomes remain unknown.")
    handoff_file.write_text(
        "Agent: claude\nChat/session: BUS-2 | Log audit\nTask: BUS-2 | Audit the service logs\nClaim/scope: task:BUS-2\n\n"
        "## State\nMonday was reviewed at 16 of 20. Tuesday's rate is pending.\n\n"
        "## Changed\nThe corrected report counts the full timetable, including cancellations.\n\n"
        "## Evidence\nmonday-report.json; tuesday-schedule.csv; tuesday-dispatch.csv.\n\n"
        f"## Risks and open questions\n{risk}\n\n"
        "## Next command\npython3 -B count.py count tuesday\n", encoding="utf-8")
    t("save-handoff", "finish", "--agent", "claude", "--task", "BUS-2", "--state", "next",
      "--reason", "Continue the incomplete Tuesday audit.", "--session", SESSIONS["audit"],
      "--handoff-file", str(handoff_file), "--to", successor)
    if successor == adaptation.SUCCESSOR:
        adaptation.review(r, ADAPTATION)
    t("resume", "start", "--task", "BUS-2", "--agent", successor, "--session", SESSIONS["next"])
    t("capsule", "capsule", "BUS-2", "--json")
    t("lesson-at-join", "lesson", "at", "join", "--agent", successor, "--task", "BUS-2", "--json")
    t("read-handoff", "handoff", "latest", "BUS-2", "--print")
    if successor == adaptation.SUCCESSOR:
        return controls

    style = r.work / "style.txt"
    before = style.read_bytes()
    r.file("baseline-style", style)
    style.write_bytes(b"MORNING SERVICE REPORT\n")
    r.file("style-edit", style)
    controls["style"] = r.control("style", "style.txt")
    gate("style-check")
    style.write_bytes(before)
    controls["restore"] = r.control("restore", "style.txt")
    dispatch = r.work / "monday-dispatch.csv"
    original_bytes = dispatch.read_bytes()
    r.file("baseline-dispatch", dispatch)
    check(original_bytes.count(b"M18,late\n") == 1, "expected one late M18")
    dispatch.write_bytes(original_bytes.replace(b"M18,late\n", b"M18,on_time\n"))
    r.file("source-dispatch", dispatch)
    r.count("source-count", "count", "monday")
    controls["source"] = r.control("source", "monday-dispatch.csv", "M18")
    gate("source-check", 1)
    controls["failed"] = r.control("failed")
    r.count("rebuild", "write", "monday")
    gate("repaired-check")
    controls["repaired"] = r.control("repaired", "monday-report.json")
    return controls


def observations(records, controls):
    tasks = [decoded(records, role + "-task") for role in ("report", "audit")]
    claims = decoded(records, "claims")["live"]
    team = []
    for task in tasks:
        scope = "task:" + task["id"]
        owner, = [claim["agent"] for claim in claims if scope in claim["scopes"]]
        team.append({"task": task["id"], "owner": owner, "scope": scope, "title": task["title"],
                     "done_when": task["done_when"]})
    capsule = decoded(records, "capsule")
    return {"monday": decoded(records, "monday-count"), "tuesday": decoded(records, "tuesday-count"),
            "team": team, "rules": {"before": decoded(records, "old-day"), "after": decoded(records, "current-rule"),
                                    "unrelated": decoded(records, "unrelated")},
            "lesson": decoded(records, "lesson-at-join")[0], "capsule": capsule, "handoff": capsule["handoff_head"],
            "proposal": decoded(records, "proposal")[0], "approval": decoded(records, "acceptance-receipt"),
            "controls": controls}


def trial():
    with tempfile.TemporaryDirectory(prefix="taos-transit-") as directory:
        session = Recorder(Path(directory).resolve())
        controls = run_history(session)
        records = session.records
        record = {"schema": "transit-workflow/1", "sources": sources(),
                  "scope": "Deterministic command replay with fictional rows and scripted human, codex and claude labels.",
                  "scenes": {scene: {"evidence": list(keys)} for scene, keys in SCENES.items()},
                  "records": records, "observations": observations(records, controls)}
        record["record_sha256"] = record_digest(record)
        return record


def validate(record):
    """Reject a stale source, unsupported scene, or observation contradicted by its evidence."""
    check(record["schema"] == "transit-workflow/1", "unknown transit record schema")
    check(record["record_sha256"] == record_digest(record), "transit record contents differ from the recorded digest")
    check(record["sources"] == sources(), "transit record sources changed; regenerate the record")
    raw = record["records"]
    obs = record["observations"]
    controls = obs["controls"]
    check(record["scenes"] == {s: {"evidence": list(keys)} for s, keys in SCENES.items()}, "scene evidence changed")
    for keys in SCENES.values():
        for key in keys:
            check(raw[key]["command"] and raw[key]["output"], f"missing evidence for {key}")
    check(obs == observations(raw, controls), "displayed observation differs from its native record")
    exceptions = {"overlap": 4, "tuesday-refusal": 3, "draft-check": 1, "agent-refusal": 1, "source-check": 1}
    for key, row in raw.items():
        check(row["exit"] == exceptions.get(key, 0), f"unexpected exit for {key}")

    monday = obs["monday"]
    check([monday[k] for k in ("scheduled", "recorded", "on_time", "canceled", "logged_percent", "scheduled_percent")]
          == [20, 18, 16, 2, 89, 80], "Monday fixture denominators changed")
    check(monday["canceled_trips"] == ["M17", "M19"] and not monday["missing_trips"], "wrong canceled or missing trips")
    tuesday = obs["tuesday"]
    check(tuesday["missing_trips"] == ["T04", "T11"] and tuesday["scheduled_percent"] is None
          and tuesday["logged_percent"] is None, "unresolved Tuesday trips cannot have a rate")
    check("T04, T11" in raw["tuesday-refusal"]["output"], "publication refusal lost the missing trips")
    check(decoded(raw, "draft")["denominator"] == 18 and decoded(raw, "write-report")["denominator"] == 20,
          "the correction must change the published denominator")
    check([row["owner"] for row in obs["team"]] == ["codex", "claude"], "ownership mismatch")
    check("held by claude" in raw["overlap"]["output"], "conflict did not identify the owner")
    before, = obs["rules"]["before"]
    after, = obs["rules"]["after"]
    check(before["quote"] == STANDARD and after["quote"] == CORRECTION and before["scope"] == after["scope"] == SCOPE
          and after["supersedes"] == before["id"] and after["added_by"] == "human" and not obs["rules"]["unrelated"],
          "date/scope resolution or correction provenance failed")
    fleet, = decoded(raw, "fleet-rule")
    check(fleet["scope"] == "fleet/maintenance"
          and decoded(raw, "report-after-fleet-rule") == decoded(raw, "baseline-why"),
          "an unrelated maintenance instruction must leave the report and its approval unchanged")
    capsule = obs["capsule"]
    check(capsule["next_action"] == NEXT and {c["agent"] for c in capsule["claims"]} == {"codex"}
          and [rule["quote"] for rule in capsule["standing"]["instructions"]] == [CORRECTION], "wrong successor capsule")
    check(obs["lesson"]["words"] in raw["resume"]["output"] and CORRECTION in raw["resume"]["output"]
          and obs["handoff"] in raw["read-handoff"]["output"] and "T04 and T11" in obs["handoff"],
          "successor's recorded brief is missing the correction or handoff")
    check(obs["proposal"]["status"] == "proposed" and obs["lesson"]["status"] == "candidate",
          "unpromoted proposal/lesson changed status")
    check(not decoded(raw, "before-acceptance")["accepted"] and obs["approval"]["by"] == "human"
          and obs["approval"]["task_id"] == "BUS-1" and "only the human" in raw["agent-refusal"]["output"],
          "a passing check is not evidence of human approval")

    states = {"baseline": ("holds", "holds", "holds", 80, 80), "style": ("holds", "holds", "stale", 80, 80),
              "restore": ("holds", "holds", "holds", 80, 80), "source": ("stale", "stale", "stale", 80, 85),
              "failed": ("fails", "stale", "stale", 80, 85), "repaired": ("holds", "stale", "stale", 85, 85)}
    check(set(controls) == set(states), "missing a controlled intervention")
    for key, expected in states.items():
        control = controls[key]
        check(tuple(control[k] for k in ("check", "artifact", "acceptance", "report_percent", "source_percent")) == expected,
              f"{key} produced different check, artifact, approval or rates")
        why = decoded(raw, key + "-why")
        parts = {part["kind"]: part for part in why["parts"]}
        check(all(control[k] == parts[k]["state"] for k in ("check", "artifact", "acceptance")),
              f"{key} does not match the engine's verdict")
        count = decoded(raw, key + "-control-count")
        saved = decoded(raw, "rebuild" if key == "repaired" else "write-report")
        check(control["source_percent"] == count["scheduled_percent"] and control["report_percent"] == saved["percent"]
              and control["report_sha256"] == sha256((json.dumps(saved, sort_keys=True) + "\n").encode()),
              f"{key} count or report version differs from the recorded input")
    base = controls["baseline"]
    old_dispatch = raw["baseline-dispatch"]["output"] + "\n"
    new_dispatch = raw["source-dispatch"]["output"] + "\n"
    check(old_dispatch == (FIXTURE / "monday-dispatch.csv").read_text(encoding="utf-8")
          and old_dispatch.replace("M18,late\n", "M18,on_time\n") == new_dispatch,
          "source intervention must change exactly M18")
    for key, dispatch in (("baseline", old_dispatch), ("source", new_dispatch)):
        check(controls[key]["dispatch_sha256"] == sha256(dispatch.encode()), f"{key} dispatch bytes differ")
    for key, raw_key in (("baseline", "baseline-style"), ("style", "style-edit")):
        check(controls[key]["style_sha256"] == sha256((raw[raw_key]["output"] + "\n").encode()), f"{key} style bytes differ")
    check(base["report_sha256"] == obs["approval"]["snapshot"]["domains"]["monday"]["files"]["monday-report.json"],
          "the accepted bytes must be the reviewed Monday report")
    check("not run again" in raw["style-check"]["output"] and "ran now and failed" in raw["source-check"]["output"],
          "lost the distinction between reuse and fresh failure")
    for key, different in (("style", {"style_sha256"}), ("restore", set()), ("source", {"dispatch_sha256"}),
                           ("failed", {"dispatch_sha256"}), ("repaired", {"dispatch_sha256", "report_sha256"})):
        changed = {field for field in ("dispatch_sha256", "style_sha256", "report_sha256") if controls[key][field] != base[field]}
        check(changed == different, f"{key} changed the wrong files")
    return record


def load_record(path=None):
    try:
        return validate(json.loads(Path(path or DEFAULT_RECORD).read_text(encoding="utf-8")))
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Malformed transit record: {exc}") from exc


def adaptation_sources():
    inputs = sources()
    for file in (ADAPTATION / "replay.py", ADAPTATION / "trip-line.json", ROOT / "atoms/promoted_atoms.json"):
        inputs[file.relative_to(ROOT).as_posix()] = sha256(file.read_bytes())
    return inputs


def adaptation_trial():
    with tempfile.TemporaryDirectory(prefix="taos-transit-") as directory:
        session = Recorder(Path(directory).resolve())
        session.taos("register-successor", "bootstrap", "add-agent", adaptation.SUCCESSOR, "--by", "human", "--json")
        run_history(session, successor=adaptation.SUCCESSOR)
        # The first part reuses the existing two-session case. Retain the commands that the branch depends on.
        adaptation.continue_audit(session)
        before = {"register-successor", "correct-rule", "current-rule", "tuesday-count", "tuesday-refusal",
                  "lesson-add", "next-action"}
        keys = list(session.records)
        before.update(keys[keys.index("save-handoff"):])
        records = {key: row for key, row in session.records.items() if key in before}
        record = {"schema": "transit-adaptation/1", "sources": adaptation_sources(),
                  "scope": "Two scripted audit sessions with fictional data and real local TAOS commands.",
                  "scenes": {"adaptation": {"evidence": list(records)}}, "records": records,
                  "observations": {"adaptation": adaptation.observations(records)}}
        record["record_sha256"] = record_digest(record)
        return record


def validate_adaptation(record):
    check(record["schema"] == "transit-adaptation/1", "unknown adaptation schema")
    check(record["record_sha256"] == record_digest(record), "adaptation record digest differs")
    check(record["sources"] == adaptation_sources(), "adaptation sources changed; regenerate the record")
    raw = record["records"]
    keys = record["scenes"]["adaptation"]["evidence"]
    check(set(keys) == set(raw) and len(keys) == len(raw), "adaptation evidence index differs")
    refused = {"tuesday-refusal": 3, "decline-stands": 1, "assistant-refused": 1, "missing-check": 1, "successor-check": 1}
    for key, row in raw.items():
        check(row["command"] and row["output"] and row["exit"] == refused.get(key, 0), f"bad evidence for {key}")
    obs = adaptation.observations(raw)
    check(record["observations"] == {"adaptation": obs}, "adaptation display differs from commands")
    check(obs["rule_id"] == adaptation.RULE and obs["proposer"] == "claude" and obs["successor"] == adaptation.SUCCESSOR
          and adaptation.SUCCESSOR in decoded(raw, "register-successor")["agents"], "wrong proposer or successor")
    pending, declined, accepted = [decoded(raw, key + "-receipt") for key in ("pending", "declined", "accepted")]
    check(pending["status"] == "proposed" and pending["id"] == declined["id"] and declined["id"] != accepted["id"]
          and declined["status"] == "rejected" and accepted["status"] == "accepted"
          and declined["decided_by"] == accepted["decided_by"] == "human"
          and pending["atom"] == declined["atom"] == accepted["atom"] == json.loads((ADAPTATION / "trip-line.json").read_text()),
          "review decisions must cover the same offered rule in two distinct proposals")
    check(obs["checks"] == {"pending": "inactive", "declined": "inactive", "missing": "fails", "repaired": "passes",
                            "holdout_stale": "passes", "holdout_repaired": "passes", "retired": "inactive"},
          "unexpected checks before or after human review")
    check(raw["pending-handoff"]["output"] == raw["declined-handoff"]["output"] == raw["missing-handoff"]["output"]
          == raw["read-handoff"]["output"] and raw["successor-check"] == raw["missing-check"]
          and "Agent: " + adaptation.SUCCESSOR in raw["repaired-handoff"]["output"]
          and raw["retired-check"]["output"] == raw["pending-check"]["output"], "successor or retirement control differs")
    check("--by human" in raw["person-retires"]["command"] and adaptation.RULE in raw["person-retires"]["output"]
          and all(key in raw for key in refused), "missing review or refusal evidence")
    check(raw["original-timetable"]["output"] + "\n" == (FIXTURE / "tuesday-schedule.csv").read_text()
          and raw["original-timetable"]["output"].replace("T11,06:34", "T27,06:34") == raw["changed-timetable"]["output"],
          "the holdout must change exactly one timetable ID")
    check(raw["repaired-handoff"]["output"] == raw["holdout_stale-handoff"]["output"],
          "the holdout must test the unchanged handoff")
    for key, case in obs["cases"].items():
        expected_ids = ["T04", "T11"] if key in ("missing", "repaired") else ["T04", "T27"]
        check(case["missing_trips"] == expected_ids and case["matches_dispatch"] == (key in ("repaired", "holdout_repaired"))
              and decoded(raw, case["count_evidence"])["scheduled_percent"] is None,
              f"unexpected reconciliation in {key}")
    return record


def load_adaptation_record(path=None):
    try:
        return validate_adaptation(json.loads(Path(path or ADAPTATION_RECORD).read_text(encoding="utf-8")))
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Malformed transit adaptation record: {exc}") from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adaptation", action="store_true", help="replay the optional human-reviewed handoff check")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--verify", nargs="?", const=True, type=Path, help="replay and compare to saved JSON")
    action.add_argument("--write", action="store_true", help="replace the selected fixture record after validation")
    args = parser.parse_args()
    destination = ADAPTATION_RECORD if args.adaptation else DEFAULT_RECORD
    record = validate_adaptation(adaptation_trial()) if args.adaptation else validate(trial())
    if args.verify:
        verify_path = destination if args.verify is True else args.verify
        saved = load_adaptation_record(verify_path) if args.adaptation else load_record(verify_path)
        if saved != record:
            for key, row in record["records"].items():
                if saved["records"].get(key) != row:
                    print(f"Transit replay differs at command {key}.", file=sys.stderr)
                    return 1
            print("Transit replay differs from the retained observations.", file=sys.stderr)
            return 1
        scenes = len(record["scenes"])
        print(f'{len(record["records"])} transit evidence records reproduced across {scenes} scene{"s" if scenes != 1 else ""}.')
    elif args.write:
        data = json.dumps(record, sort_keys=True, indent=2) + "\n"
        # A concurrent read sees the old complete record or the new complete record.
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=destination.parent, delete=False) as f:
            f.write(data)
        os.chmod(f.name, 0o644)
        os.replace(f.name, destination)
        print(f"Recorded {destination.relative_to(ROOT)}.")
    else:
        print(json.dumps(record, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
