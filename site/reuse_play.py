"""The reuse experiment as something to play with: change a file and watch which check runs again.

`reuse_play` returns one block of static HTML for the homepage figure. It shows the state after the first recorded
change, so it reads correctly with scripts off. `assets/reuse.js` then lets a visitor change any folder, replay the
recorded changes and leave one folder off each check's list. `assets/reuse.css` styles it.

The picture is driven by the recorded experiment: the changes come from the recorded seed, and the build stops if
replaying them here does not land on the recorded totals.
"""
import html

import reuse_frontier

WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve")


def word(number):
    return WORDS[number] if 0 <= number < len(WORDS) else str(number)


def replay(trace, checks, reads, hide):
    """(checks run, outdated results used) for a list of changed folders. With `hide`, each check leaves the last
    folder it reads off its list, so a change there does not make it run again."""
    ran_at, touched_at, runs, outdated = [-1] * checks, [-1] * checks, 0, 0
    for step, folder in enumerate(trace):
        check = folder // reads
        touched_at[check] = step
        if not hide or folder % reads != reads - 1:
            ran_at[check] = step
            runs += 1
        outdated += sum(1 for k in range(checks) if ran_at[k] < touched_at[k])
    return runs, outdated


def reuse_play(run, finest, hidden, everything):
    """The interactive block. `run` is the recorded experiment; the other three are its rows for full lists, lists
    with one folder left off, and rerunning everything."""
    checks, folders, edits = run["checks"], run["folders"], run["edits"]
    reads = folders // checks
    trace = [folder for folder, _ in reuse_frontier.trace(edits, run["seed"])]
    if any(reuse_frontier.reads(check) != list(range(check * reads, check * reads + reads)) for check in range(checks)):
        raise ValueError("The reuse picture assumes each check reads its own run of folders.")
    if replay(trace, checks, reads, False) != (finest["executions"], finest["wrong"]) \
            or replay(trace, checks, reads, True) != (hidden["executions"], hidden["wrong"]) \
            or everything["executions"] != checks * edits:
        raise ValueError("The reuse picture no longer reproduces the recorded totals; fix it before publishing.")

    first = trace[0]
    width = 100.0 / reads
    units = []
    for check in range(checks):
        ran = first // reads == check
        wires = "".join('<path data-folder="{0}"{1} d="M{2:.1f} 42 L50 3"/><path class="spark" data-spark="{0}" d="M{2:.1f} 42 L50 3"/>'.format(
            check * reads + slot, ' class="lit"' if check * reads + slot == first else "", width * (slot + 0.5))
                        for slot in range(reads))
        tiles = "".join(
            '<button type="button" class="reuse-folder{0}" data-folder="{1}" aria-label="Change a file in folder {2}" disabled>{2}</button>'.format(
                " changed" if check * reads + slot == first else "", check * reads + slot, check * reads + slot + 1)
            for slot in range(reads))
        units.append(
            '<div class="reuse-unit{0}" data-check="{1}"><div class="reuse-lamp"><span class="reuse-dot"></span>'
            '<b>Check {2}</b><i class="reuse-state">{3}</i></div>'
            '<svg class="reuse-wires" viewBox="0 0 100 44" aria-hidden="true">{4}</svg>'
            '<div class="reuse-folders">{5}</div></div>'.format(
                " ran" if ran else "", check, check + 1, "ran again" if ran else "kept", wires, tiles))
    say = f"Folder {first + 1} changed. Only Check {first // reads + 1} ran again."
    tally = ('<div><dt>Checks run</dt><dd data-tally="runs">1</dd></div>'
             '<div class="saved"><dt>Runs skipped</dt><dd data-tally="saved">{0}</dd></div>'
             '<div class="bad" hidden><dt>Outdated uses</dt><dd data-tally="outdated">0</dd></div>').format(checks - 1)
    return (
        '<div class="reuse-play" data-trace="[{trace}]" data-checks="{checks}" data-reads="{reads}">'
        '<p class="reuse-lede reuse-invite" hidden>Choose a folder to change a file.</p>'
        '<div class="reuse-bench" role="group" aria-label="{bench}">{units}</div>'
        '<p class="reuse-say" role="status" aria-atomic="true">{say}</p>'
        '<dl class="reuse-tally">{tally}</dl>'
        '<p class="reuse-ctl" hidden><button type="button" data-act="replay">Play the recorded {edits} changes</button>'
        '<label class="reuse-switch"><input type="checkbox" data-act="hide"> Leave a folder off each check’s list</label>'
        '<button type="button" class="quiet" data-act="reset">Start over</button></p></div>').format(
            trace=",".join(str(folder) for folder in trace), checks=checks, reads=reads,
            bench=html.escape("{0} checks and the {1} folders they read".format(word(checks).capitalize(), word(folders))),
            units="".join(units), say=html.escape(say), tally=tally, edits=edits)


def recorded_comparison(run, finest, hidden, everything):
    return (f"After six starting runs, {run['edits']} file edits led to {run['relied_on']} requests. "
            f"With both folders listed, {finest['executions']} checks ran again, "
            f"{everything['executions'] - finest['executions']} runs were skipped, and no outdated result was used. "
            f"Leaving a folder off each list cut the reruns to {hidden['executions']} and led to {hidden['wrong']} "
            "outdated uses. Requests for the same outdated result each count.")
