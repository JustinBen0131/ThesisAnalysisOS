"""Attach concrete examples to the public graph, with local line-addressable evidence."""
import ast
import json
import re
from pathlib import Path
from urllib.parse import quote


# Each example points inside the named test, to the assertion a visitor can inspect.
_TESTS = (
    ("The first-minute reads run locally", "On a fresh demo, the project summary, applicable review rule, check status and task brief were readable with networking and external programs unavailable.", "first_minute_reads_run_without_network_or_external_programs", 'self.assertIn("Measure g from the six swings"'),
    ("A recorded result", "A task has never run its check. Its record says the outcome is unknown and gives the reason.", "an_open_task_claims_nothing", 'never run for this task'),
    ("A passed check", "A check passes. Editing the project's version number immediately makes that pass unavailable.", "a_pass_does_not_cover_a_file_edited_afterwards", 'self.assertIsNone(gates.fresh_pass'),
    ("The answer names", "Editing the project settings after a check puts Cargo.toml in the reason shown to the next reviewer.", "closed_work_stands_until_a_file_changes_and_the_reason_names_the_file", 'self.assertIn("Cargo.toml"'),
    ("No route moves", "A task closed during a test-service outage keeps the waiver reason. Its closure stays unverified until the check runs.", "a_waived_closure_is_unverified_until_the_check_runs", 'without a holding check (CI is down)'),
    ("A result is shared", "Two tasks ask for the same check on identical files. The execution counter records one run.", "two_tasks_share_one_verified_result_while_the_files_are_the_same", 'self.executions()'),
    ("A change to a file", "Editing a notes file that belongs to no declared group leaves the check's status unknown.", "a_change_nobody_declared_is_unknown_and_never_rounded_to_fine", 'outside every declared domain'),
    ("A declared domain", "A data file is excluded from Git. Changing its reading still invalidates the check that listed its folder.", "an_input_git_ignores_is_still_part_of_what_a_check_stood_on", 'self.assertIsNone(gates.fresh_pass'),
    ("A check marked isolated", "The check reads a copy of the analysis code and creates a file. When it finishes, that new file is absent from the original workspace.", "an_isolated_check_sees_only_what_it_declared_and_leaves_nothing_behind", 'self.assertFalse((self.ws / "made.txt").exists())'),
    ("An acceptance records", "A reviewer accepts a timing table. After an input changes, the check passes again. The edited version still needs a fresh approval from the reviewer.", "acceptance_is_of_one_version_and_does_not_carry_over", 'self.assertEqual(part(view, "acceptance")["state"], basis.STALE)'),
    ("A work product", "Changing a timing measurement in bench.csv marks the plot that used it as outdated. A summary with no listed inputs has an unknown status.", "a_work_product_is_current_while_its_declared_inputs_are_the_same_bytes", 'bench.csv changed'),
    ("A new or lapsed", "A task was closed before its reviewer asked for the median of five runs. The new instruction appears in the reason for reviewing the closure again.", "a_new_instruction_makes_the_closure_stale_and_is_quoted", 'self.assertIn("Report the median of five runs"'),
    ("The instruction that", "A January calibration query returns reference A. A February query returns its replacement, reference B.", "a_later_replacement_does_not_erase_the_earlier_answer", 'self.quotes("calibration", "2026-02-15")'),
    ("A replacement governs", "A release temporarily requires one reviewer. On March 9, after the exception ends, the earlier two-reviewer rule applies again.", "a_temporary_replacement_gives_the_rule_back_when_it_lapses", 'self.quotes("release", "2026-03-09")'),
    ("What governs a task", "At startup the agent sees the instruction to benchmark on the large fixture and a reminder to warm the cache. The other task's parser instruction is left out.", "start_shows_what_stands_what_was_told_and_what_was_learned", 'self.assertIn("lesson:'),
    ("A reminder shown", "Three replies already include units. All three receive the reminder about units, and the repeat-mistake count stays at zero.", "a_reminder_shown_for_correct_work_is_not_a_repeated_mistake", 'self.assertEqual(sum(repeat_count'),
    ("A setup is credited", "The agent starts and finishes a task. With no observation of which setup ran, the session counts once and the setups receive zero credit.", "an_unobserved_profile_earns_no_credit", 'self.assertEqual(credited, 0)'),
    ("A lapsed lease", "An agent's one-hour assignment expires. Another agent takes the task, and the first agent's attempt to renew the old assignment is refused.", "a_lapsed_owner_cannot_come_back_after_reassignment", 'self.assertEqual(holders,'),
    ("A refused start", "A repair is blocked on another task. When an agent tries to start it, the request is refused and it acquires no assignment.", "a_refused_start_takes_nothing", 'self.assertEqual([c for c in claims.'),
    ("A label is read", "A replay row records a load with no outcome label. It contributes zero to the count of harmless outcomes.", "an_unlabelled_case_is_not_counted_as_harmless", 'self.assertEqual(result["harmless"], 0)'),
    ("A decision-bank run", "A reader gets one answer right in one condition and four in another. The scored record retains the submitted answers and their fingerprint.", "scoring_needs_sealed_lines_and_qualified_reader", 'self.assertEqual(result["answers"]["O"]'),
    ("A change is not confirmed", "A proposed speedup predicts a time saving. Entering an observed time without a source is refused, even when the value falls in the predicted range.", "a_change_is_not_confirmed_by_a_number_from_nowhere", 'with self.assertRaises(TaosError):'),
    ("A number quoted", "The test substitutes a different fingerprint for the measured code. The result becomes outdated and the reason names the changed file.", "a_recorded_number_goes_stale_when_the_code_it_measured_changes", 'the code it measured changed: evals/measured.py'),
    ("An isolated check sees", "A check needs a tuning setting from the caller. It passes in the caller's environment and fails when run in isolation.", "an_isolated_check_does_not_see_the_environment", 'self.assertFalse(gates.run'),
    ("Each isolated result", "The test tries a local network connection and an undeclared workspace file. It checks whether the run reported the access limits this machine could enforce.", "the_record_says_what_was_closed_and_it_was", 'self.assertEqual("network" in closed'),
    ("The setup answers", "The setup lists source and data folders as inputs to a fit. The generated settings retain both patterns and request an isolated check.", "setup_can_say_what_a_check_reads", 'self.assertEqual(config["basis"]["domains"]'),
    ("No row of this file", "A test reads the public claim register and requires an empty list of rows with a failed source check.", "no_claim_names_something_that_is_not_there_or_misquotes_a_recorded_run", 'self.assertEqual([(row["claim"]'),
    ("The demo runs", "The demo first omits the style file from a check's inputs. The check fails, then passes when the missing input is listed.", "it_runs_from_a_clean_copy_and_shows_each_idea_with_real_output", 'declared, the same check passes'),
)


def _one(values, context):
    values = list(values)
    if len(values) != 1:
        raise ValueError(f"Expected one {context}, found {len(values)}")
    return values[0]


class _Sources:
    def __init__(self, repo):
        self.repo = Path(repo)
        self.files = {}
        self.tests = {}
        for path in sorted((self.repo / "tests").glob("test_*.py")):
            name = path.relative_to(self.repo).as_posix()
            for node in ast.walk(ast.parse("\n".join(self.lines(name)))):
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                    self.tests.setdefault(node.name[5:], []).append((name, node.lineno, node.end_lineno))

    def lines(self, name):
        if name not in self.files:
            self.files[name] = (self.repo / name).read_text(encoding="utf-8").splitlines()
        return self.files[name]

    def data(self, name):
        return json.loads("\n".join(self.lines(name)))

    def link(self, name, snippet, label, span=None):
        lines = self.lines(name)
        first, last = span or (1, len(lines))
        number = _one((i for i in range(first, last + 1) if snippet in lines[i - 1]),
                      f"source line containing {snippet!r} in {name}:{first}-{last}")
        return {"label": label, "path": name, "line": number,
                "href": f"source/files/{quote(name, safe='/')}.html#L{number}"}

    def test(self, name, assertion):
        path, first, last = _one(self.tests.get(name, ()), f"test named {name}")
        return self.link(path, assertion, "Read the test assertion", (first, last))


def _example(kind, text, *links):
    return {"kind": kind, "text": text, "links": list(links)}


def _measured(src):
    def record(stem):
        name = f"evals/results/{stem}.json"
        return name, src.data(name)

    def case(data, field, key, value):
        return _one((row for row in data[field] if row[key] == value), f"{field} row with {key}={value}")

    def field_link(path, field, value, label):
        return src.link(path, f'"{field}": {json.dumps(value)}', label)

    def observed(text, path, snippet, label="See the recorded counts"):
        return _example("measured", text, src.link(path, snippet, label))

    rev_path, rev = record("at_revision")
    old = rev["revisions"]["89f36ce"]
    revision = observed(f"On the second earlier version, {old['did_not_pass']} of {old['ran']} checks did not pass. One concerned a check reading a file it never listed.",
                        rev_path, '"89f36ce":')
    if "test_a_check_cannot_pass_on_a_file_it_did_not_declare" not in old["names"]:
        raise ValueError("The earlier release record no longer contains the unlisted-input example")

    mutation_path, mutation = record("mutations")
    removed = "acceptance: it carries over to an edited version"
    if removed not in mutation["names"] or removed in mutation["missed"]:
        raise ValueError("The recorded removal no longer demonstrates the acceptance protection")
    mutations = observed(f"One deliberate change let a person's approval carry over after an edit. The tests caught it among {mutation['caught']} of {mutation['faults']} seeded faults.",
                         mutation_path, json.dumps(removed), "See the removed protection")
    rp, reuse = record("reuse_frontier")

    def reuse_row(policy, text):
        row = case(reuse, "rows", "policy", policy)
        return _example("measured", text.format(**row, total=reuse["relied_on"]),
                        field_link(rp, "policy", policy, "See the recorded policy and counts"))

    proper = reuse_row("TAOS, 12 domain(s) declared",
                       "Across {total} check requests, comparing the listed inputs led to {executions} runs and {wrong} outdated results being reused.")
    age = reuse_row("rerun when older than 8 consultations",
                    "With an eight-request age limit, checks ran {executions} times. An outdated result was used {wrong} times in {total} requests.")
    missing = reuse_row("TAOS, each check hides one folder it reads",
                        "Each check used one folder it had left off its list. Only {executions} checks ran, but {wrong} of {total} answers reused outdated results.")
    isolated = reuse_row("TAOS, checks isolated, each hides one folder",
                         "Each check needed a folder left out of its isolated copy. Of {executions} attempts, {passed} passed.")
    timing = reuse["timing"]
    small = case(timing, "upkeep", "files", 48)
    large = case(timing, "upkeep", "files", 4800)
    pairs = timing["isolating_one_execution"]
    if "reference_ratio" in small:
        consultation = (f"Checking six saved results took {small['reference_ratio']['median']:.2g} times as long as a fresh reference check "
                        f"with {small['files']} files, and {large['reference_ratio']['median']:.2g} times as long with {large['files']:,} files on this machine.")
        isolation = (f"Across {pairs['pairs']} matched edits, the median difference between an isolated and open check took "
                     f"{pairs['added_reference_ratio']['median']:.2g} reference-check times on this machine.")
    else:
        consultation = (f"On the test machine, checking {small['files']} files took {1000*small['seconds']:.1f} ms. "
                        f"Checking {large['files']:,} took {1000*large['seconds']:.1f} ms.")
        isolation = f"On the test machine, isolation added a median of {1000*pairs['median_seconds']:.1f} ms across {pairs['pairs']} paired runs."
    upkeep = observed(consultation, rp, '"upkeep":', "See the file counts and times")
    paired = observed(isolation, rp, '"isolating_one_execution":', "See the paired timings")

    model_path, model = record("model_evaluation")
    policy_path = "examples/model_evaluation/policy.json"
    threshold = src.data(policy_path)["flag_if_score_at_least"]
    change = case(model, "cases", "id", "shared-threshold")
    after = change["counts"]["pooled"]
    before = dict(zip(model["cell_order"], model["baseline_counts"]["pooled"]))
    if (change["executed"] != ["A", "B", "pooled"] or
            set(change["old_receipts"].values()) != {"stale"} or
            set(change["result_after_consultation"].values()) != {"fails"} or
            before["tp"] + before["fn"] != after["tp"] + after["fn"]):
        raise ValueError("Read the changed outcomes for the shared threshold before describing them")
    threshold_test = _example("measured",
        f"Raising the flagging threshold from {threshold} to {change['threshold']} reduced detection from {before['tp']} to {after['tp']} of {after['tp']+after['fn']} known faults. Both instrument checks and the combined check ran again and failed.",
        src.link(policy_path, '"flag_if_score_at_least"', "See the original threshold"),
        field_link(model_path, "id", "shared-threshold", "See what happened after the change"))

    mp, measurement = record("measurement_audit")
    fit = case(measurement, "cases", "id", "row-6-1.05")
    baseline = case(measurement, "cases", "id", "baseline")
    if fit["retained"] != "stale" or fit["fresh_exit"] == 0:
        raise ValueError("Read the revised outcome of the single-swing correction")
    pendulum = observed(f"One corrected swing time moved the fitted gravity from {baseline['g']:.2f} to {fit['g']:.2f} m/s². The earlier pass expired and the fresh check failed.",
                        mp, '"id": "row-6-1.05"', "Read the corrected-fit observation")
    sp, session = record("session_footprint")
    capsule = session["surfaces"]["task_capsule"]
    reading = observed(f"One task brief in the demo was {capsule['lines']} lines and {capsule['bytes']:,} UTF-8 bytes when requested.",
                       sp, '"task_capsule": {', "Inspect the saved brief and its text size")
    hp, handoff = record("handoff_audit")
    restored = case(handoff, "observations", "id", "restore-exact-bytes")
    if not (restored["csv_exact_original"] and restored["before"] == "holds" and restored["reused_gates"]):
        raise ValueError("Read the revised outcome of restoring the original data")
    hand = observed("Later in the handoff, restoring the exact original readings allowed the next task to reuse the passing fit.",
                    hp, '"id": "restore-exact-bytes"', "Read the restoration observation")
    fp, followup = record("followups/instrument-imbalance")
    both = case(followup, "cases", "id", "both")
    pool = both["groups"]["pooled"]
    imbalance = observed(f"After both corrections the combined detector caught {pool['counts']['tp']} of {pool['reference_faults']} faults. Giving each instrument equal weight gave {both['equal_group_mean']}.",
                         fp, '"id": "both"', "Read the two-correction result")
    cp, setting = record("followups/setting-change")
    told = setting["handoff"]
    switched = observed(f"After {told['changed']} was edited, the earlier pass of the {told['check']} check read {told['after']}. "
                        "Run again on the new setting, the check passed.",
                        cp, '"id": "after"', "Read what the record answered")
    studies = {rev_path: revision, mutation_path: mutations, rp: proper, model_path: threshold_test,
               mp: pendulum, hp: hand, fp: imbalance, cp: switched, sp: reading}
    claims = {"Reading one demo session": reading, "Earlier releases had": revision, "The tests notice": mutations, "Reuse by basis": proper,
              "Age limits trade": age, "In the open": missing, "Isolated, a check": isolated}
    if any(line.startswith("| Cost of consulting") for line in src.lines("docs/CLAIMS.md")):
        claims.update({"Cost of consulting": upkeep, "Added cost of isolating": paired})
    else:
        claims.update({"Asking costs time": upkeep, "Isolating a check costs": paired})
    return claims, studies, threshold_test


def _file_examples(src, claims, studies, threshold):
    files = dict(studies)
    files["examples/model_evaluation/policy.json"] = threshold
    prediction_path = "examples/model_evaluation/predictions.json"
    prediction = src.data(prediction_path)
    row = _one((item for item in prediction["cases"] if item["id"] == "offsetting-score-corrections"),
               "paired-score forecast")
    order = prediction["cell_order"]
    pool = dict(zip(order, row["counts"]["pooled"]))
    if row["fail"] != ["A"] or row["sensitivity_direction"] != ["down", "up", "same"]:
        raise ValueError("Read the revised forecast for the two score corrections")
    files[prediction_path] = _example("forecast",
        f"The saved prediction says that after two score corrections, only instrument A will fail. Together the instruments will still detect {pool['tp']} of {pool['tp']+pool['fn']} known faults.",
        src.link(prediction_path, '"id": "offsetting-score-corrections"', "Read the saved prediction"),
        src.link("docs/MODEL_EVALUATION.md", "| Also correct B04", "Compare the observed result"))
    files[".codex/hooks.json"] = _example("tested",
        "Before a shell command, Codex calls a guard. One test submits a force-push command to the guard and checks that it refuses.",
        src.link(".codex/hooks.json", '"matcher": "Bash"', "See the shell-command setting"),
        src.test("history_and_money_denied", 'git push --force origin feature'))
    path = "bootstrap/answers.example.json"
    files[path] = _example("documented",
        "The sample project asks for a test run and a formatting check. Its setup answers reserve merging to the main branch for a person.",
        src.link(path, '"command": "cargo test"', "See the sample checks"),
        src.link(path, '"merge to main"', "See the human-only actions"))
    path = "bootstrap/answers.schema.json"
    files[path] = _example("tested", claims["The setup answers"]["text"],
        src.link(path, '"depends_on":', "See how checks list their inputs"), *claims["The setup answers"]["links"])
    path = "bootstrap/rates.json"
    files[path] = _example("tested",
        "The example estimates the cost of three recorded model calls by pricing each call at the rate for its model. The result is an estimate in US dollars.",
        src.link(path, '"currency": "USD"', "Read the rates and their date"),
        src.test("mixed_model_pricing_and_inclusive_codex_cache", 'self.assertEqual(agents["claude"]["cost"]["amount"], 21.0)'))
    path = "evals/model_evaluation.schema.json"
    files[path] = _example("documented",
        "Each instrument report records four counts in a fixed order. That lets a reader distinguish missed faults from false alarms.",
        src.link(path, '"cell_order": {', "See the required counting order"),
        src.link(prediction_path, '"cell_order": [', "See those fields in the fixture"))
    for stem, excerpt, explanation in (
        ("CLAIMS", "taos start` claims the task", "Starting a task records its owner and the part of the project it can edit."),
        ("CONTEXT", "taos policy route", "An agent can look up the instructions that apply to the request in front of it."),
        ("CONTROL", "the human's explicit choices bound", "The person sets the limits within which an agent chooses how much work to do."),
        ("DECOMPOSITION", "one session can move it", "A job is small enough to hand off when someone can say what would make it ready for review."),
        ("DUPLICATE_WORK", "taos task find", "Before starting, an agent can search for the earlier task and read its evidence."),
        ("EVIDENCE", "Test or command output pasted", "A task can preserve the actual check output for the next reviewer."),
        ("GATES", "run what needs running", "The project names the commands a piece of work must pass before review."),
        ("GIT", "prints the lane", "Starting a task tells an agent which working directory to use."),
        ("HANDOFFS", "Fix the panic on empty generic bounds", "A sample handoff names the specific defect the next agent is taking over."),
        ("HARD_STOPS", "stop and ask. If you see one", "If work needs a secret, the agent asks the person how to proceed."),
        ("OBJECTIVE", "Maximise verified progress", "The project judges progress by the useful work a person can verify for the attention it took."),
        ("OPERATING_LOOP", "Map the human's request to exactly one task", "An incoming request is matched to one task before an agent begins."),
        ("PANEL", "served on the loopback interface", "The optional project dashboard runs on the user's own computer."),
        ("REPO_SPLIT", "your tasks, claims, events, handoffs, and gate runs stay", "A project can use the public software while keeping its own task and review history private."),
        ("REVIEW", "Check the deliverable against them", "Reviewers compare the delivered work with the request and its required checks."),
        ("SCIENCE", "Do not grade your own change", "A different agent or a person assesses a proposed change against the prediction recorded for it."),
        ("SELF_ITERATION", "The human reviews the proposal", "An agent can suggest a new check. The operator can decline it, install it, or retire it later."),
    ):
        path = f"policies/{stem}.md"
        files[path] = _example("documented", explanation, src.link(path, excerpt, "Read the policy passage"))
    for path, excerpt, explanation in (
        (".claude/settings.json", "hooks/session_start.py", "Claude Code can run the local status hook when a session opens."),
        ("kernels/KERNEL_INDEX.json", '"name": "OS_KERNEL"', "The index records which files the overview draws on, so a reader can check its sources."),
        ("atoms/promoted_atoms.json", '"id": "handoff-header-required"', "A saved check asks whether the latest handoff identifies its author, session, task and scope."),
        ("policies/ROUTING.yaml", "triggers: [review, check your work", "A request to review the work selects the project's review instructions."),
    ):
        files[path] = _example("documented", explanation, src.link(path, excerpt, "Inspect the setting"))
    files["policies/HPC.md"] = _example("tested",
        "Two sensor files kept all five readings between them. File C arrived empty, so only C went back for review.",
        src.link("examples/hpc/returns/C-transfer.txt", "Input manifest: 2 readings.", "Read the first delivery log"),
        src.test("checked_and_partial_outputs_remain_distinct", '("C", "retry", 0, 2)'))
    files["taos_core/policy.py"] = _example("tested",
        "A request to run the benchmark again brings up the rule for checking whether that work already exists.",
        src.test("route_picks_the_right_policies", 'self.assertIn("policies/DUPLICATE_WORK.md"'))
    files["taos_core/control.py"] = claims["A setup is credited"]
    files["taos_core/config.py"] = _example("tested",
        "The fit names an analysis input group missing from setup. Validation flags that name and the fit's earlier result has unknown status.",
        src.test("a_check_that_names_an_undeclared_domain_is_refused_not_trusted_forever",
                 'self.assertTrue(any("depends_on names analysis"'))
    aliases = {"bootstrap": "The setup answers", "rules": "The instruction that", "claims": "A lapsed lease",
               "gates": "A check marked isolated", "standing": "An acceptance records", "tasks": "An acceptance records",
               "basis": "The answer names", "anchors": "A change is not confirmed", "changes": "A change is not confirmed",
               "lessons": "A reminder shown", "bank": "A decision-bank run", "lifecycle": "What governs a task",
               "replay": "A label is read"}
    for module, claim in aliases.items():
        files[f"taos_core/{module}.py"] = claims[claim]
    files["taos_core/anchors.py"] = _example("tested",
        "Once the agent records its predicted range for a ratio, an attempt to replace that range is refused.",
        src.test("a_prediction_cannot_be_rewritten_once_made", "with self.assertRaises(TaosError):"))
    for stem, text, snippet in (
        ("AGENTS", "Before editing the parser, the agent can check whether another agent already holds that part of the project.", "# is it free"),
        ("CLAUDE", "Claude receives the same working contract as Codex. Its setup instructions point back to that shared document.", "Everything in it applies to you exactly as"),
        ("PRINCIPAL_KERNEL", "The setup guide gives a new agent a concrete instruction about reporting failed work.", "Report what is true, including what failed."),
        ("PROJECT_KERNEL", "The project guide has a place for the build and test commands a newcomer needs before editing code.", "commands beyond the gates"),
        ("workspace_block", "A linked project tells an agent where to find the shared task and how to check who is working there.", "before writing in an area another agent may hold"),
    ):
        path = f"taos_core/templates/{stem}.md.tmpl"
        files[path] = _example("documented", text, src.link(path, snippet, "Read the setup instructions"))
    passage = _one((line for line in src.lines("README.md")
                    if re.match(r"^\s*stale\s+", line) and "data/swings.csv" in line),
                   "README demo result naming the changed timing file")
    files["README.md"] = _example("documented",
        "The README shows which file changed when one swing was measured again. The saved fit used the earlier timing.",
        src.link("README.md", passage, "Read the README example"),
        src.test("it_runs_from_a_clean_copy_and_shows_each_idea_with_real_output", "stale    check fit: analysis changed: data/swings.csv"))
    files["docs/CLAIMS.md"] = claims["No row of this file"]
    path = "examples/transit/workflow.json"
    files[path] = _example("measured",
        "Two missing dispatch entries keep Tuesday’s rate pending. The incoming agent can open the task brief and see which entries it still needs.",
        src.link(path, '"tuesday-refusal": {', "Inspect the attempt to publish Tuesday’s rate"),
        src.link("evals/transit_workflow.py", "def run_history(", "See the commands that produced the workflow"))
    path = "examples/transit/adaptation/workflow.json"
    files[path] = _example("measured",
        "The next shift listed yesterday’s trips. Its new format check passed. Comparing the IDs with dispatch caught the mistake.",
        src.link(path, '"holdout_stale-check": {', "Inspect the format check on the old trip IDs"),
        src.link(path, '"changed-count": {', "Compare the independent dispatch count"))
    return files


def attach_policy_evidence(graph, repo):
    """Decorate and return the input graph; hrefs are relative to this site's root.

    Pass each evidence link's path to the build's local source viewer exporter.
    The kind separates test assertions, measured observations, documentation and forecasts.
    """
    src = _Sources(repo)
    claims = {key: _example("tested", text, src.test(method, assertion))
              for key, text, method, assertion in _TESTS}
    measured, studies, threshold = _measured(src)
    claims.update(measured)
    suite = _example("documented",
        "The CI configuration runs the suite across Linux, macOS and two Python versions. The public count comes from discovering the tests in this checkout.",
        src.link(".github/workflows/ci.yml", 'python: ["3.9", "3.12"]', "See the operating systems and versions"),
        src.link("evals/claims.py", "countTestCases()", "See how the tests are counted"))
    nodes = [node for node in graph["nodes"] if node["k"] == "c"]
    ledger = {}
    for line in src.lines("docs/CLAIMS.md"):
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == 4 and cells[3].startswith(("tested", "measured")):
            ledger[re.sub(r"[`*]", "", cells[0])] = line
    suite_row = _one((name for name in ledger if name.startswith(("The suite passes", "Cases collected by the self-test suite"))),
                     "test suite count row")
    claims[suite_row] = suite
    ordinary = [n["l"] for n in nodes if not n["l"].startswith("README.md repeats: ")]
    if len(ordinary) != len(set(ordinary)) or set(ordinary) != set(ledger) or len(ordinary) != len(claims):
        raise ValueError("The graph, claim register and concrete policy examples no longer match")
    readme_examples = {
        r"\d+ tests": suite,
        r"\d+ of \d+ fail at .+": measured["Earlier releases had"],
        r"\d+ of \d+ removals are caught": measured["The tests notice"],
        r"\d+ executions and \d+ wrong reuses": measured["Reuse by basis"],
        r"\d+ wrong reuses in \d+": measured["In the open"],
        r"\d+ of \d+ runs passed": measured["Isolated, a check"],
    }
    files = _file_examples(src, claims, studies, threshold)
    seen, repeated = set(), set()
    for node in graph["nodes"]:
        name = node["l"]
        if node["k"] == "c" and name in ledger:
            key = _one((k for k in claims if name.startswith(k)), f"policy example for {name!r}")
            if key in seen:
                raise ValueError(f"Ambiguous policy example for {key}")
            seen.add(key)
            example = claims[key]
            links = example["links"]
            if len(links) == 1:
                if key == "An acceptance records":
                    source = src.link("SECURITY.md", "reviewer name on a decision is supplied by the caller.",
                                      "Read what a reviewer label establishes")
                else:
                    source = src.link("docs/CLAIMS.md", ledger[name], "Read the full claim")
                links = [*links, source]
            node["evidence"] = _example(example["kind"], example["text"], *links)
        elif node["k"] == "c":
            phrase = name.removeprefix("README.md repeats: ")
            key = _one((pattern for pattern in readme_examples if re.fullmatch(pattern, phrase)),
                       f"README example for {name}")
            if key in repeated:
                raise ValueError(f"Duplicate public number matching {key}")
            repeated.add(key)
            line = _one((raw for raw in src.lines("README.md") if phrase in raw.replace("`", "")),
                        f"README passage quoting {phrase!r}")
            source = src.link("README.md", line, "Read the original README passage")
            example = readme_examples[key]
            node["evidence"] = _example(example["kind"], example["text"], source, example["links"][0])
        elif node["k"] in {"f", "r"}:
            if name in files:
                node["evidence"] = files[name]
            elif name.endswith((".json", ".yaml", ".yml", ".tmpl")) or name.startswith("policies/"):
                raise ValueError(f"Add a source-backed example for {name}")
    if seen != set(claims) or repeated != set(readme_examples):
        raise ValueError("Public claim examples are missing")
    return graph
