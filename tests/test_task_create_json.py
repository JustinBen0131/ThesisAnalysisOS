"""`taos task create --json` prints the task as JSON, as `show --json` does."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import REPO, cleanup, make_home
from taos_core import use


class CreateJson(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.paths = make_home()
        self.addCleanup(cleanup, self.tmp)
        self.work = Path(tempfile.mkdtemp()).resolve() / "my-analysis"
        self.addCleanup(shutil.rmtree, str(self.work.parent), True)
        shutil.copytree(str(REPO / "examples" / "measurement"), str(self.work), ignore=shutil.ignore_patterns("__pycache__"))

    def test_task_create_json_prints_json(self) -> None:
        use.use(self.paths, self.work, [])
        said = subprocess.run([sys.executable, str(self.paths.home / "taos"), "task", "create", "--agent", "human",
                               "--title", "a second task", "--json"], capture_output=True, text=True, cwd=str(self.work))
        self.assertEqual(said.returncode, 0, said.stderr)
        task = json.loads(said.stdout)
        self.assertEqual(task["title"], "a second task")
        self.assertTrue(task["id"])


if __name__ == "__main__":
    unittest.main()
