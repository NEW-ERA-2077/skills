"""Integration tests using a tiny generated video. Run python -m unittest discover -s tests -v."""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "video_map_builder.py"


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg/FFprobe not installed")
class VideoMapCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="videomap_test_")
        cls.root = Path(cls.tmp.name)
        cls.video = cls.root / "sample video.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                        "testsrc2=size=320x180:rate=24", "-t", "6", "-c:v", "mpeg4", "-y", str(cls.video)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def call(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(APP), *map(str, args), "--json"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, ok, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def test_plan_has_no_output_files(self):
        plan = self.call("plan", self.video)
        self.assertEqual(plan["estimated_frames"], 38)  # 2 + 12 + 24
        self.assertFalse((self.root / "sample video_video_map").exists())

    def test_build_locate_extend_cache_fullres_resume(self):
        project = self.root / "main"
        result = self.call(self.video, "--output", project)
        self.assertTrue(result["ok"])
        self.assertEqual(result["frames"], 38)
        first = list((project / "02_main_2fps" / "sheets").glob("*.jpg"))
        self.assertEqual(len(first), 1)
        with (project / "02_main_2fps" / "frames.csv").open(encoding="utf-8-sig") as f:
            records = list(csv.DictReader(f))
        self.assertTrue(records)
        self.assertTrue(all(not x["filename"] and not x["frame_path"] for x in records))
        found = self.call("locate", "--project", project, "--start", "00:02", "--end", "00:03")
        self.assertTrue(found["sheets"])
        self.assertTrue(all(2 <= x["seconds"] < 3 for x in found["matches"]))
        self.assertEqual(self.call(self.video, "--output", project, "--resume")["frames"], 38)
        extra = self.call("extend", "--project", project, "--start", "00:02", "--end", "00:04", "--fps", "5")
        self.assertEqual(extra["frames"], 48)
        again = self.call("extend", "--project", project, "--start", "00:02", "--end", "00:04", "--fps", "5")
        self.assertTrue(again["cached"])
        self.assertEqual(self.call(self.video, "--output", project, "--resume")["frames"], 48)
        from PIL import Image
        image = self.call("frame", "--project", project, "--at", "00:03.20")
        with Image.open(image["frame"]) as frame:
            self.assertEqual(frame.size, (320, 180))
        self.assertTrue(self.call("frame", "--project", project, "--at", "00:03.20")["cached"])
        self.assertEqual(self.call("status", "--project", project)["passes"], 4)
        self.assertFalse(self.call("locate", "--project", project, "--start", "00:04", "--end", "00:03", ok=False)["ok"])

    def test_range_boundary_and_preserved_frames(self):
        project = self.root / "single"
        self.call(self.video, "--output", project, "--fps", "2", "--start", "00:01.3",
                  "--end", "00:03.1", "--keep-frames", "--format", "png")
        folder = project / "map_2fps"
        with (folder / "frames.csv").open(encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        self.assertTrue(all(1.3 <= float(x["seconds"]) < 3.1 for x in rows))
        self.assertTrue(all((folder / x["frame_path"]).is_file() for x in rows))
        self.assertTrue(list((folder / "sheets").glob("*.png")))

    def test_resume_recovers_committed_pass(self):
        project = self.root / "recovered"
        self.call(self.video, "--output", project, "--fps", "1")
        manifest_path = project / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["results"] = []
        manifest["status"] = "incomplete"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        recovered = self.call(self.video, "--output", project, "--fps", "1", "--resume")
        self.assertTrue(recovered["ok"])
        self.assertEqual(recovered["passes"], 1)

    def test_invalid_ranges(self):
        result = self.call("plan", self.video, "--fps", "1", "--start", "00:04", "--end", "00:03", ok=False)
        self.assertFalse(result["ok"])
        self.assertFalse(self.call("frame", "--project", self.root / "main", "--at", "00:07", ok=False)["ok"])


if __name__ == "__main__":
    unittest.main()
