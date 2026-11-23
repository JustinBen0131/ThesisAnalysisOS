"""Render what the next agent is handed on the homepage from the saved setting-change replay."""

import hashlib
import json
import re
from html import escape

SETTING_RECORD = "evals/results/followups/setting-change.json"
SETTING_RUNNER = "evals/replay_setting_change.py"
SETTING_FIXTURE = "examples/instrument_setting"
SETTING_DOWNLOAD = "records/setting-change.json"
# What the page stands on, and the stand-in project's files kept with the source snapshot.
SETTING_SOURCES = (SETTING_RECORD, SETTING_RUNNER, "site/setting_change_exhibit.py")
SETTING_FIXTURE_FILES = (SETTING_FIXTURE + "/README.md", SETTING_FIXTURE + "/model/settings.json",
                         SETTING_FIXTURE + "/model/check_response.py", SETTING_FIXTURE + "/notes/lab_notes.txt")
# The page's plain words for the standing the software reports once the setting has changed.
STANDING = {"stale": "needs rechecking"}
# The answers the homepage repeats in its own words. The build stops when the record says otherwise.
REPEATED = {"before": "holds", "control": "holds", "after": "stale", "rerun": "holds", "changed": "model/settings.json"}


def load_setting_change(repo, record_path=None):
    """Check every recorded source and every answer the homepage repeats before showing them."""
    root = repo.resolve()
    raw = (record_path if record_path is not None else root / SETTING_RECORD).read_bytes()
    record = json.loads(raw.decode("utf-8"))
    if record.get("schema") != "setting-change-replay/1":
        raise ValueError("Unsupported setting-change record.")
    expected = {SETTING_RUNNER, "bootstrap/answers.example.json"}
    expected.update(p.relative_to(root).as_posix() for p in (root / "taos_core").glob("*.py"))
    expected.update(p.relative_to(root).as_posix() for p in (root / SETTING_FIXTURE).rglob("*")
                    if p.is_file() and "__pycache__" not in p.parts)
    sources = record.get("sources")
    if not isinstance(sources, dict) or set(sources) != expected:
        raise ValueError("Setting-change sources do not match the input roster.")
    for name, fingerprint in sources.items():
        source = (root / name).resolve()
        source.relative_to(root)
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != fingerprint:
            raise ValueError("The setting-change record is stale: {0} changed. Run {1} again.".format(
                name, SETTING_RUNNER))
    handoff = record.get("handoff")
    if (record.get("expectation_mismatches") or not isinstance(handoff, dict)
            or any(handoff.get(key) != value for key, value in REPEATED.items())
            or not str(handoff.get("next", "")).startswith("run the checks on the files as they are")):
        raise ValueError("The setting-change record no longer says what the homepage repeats.")
    record["fingerprint"] = hashlib.sha256(raw).hexdigest()
    return record


def _lines(record, name, *words):
    row = next(step for step in record["steps"] if step["id"] == name)
    return [line for line in row["printed"] if not words or any(word in line for word in words)]


def _read(text):
    found = re.fullmatch(r"fed (\d+), read (\d+), correction (on|off)", text)
    if not found:
        raise ValueError("The setting-change record holds a reading the homepage cannot repeat.")
    return found.group(2), found.group(1)


def setting_change_run(record):
    """The commands and answers shown under the saved record, as plain text."""
    told = record["handoff"]
    edit = next(step for step in record["steps"] if step["id"] == "setting-switched")
    noted = next(step for step in record["steps"] if step["id"] == "notes-edited")
    before, fed = _read(told["readings"]["before"])
    after, _ = _read(told["readings"]["after"])
    why = "$ taos why " + told["task"]
    shown = [why] + ["  " + line for line in _lines(record, "before", "check ")]
    shown += ["", noted["file"] + " is edited. The check never read it.", why]
    shown += ["  " + line for line in _lines(record, "control", "check ")]
    shown += ["", "{0} is edited: the correction goes from {1} to {2}.".format(
        edit["file"], edit["before"]["correction"], edit["after"]["correction"]), why]
    shown += ["  " + line for line in _lines(record, "after")]
    shown += ["", "What an agent picking the task up is shown.", "$ taos capsule " + told["task"]]
    shown += ["  " + line for line in _lines(record, "pickup")]
    shown += ["", "The check is run again on the new setting. It passes: it read {0} of {2} before and reads {1} of {2} now.".format(
        before, after, fed), why]
    shown += ["  " + line for line in _lines(record, "rerun", "check ")]
    return "\n".join(shown)


def next_agent_fields(record, root, source):
    """The fields of site/next_agent.html that repeat the record. `source` links a repository file."""
    return {
        "standing_label": escape(STANDING[record["handoff"]["after"]]),
        "saved_record": (
            '<p class="prov">A present-day run of the same pattern with ThesisAnalysisOS {version}, on a small '
            'stand-in project with made-up readings. It is not a record of the original project.</p>\n'
            '<pre class="run" tabindex="0" aria-label="The recorded commands and answers"><code>{run}</code></pre>\n'
            '<p class="prov"><strong>Recorded by the software:</strong> that the check needs rechecking, the file that '
            'changed and the next step. <strong>Written by the team:</strong> comparing with its reference, and the '
            'decision. A pass does not say which setting is right. The standing is worked out each time the record '
            'is asked, not by a watcher.</p>\n'
            '<p class="prov links"><a href="{root}{download}">The recorded run</a> · the script {runner} · '
            'the stand-in project {fixture} · record <code>{mark}</code></p>').format(
                version=escape(str(record["taos_version"])), run=escape(setting_change_run(record)),
                root=root, download=SETTING_DOWNLOAD, runner=source(SETTING_RUNNER),
                fixture=source(SETTING_FIXTURE + "/README.md"), mark=record["fingerprint"][:12]),
    }
