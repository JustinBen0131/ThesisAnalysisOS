"""Review a finite compute campaign from local evidence. The site renders these same findings."""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

from .util import TaosError

EVIDENCE = "taos.hpc.evidence.v1"
REPORT = "taos.hpc.review.v1"
BASIS = ("input", "recipe", "settings", "check")
SETTINGS = {
    "htcondor": ("HTCondor", "Use the saved submit description, job history and output-transfer receipts."),
    "slurm": ("Slurm", "Use the saved job script, accounting record and output checks."),
    "aws": ("AWS Batch", "Use the saved job definition, attempt status, object checks and budget in one currency."),
    "local": ("Workstation", "Use the command record, worker exit status, peak usage and output checks."),
    "other": ("Other environment", "Name the execution record, the resource owner and the independent output check."),
}
BRIEF = """Research question
{question}

Environment: {setting}. {guidance}

Inspect the records already available to you. List the expected output IDs from the input manifest before looking at what returned. For each ID compare the input, recipe, settings and independent check with the recorded attempt. Record its backend state, expected and observed counts, and a small checked file or audit receipt with its recorded SHA-256. Preserve unknowns. If an attempt might still exist, reconcile its identity before suggesting another.

When saved accounting is available, include its local file and SHA-256. For each distinct attempt record its output ID and elapsed worker-seconds, including failed attempts. Keep missing durations unknown.

For a larger run, identify a checked pilot with the same workload profile, including unusually heavy inputs. Use measured wall time, memory, temporary and retained bytes, file counts and permitted concurrency. Include a spending limit and the cost per job for cloud work. Name who can authorize the proposed scope.

Use examples/hpc/campaign.json in the downloaded project as the input format. Save the local evidence as campaign.json and run:
./taos hpc review campaign.json --json

Return the JSON review and the references behind its first unresolved item. Use only local read access. Leave submission, retries, transfers, deletion and spending to the resource owner."""
LIMIT = 16 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
MAX_ROWS = 10000
LABELS = {"keep": "Reuse", "wait": "Already in flight", "inspect": "Inspect evidence",
          "retry": "Review a targeted retry", "pilot": "Plan unstarted work"}
SCOPE = ("The reviewer compares a local manifest with retained checks and hashes the cited files. "
         "The project supplies the scientific test and observations. The resource owner decides what runs.")


def brief(question, setting):
    if not _text(question) or setting not in SETTINGS:
        raise TaosError("Enter a research question and choose a supported environment.")
    label, guidance = SETTINGS[setting]
    return BRIEF.format(question=question.strip(), setting=label, guidance=guidance)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _count(value, minimum=0):
    return type(value) is int and minimum <= value <= 2**53 - 1


def _index(rows, label, *, private_ids=False):
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise TaosError(f"{label} must be a list with at most {MAX_ROWS} entries.")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not _text(row.get("id")):
            raise TaosError(f"Each entry in {label} needs an output ID.")
        key = row["id"]
        if key != key.strip() or key in result:
            if private_ids:
                raise TaosError(f"Conflicting or untrimmed ID in {label}.")
            raise TaosError(f"Conflicting or untrimmed output ID in {label}: {key!r}.")
        result[key] = row
    return result


class EvidenceFiles:
    """Only open regular files inside the selected packet. Large results can cite small audit receipts."""
    def __init__(self, root):
        self.root = root.resolve()
        self.digests = {}
        self.retained = {}
        self.used = 0

    def check(self, name, expected, retain=False):
        if not _text(name) or not isinstance(expected, str) or len(expected) != 64 or any(
            c not in "0123456789abcdef" for c in expected
        ):
            return "Record a local output or audit receipt and its original SHA-256."
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            return "Choose a file inside this evidence packet."
        try:
            path = (self.root / path).resolve()
            if not path.is_relative_to(self.root):
                return "Choose a file inside this evidence packet."
            if path not in self.digests or (retain and name not in self.retained):
                info = path.stat()
                if not stat.S_ISREG(info.st_mode):
                    return "The cited evidence must be a regular file."
                if info.st_size > LIMIT or self.used + info.st_size > MAX_TOTAL:
                    return "Use a small retained audit receipt for this output."
                with path.open("rb") as stream:
                    data = stream.read(min(LIMIT, MAX_TOTAL - self.used) + 1)
                if len(data) != info.st_size:
                    return "The evidence file changed size. Read a stable receipt."
                self.used += len(data)
                self.digests[path] = hashlib.sha256(data).hexdigest()
                if retain:
                    self.retained[name] = data
            return "" if self.digests[path] == expected else "The bytes differ from the recorded SHA-256."
        except (OSError, RuntimeError, ValueError):
            return "The cited local output or audit receipt could not be read."


def _row(plan, actual, files):
    state = actual.get("state", "unknown")
    evidence = actual.get("source") if _text(actual.get("source")) else ""
    def finding(action, reason, ref=evidence):
        receipt = actual.get("receipt")
        count = receipt.get("count") if isinstance(receipt, dict) else None
        basis = plan.get("basis") or {}
        recorded = receipt.get("basis") if isinstance(receipt, dict) else None
        return {"id": plan["id"], "action": action, "reason": reason, "reference": ref,
                "basis": {key: basis[key] for key in BASIS if _text(basis.get(key))},
                "recorded_basis": {key: recorded[key] for key in BASIS if _text(recorded.get(key))}
                                  if isinstance(recorded, dict) else {},
                "receipt_sha256": receipt.get("sha256") if isinstance(receipt, dict) and _text(receipt.get("sha256")) else None,
                "expected_count": plan.get("count") if _count(plan.get("count")) else None,
                "reported_count": count if _count(count) else None}

    if not evidence or state == "unknown":
        return finding("inspect", "Reconcile the attempt with the saved submission or execution record.")
    if state in ("queued", "running"):
        return finding("wait", "An existing attempt is in flight. Read its next scheduled progress or output record.")
    if state == "unstarted":
        if actual.get("receipt") is not None:
            return finding("inspect", "An output receipt conflicts with the unstarted execution state.")
        return finding("pilot", "The execution record confirms this item has never started.")
    if state not in ("finished", "failed"):
        raise TaosError(f"Unrecognized execution state for {plan['id']}: {state!r}.")

    def affected(reason):
        diagnosis = actual.get("diagnosis")
        if isinstance(diagnosis, dict) and all(_text(diagnosis.get(k)) for k in ("cause", "reference")):
            problem = files.check(diagnosis["reference"], diagnosis.get("sha256"))
            if problem:
                return finding("inspect", reason + " Check the diagnosis evidence. " + problem, diagnosis["reference"])
            return finding("retry", reason + " Recorded cause: " + diagnosis["cause"], diagnosis["reference"])
        return finding("inspect", reason + " Identify the cause before proposing a retry.")

    if state == "failed":
        return affected("The execution record reports a terminal failure.")
    receipt = actual.get("receipt")
    if not isinstance(receipt, dict):
        return finding("inspect", "The job finished. Its independent output check is missing.")
    pinned = receipt.get("basis")
    target = plan.get("basis")
    if not isinstance(pinned, dict) or not isinstance(target, dict) or any(
        not _text(values.get(k)) for values in (pinned, target) for k in BASIS
    ):
        return finding("inspect", "The input, recipe, settings or independent check has no recorded identity.")
    changed = [k for k in BASIS if pinned[k] != target[k]]
    if changed:
        details = ". ".join(f"{k.capitalize()} when checked: {pinned[k]}. Requested now: {target[k]}" for k in changed)
        return finding("inspect", details + ". Scope the affected work.")
    problem = files.check(receipt.get("file"), receipt.get("sha256"))
    if problem:
        return finding("inspect", problem)
    ref = receipt["file"]
    if not _count(receipt.get("count")) or not _count(plan.get("count")) or type(receipt.get("passed")) is not bool:
        return finding("inspect", "Supply both counts and the result of the independent check.", ref)
    if receipt["count"] != plan["count"]:
        return affected(f"The receipt reports {receipt['count']} of {plan['count']} expected records.")
    if not receipt["passed"]:
        return affected("The independent output check failed.")
    return finding("keep", f"The recorded basis, {plan['count']} expected records, independent check and file hash agree.", ref)


def _batch(request, plan, findings, setting):
    if request is None:
        return None
    if not isinstance(request, dict):
        raise TaosError("batch must be an object.")
    ids = request.get("ids")
    if not isinstance(ids, list) or not ids or any(not _text(i) for i in ids) or len(set(ids)) != len(ids):
        raise TaosError("Give the proposed batch a nonempty list of distinct output IDs.")
    issues = []
    result = {"ids": ids, "state": "hold", "issues": issues, "warnings": [], "estimates": {}, "owner": ""}
    if any(i not in plan or findings[i]["action"] not in ("pilot", "retry") for i in ids):
        issues.append("Limit the batch to confirmed unstarted items or diagnosed terminal failures.")
    pilot_id = request.get("pilot_id")
    pilot = plan.get(pilot_id) if _text(pilot_id) else None
    if not pilot or findings[pilot_id]["action"] != "keep":
        issues.append("Identify a pilot with a checked output on the current recipe.")
    else:
        profile = pilot.get("profile")
        if not _text(profile) or any(plan.get(i, {}).get("profile") != profile or any(
            (plan.get(i, {}).get("basis") or {}).get(k) != pilot["basis"][k] for k in ("recipe", "settings", "check")
        ) for i in ids):
            issues.append("Use a checked pilot for each workload profile, recipe, settings and output check.")
    for item in ids:
        candidate = plan.get(item, {})
        basis = candidate.get("basis") or {}
        if not _count(candidate.get("count")) or any(not _text(basis.get(key)) for key in BASIS):
            issues.append(f"Complete the expected count and basis for {item}.")
    for key, message in (("representative", "Record why the pilot covers the proposed inputs, including the heavy case."),
                         ("measurement_ref", "Cite the measurements used for the estimate."),
                         ("limits_ref", "Cite the current resource limits for this proposal."),
                         ("owner", "Name the person or group that can approve the batch.")):
        if not _text(request.get(key)):
            issues.append(message)
    result["owner"] = request.get("owner") if _text(request.get("owner")) else ""
    measured, limits = request.get("measured"), request.get("limits")
    if not isinstance(measured, dict) or not isinstance(limits, dict):
        issues.append("Supply measured pilot usage and current resource limits.")
        return result
    job_fields = ("wall_seconds", "memory_mib", "output_mib", "scratch_mib", "output_files", "scratch_files")
    cap_fields = ("wall_seconds", "memory_mib", "free_mib", "free_files", "parallel")
    invalid = [f"measured.{key}" for key in job_fields if not _count(measured.get(key), int(key in job_fields[:2]))]
    invalid += [f"limits.{key}" for key in cap_fields if not _count(limits.get(key))]
    if not _count(request.get("parallel"), 1):
        invalid.append("parallel")
    if "min_job_seconds" in limits and not _count(limits["min_job_seconds"]):
        invalid.append("limits.min_job_seconds")
    priced = setting == "aws" or any(k in limits for k in ("budget_minor", "currency")) or "cost_minor" in measured
    if priced:
        if not _count(measured.get("cost_minor")) or not _count(limits.get("budget_minor")) or not _text(limits.get("currency")):
            invalid.append("measured.cost_minor / limits.budget_minor / limits.currency")
    shared_memory = setting == "local" or "shared_memory_mib" in limits
    if shared_memory and not _count(limits.get("shared_memory_mib")):
        invalid.append("limits.shared_memory_mib")
    if invalid:
        issues.append("Supply valid whole units for " + ", ".join(invalid) + ".")
        return result
    count = len(ids)
    live = min(request["parallel"], count)
    waves = (count + live - 1) // live
    space = count * measured["output_mib"] + live * measured["scratch_mib"]
    files = count * measured["output_files"] + live * measured["scratch_files"]
    result["estimates"] = {"jobs": count, "concurrent": live, "waves": waves,
                           "elapsed_seconds": waves * measured["wall_seconds"],
                           "worker_seconds": count * measured["wall_seconds"], "space_mib": space, "files": files}
    comparisons = [(live, limits["parallel"], "concurrent jobs"), (space, limits["free_mib"], "MiB of storage"),
                   (files, limits["free_files"], "file slots"), (measured["memory_mib"], limits["memory_mib"], "MiB of memory per job"),
                   (measured["wall_seconds"], limits["wall_seconds"], "seconds per job")]
    if shared_memory:
        memory = live * measured["memory_mib"]
        result["estimates"]["shared_memory_mib"] = memory
        comparisons.append((memory, limits["shared_memory_mib"], "MiB of shared memory"))
    if measured["wall_seconds"] < limits.get("min_job_seconds", 0):
        issues.append("Group short jobs or reduce dispatch pressure under this site's minimum job length.")
    if priced:
        spend = count * measured["cost_minor"]
        result["estimates"].update(cost_minor=spend, currency=limits["currency"])
        comparisons.append((spend, limits["budget_minor"], "minor currency units"))
    issues.extend(f"The proposal needs {need} {unit}. The available limit is {cap}." for need, cap, unit in comparisons if need > cap)
    for need, cap, unit in comparisons:
        if need == cap and need > 0 and unit != "concurrent jobs":
            result["warnings"].append(f"The estimate uses all {cap} {unit}. Allow headroom for variation.")
    if not issues:
        result["state"] = "owner_review"
    return result


def review(packet, root):
    if not isinstance(packet, dict) or packet.get("format") != EVIDENCE:
        raise TaosError(f"Expected a {EVIDENCE} packet.")
    question, setting = packet.get("question"), packet.get("setting")
    if not _text(question) or not isinstance(setting, str) or setting not in SETTINGS:
        raise TaosError("Name the research question and one supported setting.")
    plan = _index(packet.get("expected"), "expected")
    attempts = _index(packet.get("returns", []), "returns")
    if not plan:
        raise TaosError("List at least one expected output from the input manifest.")
    for key, row in plan.items():
        if row.get("basis") is not None and not isinstance(row["basis"], dict):
            raise TaosError(f"The basis for {key} must be an object.")
    manifest = packet.get("manifest")
    inventory = ""
    if not isinstance(manifest, dict) or not _text(manifest.get("reference")) or not _count(manifest.get("total"), 1):
        inventory = "Cite the source manifest and its independent count of expected outputs."
    elif manifest["total"] != len(plan):
        inventory = f"The manifest declares {manifest['total']} expected outputs. The packet names {len(plan)}."
    files = EvidenceFiles(Path(root))
    rows = {key: _row(output, attempts.get(key, {}), files) for key, output in plan.items()}
    accounting = _accounting(packet.get("accounting"), files, plan)
    unexpected = sorted(set(attempts) - set(plan))
    batch = _batch(packet.get("batch"), plan, rows, setting)
    if batch is not None and inventory:
        batch["state"] = "hold"
        batch["issues"].append(inventory)
    if batch is not None and unexpected:
        batch["state"] = "hold"
        batch["issues"].append("Reconcile returns outside the manifest before expanding this batch.")
    if inventory:
        next_step = inventory
    elif unexpected:
        next_step = "Reconcile returns outside the manifest: " + ", ".join(unexpected) + "."
    else:
        next_step = ""
        for action in ("inspect", "wait", "retry"):
            first = next((r for r in rows.values() if r["action"] == action), None)
            if first:
                next_step = f"{first['id']}: {first['reason']}"
                break
        if not next_step:
            if batch:
                next_step = batch["issues"][0] if batch["issues"] else f"Take this exact batch to {batch['owner']} for approval."
            elif all(r["action"] == "keep" for r in rows.values()):
                next_step = "Reuse the checked outputs listed below."
            else:
                next_step = "Define one representative pilot and its limits with the resource owner."
    canonical = json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return {"format": REPORT, "question": question, "setting": setting, "next": next_step,
            "packet_sha256": hashlib.sha256(canonical).hexdigest(),
            "reviewer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "accounting": accounting, "outputs": list(rows.values()), "manifest_issue": inventory, "unexpected": unexpected, "batch": batch, "scope": SCOPE}


def _decode(data):
    def unique_keys(pairs):
        fields = {}
        for key, value in pairs:
            if key in fields:
                raise TaosError(f"Conflicting duplicate JSON field: {key!r}.")
            fields[key] = value
        return fields

    def invalid_number(value):
        raise TaosError(f"Expected a finite JSON value, received {value}.")

    return json.loads(data, object_pairs_hook=unique_keys, parse_constant=invalid_number)


def read_packet(path):
    try:
        if not path.is_file() or path.stat().st_size > LIMIT:
            raise TaosError("Choose a local JSON packet of at most 16 MiB.")
        return _decode(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as exc:
        raise TaosError(f"Could not read the evidence JSON: {exc}") from exc


def _accounting(reference, files, plan):
    """Only sum elapsed worker time from distinct attempts in the hash-checked record."""
    result = {"worker_seconds": None, "attempts": None, "outputs": None, "sha256": None,
              "reason": "This packet has no retained worker accounting."}
    if reference is None:
        return result
    if not isinstance(reference, dict):
        return dict(result, reason="Supply a local accounting file and its SHA-256.")
    name = reference.get("file")
    problem = files.check(name, reference.get("sha256"), retain=True)
    if problem:
        return dict(result, reason=problem)
    try:
        record = _decode(files.retained[name].decode("utf-8"))
        if not isinstance(record, dict) or record.get("format") != "taos.hpc.accounting.v1":
            raise TaosError("Expected a taos.hpc.accounting.v1 record.")
        attempts = _index(record.get("attempts"), "accounting attempts", private_ids=True)
        if not attempts:
            raise TaosError("The accounting file has no observed attempts.")
        outputs = set()
        seconds = 0
        for attempt in attempts.values():
            output = attempt.get("output")
            if not _text(output) or output not in plan or not _count(attempt.get("worker_seconds")):
                raise TaosError("Each attempt needs a listed output and nonnegative whole worker seconds.")
            outputs.add(output)
            seconds += attempt["worker_seconds"]
        if not _count(seconds):
            raise TaosError("The sum exceeds the supported whole-second range.")
    except (TaosError, ValueError, RecursionError) as exc:
        return dict(result, reason=f"Cannot use the accounting record. {exc}")
    return {"worker_seconds": seconds, "attempts": len(attempts), "outputs": len(outputs),
            "sha256": reference["sha256"], "reason": ""}


def accounting_line(measured, expected):
    if measured["worker_seconds"] is None:
        return "Worker time unknown. " + measured["reason"]
    return (f'{measured["worker_seconds"]:,} recorded worker-seconds across {measured["attempts"]} '
            f'attempt(s) covering {measured["outputs"]} of {expected} listed outputs.')


def register(verbs):
    parser = verbs.add_parser("hpc", help="inspect a compute campaign before choosing what to run")
    sub = parser.add_subparsers(dest="hpc_action", required=True)
    prompt = sub.add_parser("brief", help="give your agent a read-only inspection brief")
    prompt.add_argument("--question", required=True)
    prompt.add_argument("--setting", choices=SETTINGS, required=True)
    prompt.set_defaults(func=lambda args, paths: print(brief(args.question, args.setting)))
    inspect = sub.add_parser("review", help="compare the planned outputs with a local evidence packet")
    inspect.add_argument("packet", type=Path)
    inspect.add_argument("--json", action="store_true", help="return a report the HPC page can open")
    inspect.add_argument("--task", help="record the checked summary on this project task")
    inspect.add_argument("--campaign", help="stable campaign name within the task (default: primary)")
    inspect.add_argument("--agent", help="project actor filing this review (default: human)")
    inspect.set_defaults(func=_command)


def _command(args, paths):
    report = review(read_packet(args.packet), args.packet.parent)
    if args.task:
        from . import progress

        progress.record(paths, args.task, args.campaign or "primary", args.agent or "human", report)
    elif args.campaign is not None or args.agent is not None:
        raise TaosError("Give --task to associate a campaign or actor with a project task.")
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return
    print(report["next"])
    for row in report["outputs"]:
        print(f"  {row['id']}  {LABELS[row['action']]}  {row['reason']}  {row['reference']}")
    if report["unexpected"]:
        print("Unlisted returns: " + ", ".join(report["unexpected"]))
    batch = report["batch"]
    if batch:
        print("Batch: " + ("Hold" if batch["state"] == "hold" else "Ready for owner review"))
        for issue in batch["issues"] + batch["warnings"]:
            print("  " + issue)
        if batch["estimates"]:
            print("  Estimated batch use: " + ", ".join(f"{key}={value}" for key, value in batch["estimates"].items()))
    print(accounting_line(report["accounting"], len(report["outputs"])))
    if args.task:
        print(f"Project progress: ./taos usage progress --task {args.task}")
    print("Evidence packet SHA-256: " + report["packet_sha256"])
    print(report["scope"])
