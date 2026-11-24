import csv
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path
from unittest import mock

from resolve_autotools import cli, ops
from resolve_autotools.connect import ResolveError
from resolve_autotools.markers import Marker

from tests.fake_resolve import FakeProject, FakeResolve, demo_resolve


class ImportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name) / "Day 01"
        self.folder.mkdir()
        for name in ["shot_0001.png", "shot_0002.png", "shot_0003.png", "b_roll10.mov", "b_roll2.mov", "vo.wav"]:
            (self.folder / name).write_bytes(b"")
        self.resolve = FakeResolve(FakeProject())
        self.pool = self.resolve.GetProjectManager().GetCurrentProject().GetMediaPool()

    def tearDown(self):
        self.tmp.cleanup()

    def test_imports_into_bin_and_builds_timeline(self):
        report = ops.import_folder(self.resolve, self.folder, timeline_name="Assembly")
        self.assertEqual(report.bin_name, "Day 01")
        self.assertEqual([f.GetName() for f in self.pool.root.subfolders], ["Day 01"])
        # plain files and sequences are imported in two separate calls
        self.assertEqual(len(self.pool.import_calls), 2)
        self.assertEqual(self.pool.import_calls[1][0]["StartIndex"], 1)
        self.assertEqual(len(report.clips), 4)

        project = self.resolve.GetProjectManager().GetCurrentProject()
        timeline = ops.find_timeline(project, "Assembly")
        names = [i.GetName() for i in timeline.GetItemListInTrack("video", 1)]
        self.assertEqual(names, ["b_roll2.mov", "b_roll10.mov", "shot_[0001-0003].png"])  # audio left out

    def test_reuses_bin_and_makes_timeline_name_unique(self):
        ops.import_folder(self.resolve, self.folder, timeline_name="Assembly")
        report = ops.import_folder(self.resolve, self.folder, timeline_name="Assembly")
        self.assertEqual(report.timeline_name, "Assembly 2")
        self.assertEqual(len(self.pool.root.subfolders), 1)

    def test_empty_folder_and_no_project(self):
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        with self.assertRaises(ResolveError):
            ops.import_folder(self.resolve, empty)
        with self.assertRaises(ResolveError):
            ops.import_folder(FakeResolve(None), self.folder)


class MarkersAndShotListTest(unittest.TestCase):
    def setUp(self):
        self.resolve = demo_resolve()
        self.project = self.resolve.GetProjectManager().GetCurrentProject()
        self.timeline = ops.find_timeline(self.project)  # "Edit v1", 96 frames

    def test_apply_markers(self):
        markers = [Marker("00:00:02:00", "Red", "Cut", line=2),
                   Marker("01:00:02:00", "Blue", "Same frame", line=3),
                   Marker("00:00:10:00", line=4),
                   Marker("bad", line=5)]
        report = ops.apply_markers(self.timeline, markers)
        self.assertEqual([m.line for m in report.added], [2])
        self.assertEqual(self.timeline.GetMarkers()[48]["color"], "Red")
        reasons = {m.line: reason for m, reason in report.failed}
        self.assertIn("rejected", reasons[3])
        self.assertIn("outside the timeline", reasons[4])
        self.assertIn("Bad timecode", reasons[5])

    def test_shot_list(self):
        rows = ops.shot_list(self.timeline)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1], {
            "track": "V1", "index": 2, "name": "interview.mov",
            "record_in": "01:00:02:00", "record_out": "01:00:04:00",
            "duration_frames": 48, "duration": "00:00:02:00", "source_file": r"D:\media\interview.mov",
        })

    def test_write_shot_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shots.csv"
            self.assertEqual(ops.write_shot_list(self.timeline, path), 2)
            with open(path, encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.DictReader(fh))
        self.assertEqual(rows[0]["name"], "intro.mov")
        self.assertEqual(list(rows[0]), ops.SHOT_LIST_FIELDS)

    def test_unknown_timeline(self):
        with self.assertRaisesRegex(ResolveError, "available: Edit v1, Shorts cut"):
            ops.find_timeline(self.project, "Final")


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.resolve = demo_resolve()
        self.project = self.resolve.GetProjectManager().GetCurrentProject()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_render_name(self):
        self.assertEqual(ops.render_name("{project}_{timeline}_{date}", "My: Project", "Edit/v2", date(2026, 11, 24)),
                         "My_Project_Edit_v2_2026-11-24")
        self.assertEqual(ops.render_name("{timeline}", "", "???"), "render")

    def test_queue_all_timelines_and_restore_current(self):
        self.project.current = self.project.timelines[1]
        jobs = ops.queue_renders(self.resolve, "YouTube - 1080p", self.tmp.name, name_template="{timeline}")
        self.assertEqual([(j.timeline, j.file_name) for j in jobs], [("Edit v1", "Edit_v1"), ("Shorts cut", "Shorts_cut")])
        self.assertEqual(self.project.jobs["job-1"]["preset"], "YouTube - 1080p")
        self.assertEqual(self.project.jobs["job-2"]["CustomName"], "Shorts_cut")
        self.assertTrue(self.project.jobs["job-1"]["SelectAllFrames"])
        self.assertEqual(self.project.GetCurrentTimeline().GetName(), "Shorts cut")

    def test_queue_selected_timeline(self):
        jobs = ops.queue_renders(self.resolve, "H.264 Master", self.tmp.name, ["Shorts cut"])
        self.assertEqual([j.timeline for j in jobs], ["Shorts cut"])

    def test_unknown_preset(self):
        with self.assertRaisesRegex(ResolveError, "available: YouTube - 1080p, H.264 Master"):
            ops.queue_renders(self.resolve, "ProRes", self.tmp.name)

    def test_start_and_wait(self):
        jobs = ops.queue_renders(self.resolve, "YouTube - 1080p", self.tmp.name)
        seen = []
        with mock.patch("resolve_autotools.ops.time.sleep"):
            results = ops.start_and_wait(self.resolve, jobs, lambda job, st: seen.append(st["JobStatus"]))
        self.assertIn("Rendering", seen)
        self.assertEqual({st["JobStatus"] for st in results.values()}, {"Complete"})


class CliTest(unittest.TestCase):
    def run_cli(self, *argv, resolve=None):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv), resolve=resolve or demo_resolve())
        return code, out.getvalue(), err.getvalue()

    def test_info(self):
        code, out, _ = self.run_cli("info")
        self.assertEqual(code, 0)
        self.assertIn("Project: Demo Project", out)
        self.assertIn("* Edit v1  (24 fps, 00:00:04:00, start 01:00:00:00)", out)

    def test_markers_exit_code_on_partial_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.csv"
            path.write_text("timecode,color\n00:00:01:00,Red\n00:00:30:00,Red\n", encoding="utf-8")
            code, out, err = self.run_cli("markers", str(path))
        self.assertEqual(code, 2)
        self.assertIn("Added 1 markers", out)
        self.assertIn("outside the timeline", err)

    def test_shotlist_and_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _ = self.run_cli("shotlist", str(Path(tmp) / "s.csv"), "--timeline", "Shorts cut")
            self.assertEqual(code, 0)
            self.assertIn("Wrote 1 shots", out)
            with mock.patch("resolve_autotools.ops.time.sleep"):
                code, out, _ = self.run_cli("render", "--preset", "YouTube - 1080p", "--out", tmp, "--wait")
        self.assertEqual(code, 0)
        self.assertIn("All renders finished.", out)

    def test_errors_are_reported_not_raised(self):
        code, _, err = self.run_cli("info", resolve=FakeResolve(None))
        self.assertEqual(code, 1)
        self.assertIn("No project is open", err)


if __name__ == "__main__":
    unittest.main()
