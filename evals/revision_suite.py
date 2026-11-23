"""Execute a historical counterexample inventory and return one verifiable JSON row."""
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest


def cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield item


def main(tree):
    sys.path[:0] = [str(tree / "tests"), str(tree)]
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("test_counterexamples")
    inventory = sorted(test.id() for test in cases(suite))
    if loader.errors or not inventory or len(set(inventory)) != len(inventory):
        raise SystemExit("The named suite could not be collected as distinct test cases.")
    result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
    failed = sorted(test.id() for test, _ in result.failures + result.errors)
    if (result.testsRun != len(inventory) or set(failed) - set(inventory)
            or result.skipped or result.expectedFailures or result.unexpectedSuccesses):
        raise SystemExit("Each named case must execute and return an ordinary pass or failure.")
    fingerprint = hashlib.sha256("\n".join(inventory).encode()).hexdigest()
    print(json.dumps({"ran": result.testsRun, "did_not_pass": len(failed),
                      "names": [name.rsplit(".", 1)[-1] for name in failed], "case_roster_sha256": fingerprint}))


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
