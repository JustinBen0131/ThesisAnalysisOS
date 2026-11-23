"""Exercise evidence maintenance in temporary directories without running a study."""

import contextlib
import copy
import io
import json
import os
import subprocess
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import zlib

from evals import refresh_results as refresh


class RefreshTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.addCleanup(os.chdir, Path.cwd())
        os.chdir(directory.name)
        self.source = Path("source.txt")
        self.source.write_text("original")
        self.result = Path("result.json")
        self.replay = Path("replay.json")
        self.stable = Path("headline.txt")

        def study():
            return json.dumps({"sources": refresh.fingerprint([self.source]), "count": 4})

        def replay():
            return json.dumps({"sources": refresh.fingerprint([self.result])})

        def headline():
            return str(refresh.record(self.result)["count"])

        self.result.write_text(study())
        self.replay.write_text(replay())
        self.stable.write_text(headline())
        self.writes = []

        def write(path, produce):
            def generate(candidate):
                self.writes.append(path)
                candidate.write_text(produce())
            return generate

        self.entries = [
            refresh.Item(self.result, lambda p: refresh.source_reason(p, lambda _: refresh.fingerprint([self.source])),
                         write(self.result, study)),
            refresh.Item(self.replay, lambda p: refresh.source_reason(p, lambda _: refresh.fingerprint([self.result])),
                         write(self.replay, replay), (self.result,)),
            refresh.Item(self.stable, lambda p: refresh.different_text(p, headline, "headline changed"),
                         write(self.stable, headline), (self.result,)),
        ]

    def run_refresh(self, write=False):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            status = refresh.refresh(self.entries, write)
        return status, output.getvalue()

    def test_clean_run_preserves_all_saved_files(self):
        mtimes = {p: p.stat().st_mtime_ns for p in Path.cwd().iterdir()}
        for write in (False, True):
            status, output = self.run_refresh(write)
            self.assertEqual(status, 0)
            self.assertEqual(output.count("CURRENT"), 3)
        self.assertEqual({p: p.stat().st_mtime_ns for p in Path.cwd().iterdir()}, mtimes)
        self.assertEqual(self.writes, [])

    def test_check_reports_prerequisite_and_write_rechecks_each_dependent(self):
        self.source.write_text("changed bytes")
        originals = {item.path: item.path.read_bytes() for item in self.entries}
        status, output = self.run_refresh()
        self.assertEqual(status, 1)
        self.assertIn("source changed: source.txt", output)
        self.assertIn("RECHECK replay.json after result.json", output)
        self.assertEqual({p: p.read_bytes() for p in originals}, originals)
        self.assertEqual(self.writes, [])
        self.assertEqual(self.run_refresh(True)[0], 0)
        self.assertEqual(self.writes, [self.result, self.replay])
        self.assertEqual(refresh.record(self.replay)["sources"]["result.json"], refresh.digest(self.result))
        self.assertEqual(self.run_refresh()[0], 0)

    def test_failed_native_writer_preserves_output_and_stops(self):
        script = Path("stub.py")
        script.write_text("from pathlib import Path\nRECORD = Path('result.json')\n"
                          "def main():\n    RECORD.write_text('partial output')\n    return 7\n")
        self.entries[0].write = refresh.writer("stub.py", "--write", output_attribute="RECORD")
        self.source.write_text("changed")
        originals = {item.path: item.path.read_bytes() for item in self.entries}
        status, output = self.run_refresh(True)
        self.assertEqual(status, 2)
        self.assertIn("generator exited 7", output)
        self.assertNotIn("replay.json", output)
        self.assertEqual({p: p.read_bytes() for p in originals}, originals)
        self.assertEqual(self.writes, [])

    def test_invalid_successful_output_is_never_installed(self):
        self.source.write_text("changed")
        self.entries[0].write = lambda p: p.write_text("{}")
        before = self.result.read_bytes()
        status, output = self.run_refresh(True)
        self.assertEqual(status, 2)
        self.assertIn("missing source fingerprints", output)
        self.assertEqual(self.result.read_bytes(), before)

    def test_an_edit_during_generation_is_preserved(self):
        self.source.write_text("changed")
        original_write = self.entries[0].write

        def simultaneous_edit(candidate):
            original_write(candidate)
            self.result.write_text("a contributor saved this")

        self.entries[0].write = simultaneous_edit
        status, output = self.run_refresh(True)
        self.assertEqual(status, 2)
        self.assertIn("saved file changed during refresh", output)
        self.assertEqual(self.result.read_text(), "a contributor saved this")
        self.assertEqual(self.writes, [self.result])

    def test_measured_declarations_detect_new_files_and_removed_patterns(self):
        sys.path.insert(0, str(refresh.ROOT / "evals"))
        self.addCleanup(sys.path.pop, 0)
        import measured
        rules = ["inputs/*.py"]
        study = mock.Mock(STANDS_ON=rules)
        Path("inputs").mkdir()
        Path("inputs/a.py").write_text("a")
        with mock.patch.object(measured, "REPO", Path.cwd()):
            self.result.write_text(json.dumps({"measured_on": measured.stamp(rules)}))
            verify = mock.Mock()
            self.assertIsNone(refresh.measured_reason(self.result, study, verify))
            verify.assert_called_once_with(refresh.record(self.result))
            verify.side_effect = ValueError("timing summary mismatch")
            with self.assertRaisesRegex(ValueError, "timing summary mismatch"):
                refresh.measured_reason(self.result, study, verify)
            Path("inputs/b.py").write_text("b")
            self.assertIn("inputs/b.py", refresh.measured_reason(self.result, study, verify))
            self.assertEqual(verify.call_count, 2)
            study.STANDS_ON = []
            self.assertIn("declaration differs", refresh.measured_reason(self.result, study))

    def test_session_record_recalculates_text_and_rejects_a_changed_manifest_or_quote(self):
        from evals import claims
        study = claims.session_footprint
        # A one-file dependency and three UTF-8 samples exercise the claim and refresh readers together.
        with mock.patch.object(study, "STANDS_ON", ["source.txt"]), mock.patch.object(study.measured, "REPO", Path.cwd()):
            valid = {"schema": study.SCHEMA, "measured_on": study.measured.stamp(study.STANDS_ON),
                     "surfaces": {key: study.surface("μ\nsecond line\n", delivery) for key, delivery in study.DELIVERY.items()}}
            phrase = study.quote(valid)
            self.assertIn("15 bytes / 2 lines", phrase)
            claim_path = Path("CLAIMS.md")
            row = "| Reading one demo session | {} | `python3 evals/session_footprint.py` | measured |\n"
            claim_path.write_text(row.format(phrase))
            item = next(entry for entry in refresh.items() if entry.path == refresh.SESSION)
            read_path = Path("session_footprint.json")
            def read(data):
                read_path.write_text(json.dumps(data))
                with mock.patch.object(claims, "RESULTS", Path.cwd()), mock.patch.object(claims, "CLAIMS", claim_path), \
                        mock.patch.object(claims, "README", Path("absent.md")):
                    return claims.check()[0]["state"]
            self.assertEqual(read(valid), "holds")
            self.assertIsNone(refresh.reason(item, read_path))
            for field in ("lines", "bytes", "sha256", "text", "delivery", "patterns", "manifest", "count", "surface"):
                with self.subTest(field=field):
                    bad = copy.deepcopy(valid)
                    if field == "patterns":
                        bad["measured_on"]["patterns"] = []
                    elif field == "manifest":
                        bad["measured_on"]["files"]["files"]["source.txt"] = "0" * 64
                    elif field == "count":
                        bad["measured_on"]["files"]["count"] += 1
                    elif field == "surface":
                        del bad["surfaces"]["agents_md"]
                    else:
                        bad["surfaces"]["compact_status"][field] = 0
                    self.assertEqual(read(bad), "fails")
                    self.assertIsNotNone(refresh.reason(item, read_path))
            claim_path.write_text(row.format("unrecorded quantity"))
            self.assertEqual(read(valid), "fails")
            claim_path.write_text(row.format(phrase))
            self.source.write_text("source edited")
            self.assertEqual(read(valid), "stale")
            self.assertIn("source.txt", refresh.reason(item, read_path))
            read_path.unlink()
            with mock.patch.object(claims, "RESULTS", Path.cwd()), mock.patch.object(claims, "CLAIMS", claim_path), \
                    mock.patch.object(claims, "README", Path("absent.md")):
                self.assertEqual(claims.check()[0]["state"], "unknown")

    def test_session_text_reproduces_across_temp_paths_and_renders_one_named_claim(self):
        from evals import claims
        study = claims.session_footprint
        outputs = []
        for name in ("a", "a longer's fixture path"):
            fixture = Path.cwd() / name
            fixture.mkdir()
            outputs.append(study.observe(fixture))
        self.assertEqual(outputs[0], outputs[1])
        self.assertIn("<PYTHON>", outputs[0]["agents_md"]["text"])
        self.assertIn("<DEMO>", outputs[0]["agents_md"]["text"])
        self.assertIn("YYYY-MM-DD", outputs[0]["compact_status"]["text"])
        self.assertEqual(set(outputs[0]), {"agents_md", "compact_status", "task_capsule"})
        dependency = next(entry for entry in refresh.items() if entry.path == refresh.CLAIMS)
        self.assertIn(refresh.SESSION, dependency.needs)
        original = "before\n| Reading one demo session | previous | cmd | measured |\nafter\n"
        self.assertEqual(refresh.replace_rows(original, {study.LABEL: "new counts"}, {}),
                         original.replace("previous", "new counts"))

    def test_timing_refresh_only_edits_named_cells(self):
        import types
        rows = {"Cost of a consultation": "8 ms", "Cost per file": "12 us per file"}
        fake = types.SimpleNamespace(timing_claims=lambda _: rows, UPKEEP_LABEL="other", ISOLATION_LABEL="isolate")
        claims = Path("claims.md")
        original = ("before\n| Cost of a consultation | old | same | measured timing |\n"
                    "| Cost per file | old | same | measured timing |\n"
                    "| Another row | keep | same | measured timing |\nafter\n")
        claims.write_text(original)
        with mock.patch.dict(sys.modules, claims=fake), mock.patch.object(refresh, "REUSE", self.result), \
                mock.patch.object(refresh, "CLAIMS", claims):
            updated = refresh.timing_text()
            self.assertEqual(updated, original.replace("| old |", "| 8 ms |", 1).replace("| old |", "| 12 us per file |", 1))
            claims.write_text(original + "| Cost per file | old | same | measured timing |\n")
            with self.assertRaisesRegex(ValueError, "expected one timing row"):
                refresh.timing_text()

    def test_timing_refresh_migrates_legacy_label_without_adding_a_row(self):
        import types
        label = "Cost of consulting six unchanged checks at three tree sizes"
        fake = types.SimpleNamespace(timing_claims=lambda _: {label: "new measurement"}, UPKEEP_LABEL=label, ISOLATION_LABEL="isolate")
        claims = Path("claims.md")
        old = "| Asking costs time that grows with the tree | previous | same | measured, one laptop |\n"
        claims.write_text(old)
        with mock.patch.dict(sys.modules, claims=fake), mock.patch.object(refresh, "REUSE", self.result), \
                mock.patch.object(refresh, "CLAIMS", claims):
            expected = "| " + label + " | new measurement | same | measured, one laptop |\n"
            self.assertEqual(refresh.timing_text(), expected)
            claims.write_text(old + expected)
            with self.assertRaisesRegex(ValueError, "expected one timing row"):
                refresh.timing_text()

    def test_figure_tracks_data_renderer_and_png_integrity(self):
        from plot_pendulum import figure_inputs

        def chunk(kind, body):
            return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

        renderer = Path("site/plot_pendulum.py")
        renderer.parent.mkdir()
        renderer.write_text("# figure version 1")
        refresh.MEASUREMENT.parent.mkdir(parents=True)
        refresh.MEASUREMENT.write_text("{}")
        fields = figure_inputs(refresh.MEASUREMENT.read_bytes(), renderer)
        png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
               + b"".join(chunk(b"tEXt", f"{k}\0{v}".encode()) for k, v in fields.items())
               + chunk(b"IDAT", zlib.compress(b"\0\0\0\0")) + chunk(b"IEND", b""))
        figure = Path("figure.png")
        figure.write_bytes(png)
        self.assertIsNone(refresh.figure_reason(figure))
        renderer.write_text("# figure version 2")
        self.assertIn("RendererSHA256", refresh.figure_reason(figure))
        renderer.write_text("# figure version 1")
        refresh.MEASUREMENT.write_text('{"new": true}')
        self.assertIn("SourceSHA256", refresh.figure_reason(figure))
        figure.write_bytes(png[:-1] + bytes([png[-1] ^ 1]))
        self.assertIn("damaged", refresh.figure_reason(figure))

    def test_historical_comparison_checks_inputs_without_exporting_old_commits(self):
        sys.path.insert(0, str(refresh.ROOT / "evals"))
        self.addCleanup(sys.path.pop, 0)
        import at_revision
        import measured
        item = next(entry for entry in refresh.items() if entry.path.name == "at_revision.json")
        with mock.patch.object(measured, "REPO", Path.cwd()), mock.patch.object(at_revision, "STANDS_ON", ["source.txt"]):
            self.result.write_text(json.dumps({"measured_on": measured.stamp(at_revision.STANDS_ON)}))
            self.assertIsNone(item.check(self.result))
            self.source.write_text("revised counterexample")
            self.assertIn("source.txt", item.check(self.result))

    def test_review_transfer_and_instrument_paths_join_the_routine_check(self):
        sys.path.insert(0, str(refresh.ROOT / "evals"))
        self.addCleanup(sys.path.pop, 0)
        from model_evaluation import EXAMPLE
        from replay_instrument_paths import FILES
        named = {entry.path.as_posix() for entry in refresh.items()}
        self.assertIn("evals/results/followups/review-transfer.json", named)
        self.assertIn("evals/results/followups/instrument-paths.json", named)
        saved = {name: refresh.digest(EXAMPLE / name) for name in FILES}
        self.result.write_text(json.dumps({"source_sha256": saved}))
        self.assertIsNone(refresh.instrument_paths_reason(self.result))
        self.result.write_text(json.dumps({"source_sha256": dict(saved, **{"a.csv": "0" * 64})}))
        self.assertIn("source changed: model_evaluation/a.csv", refresh.instrument_paths_reason(self.result))
        self.result.write_text(json.dumps({"source_sha256": {"a.csv": saved["a.csv"]}}))
        self.assertIn("fixture declaration differs", refresh.instrument_paths_reason(self.result))
        self.source.write_text("sealed")
        self.result.write_text(json.dumps({"sources": refresh.fingerprint([self.source])}))
        item = next(entry for entry in refresh.items() if entry.path.name == "review-transfer.json")
        self.assertIsNone(item.check(self.result))
        self.source.write_text("changed")
        self.assertEqual(item.check(self.result), "source changed: source.txt")

    def test_cli_requires_one_explicit_mode(self):
        for args in ([], ["--check", "--write"], ["--w"]):
            run = subprocess.run([sys.executable, "-B", str(refresh.ROOT / "evals/refresh_results.py"), *args],
                                 capture_output=True)
            self.assertEqual(run.returncode, 2)


if __name__ == "__main__":
    unittest.main()
