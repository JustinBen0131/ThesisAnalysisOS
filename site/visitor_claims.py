"""Short statements for claim selection. The graph retains the full source wording."""
import re


_TITLES = (
    ("A recorded result is answered", "Each result has a verdict and a reason"),
    ("A passed check", "Changing a recorded input invalidates the old pass"),
    ("The answer names", "TAOS names the file that changed"),
    ("No route moves a task", "Closing a task requires passing checks or a documented waiver"),
    ("A result is shared", "Two tasks can share a passing check on identical inputs"),
    ("A change to a file no domain", "An unassigned input leaves the check’s status unknown"),
    ("A declared domain holds", "A listed input counts even when Git ignores it"),
    ("A check marked isolated", "An isolated check runs on a copy of its listed files"),
    ("An acceptance records", "A recorded approval belongs to one version"),
    ("A work product is current", "An output stays current while its listed inputs match"),
    ("A new or lapsed instruction", "Changed instructions can make a task’s earlier closure outdated"),
    ("The instruction that governed", "Earlier instructions remain available by date"),
    ("A replacement governs", "A replacement instruction applies only to its tasks and dates"),
    ("What governs a task", "A new agent gets the original instructions and lessons"),
    ("A reminder shown", "A repeat counts only after someone confirms the mistake"),
    ("A setup is credited", "A setup gets credit only when someone observes it running"),
    ("A lapsed lease", "An expired assignment frees the task"),
    ("A refused start", "A refused start gives the agent no claim on the task"),
    ("A label is read", "Outcomes with missing labels get their own count"),
    ("A decision-bank run", "Saved answers let a reviewer recalculate the score"),
    ("A change is not confirmed", "Predictions stay fixed and scores need a source"),
    ("A number quoted here", "Changing the measured code puts its reported number in doubt"),
    ("An isolated check sees", "An isolated check starts with fixed environment settings"),
    ("Each isolated result records", "Each isolated run records which access it actually blocked"),
    ("The setup answers", "Setup records which files each check should read"),
    ("No row of this file", "The listed code, tests and quoted figures match their sources"),
    ("The first-minute reads run locally", "A new agent can read the task and its rules offline"),
    ("Reading one demo session", "How much text does a new session receive?"),
    ("The demo runs", "The demo runs its commands on a clean copy of the example"),
    ("Earlier releases had", "Fewer of the same tests failed on the next release"),
    ("The tests notice", "Removing safeguards exposed a missing test"),
    ("Reuse by basis relied", "Checking the inputs avoided outdated reuse in this experiment"),
    ("Age limits trade", "Longer intervals saved reruns and missed more changes"),
    ("In the open", "An unlisted input allowed an outdated result to be reused"),
    ("Isolated, a check", "Checks missing a required input failed in isolation"),
    ("Asking costs time", "Comparing more files took longer on the test laptop"),
    ("Isolating a check costs", "Checks took longer in isolation in the paired trial"),
    ("Cost of consulting", "How long did it take to check which results still applied?"),
    ("Added cost of isolating", "How did isolation affect the time to run a check?"),
    ("The suite passes", "Which environments does the test suite cover?"),
    ("Cases collected by the self-test suite", "Which cases does the self-test suite include?"),
)

# These six claims quote the project overview. Take the numbers from the current
# quote so the heading cannot silently retain a value from a previous release.
_OVERVIEW = (
    (r"(\d+) tests", "The test suite contains {0} tests"),
    (r"(\d+) of (\d+) fail at [0-9a-f]+, (\d+) of (\d+) fail at [0-9a-f]+, (\d+) of (\d+) pass here",
     "Earlier releases failed {0}/{1} and {2}/{3} checks. This release passed {4}/{5}"),
    (r"(\d+) of (\d+) removals are caught", "Tests caught {0} of {1} deliberately removed safeguards"),
    (r"(\d+) executions and (\d+) wrong reuses",
     "Checks with both folders listed ran {0} times and reused {1} outdated results"),
    (r"(\d+) wrong reuses in (\d+)",
     "Omitting one folder led to {0} outdated results in {1} uses"),
    (r"(\d+) of (\d+) runs passed",
     "With a required folder missing, {0} of {1} isolated checks passed"),
)


def visitor_claim_title(text):
    """Return the exact source claim for any new wording that needs editorial review."""
    for beginning, title in _TITLES:
        if text.startswith(beginning):
            return title
    prefix = "README.md repeats: "
    if text.startswith(prefix):
        for pattern, title in _OVERVIEW:
            match = re.fullmatch(pattern, text[len(prefix):])
            if match:
                return title.format(*match.groups())
    return text
