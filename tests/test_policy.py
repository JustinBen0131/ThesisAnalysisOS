"""The routing map must resolve, and routing must be predictable."""

from __future__ import annotations

import unittest

from helpers import cleanup, construct_example, make_home

from taos_core import policy as policy_mod
from taos_core.cli import main as cli


class TestPolicy(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.paths = make_home()
        construct_example(self.tmp, self.paths)

    def tearDown(self) -> None:
        cleanup(self.tmp)

    def test_yaml_subset_parses_routing(self) -> None:
        data = policy_mod.load_routing(self.paths)
        self.assertEqual(data["version"], 1)
        self.assertIn("AGENTS.md", data["always"])
        self.assertIn("starting_work", data["routes"])
        route = data["routes"]["starting_work"]
        self.assertIn("work on", route["triggers"])
        self.assertIn("policies/CLAIMS.md", route["load"])
        self.assertTrue(len(route["first_actions"]) >= 3)
        # every route keeps its own block list; a by-name lookup once collapsed them
        git = data["routes"]["git_and_branches"]["first_actions"]
        self.assertNotEqual(git, route["first_actions"])
        self.assertTrue(any("protected" in a or "branch" in a for a in git))
        self.assertEqual(len({tuple(r["first_actions"]) for r in data["routes"].values()}), len(data["routes"]))

    def test_yaml_subset_edge_cases(self) -> None:
        parsed = policy_mod.parse_yaml(
            "a: 1\nb: \"x: y\"  # comment\nc:\n  - one\n  - two\nd:\n  e: [p, q]\n  f:\n    - deep\ng: true\n"
        )
        self.assertEqual(parsed, {"a": 1, "b": "x: y", "c": ["one", "two"], "d": {"e": ["p", "q"], "f": ["deep"]}, "g": True})

    def test_routes_resolve_and_nothing_is_orphaned(self) -> None:
        self.assertEqual(policy_mod.check(self.paths), [])

    def test_route_picks_the_right_policies(self) -> None:
        result = policy_mod.route(self.paths, "can you work on CMP-2 and push a branch")
        names = [r["name"] for r in result["routes"]]
        self.assertIn("starting_work", names)
        self.assertIn("git_and_branches", names)
        self.assertEqual(result["load"][:5], ["AGENTS.md", "policies/OBJECTIVE.md", "policies/CONTROL.md", "policies/OPERATING_LOOP.md", "policies/HARD_STOPS.md"])
        self.assertIn("policies/GIT.md", result["load"])
        self.assertEqual(result["missing"], [])

        result = policy_mod.route(self.paths, "rerun the benchmark again")
        self.assertEqual(result["routes"][0]["name"], "repeating_work")
        self.assertIn("policies/DUPLICATE_WORK.md", result["load"])

        result = policy_mod.route(self.paths, "hello")
        self.assertEqual(result["routes"], [])
        self.assertEqual(len(result["load"]), 5)

    def test_secret_words_route_to_hard_stops_first(self) -> None:
        result = policy_mod.route(self.paths, "read the deploy key and sign the release")
        self.assertEqual(result["routes"][0]["name"], "secrets_and_danger")

    def test_orphan_policy_is_caught(self) -> None:
        (self.paths.policies_dir / "ORPHAN.md").write_text("# nobody routes here\n", encoding="utf-8")
        problems = policy_mod.check(self.paths)
        self.assertTrue(any("ORPHAN.md" in p for p in problems))

    def test_cli(self) -> None:
        self.assertEqual(cli(["--home", str(self.paths.home), "policy", "check"]), 0)
        self.assertEqual(cli(["--home", str(self.paths.home), "policy", "route", "finish this up"]), 0)
        self.assertEqual(cli(["--home", str(self.paths.home), "policy", "show", "gates"]), 0)
        self.assertEqual(cli(["--home", str(self.paths.home), "policy", "show", "nope"]), 1)


if __name__ == "__main__":
    unittest.main()
