import tempfile
import unittest
from pathlib import Path

from resolve_autotools.media import natural_key, scan_folder


def touch(folder: Path, *names: str) -> None:
    for name in names:
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")


class ScanFolderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        touch(self.root,
              *[f"shot_{i:04d}.png" for i in (1, 2, 3, 4, 5, 7, 8)],  # gap at 6
              "frame9.jpg", "frame10.jpg", "frame11.jpg",  # unpadded
              *[f"plate_{i:04d}.exr" for i in (998, 999, 1000, 1001)],  # padding rollover
              "clip10.mp4", "clip2.mp4", "music.wav", "cover.png", "logo_01.png",
              "notes.txt", ".DS_Store",
              "sub/a_001.png", "sub/a_002.png")

    def tearDown(self):
        self.tmp.cleanup()

    def test_groups_sequences(self):
        result = scan_folder(self.root)
        self.assertEqual([s.name for s in result.sequences],
                         ["frame[9-11].jpg", "plate_[0998-1001].exr", "shot_[0001-0005].png", "shot_[0007-0008].png"])
        self.assertEqual([s.frame_count for s in result.sequences], [3, 4, 5, 2])

    def test_files_in_natural_order(self):
        result = scan_folder(self.root)
        self.assertEqual([p.name for p in result.files],
                         ["clip2.mp4", "clip10.mp4", "cover.png", "logo_01.png", "music.wav"])

    def test_skipped_hidden_and_warnings(self):
        result = scan_folder(self.root)
        self.assertEqual([p.name for p in result.skipped], ["notes.txt"])
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("missing frames 6", result.warnings[0])

    def test_clip_info_for_import_media(self):
        result = scan_folder(self.root)
        shot = next(s for s in result.sequences if s.prefix == "shot_" and s.start == 1)
        info = shot.clip_info()
        self.assertTrue(info["FilePath"].endswith("shot_%04d.png"))
        self.assertEqual((info["StartIndex"], info["EndIndex"]), (1, 5))
        unpadded = next(s for s in result.sequences if s.prefix == "frame")
        self.assertTrue(unpadded.clip_info()["FilePath"].endswith("frame%d.jpg"))

    def test_recursive(self):
        self.assertFalse(any(s.prefix == "a_" for s in scan_folder(self.root).sequences))
        self.assertTrue(any(s.name == "a_[001-002].png" for s in scan_folder(self.root, recursive=True).sequences))

    def test_missing_folder(self):
        with self.assertRaises(FileNotFoundError):
            scan_folder(self.root / "nope")

    def test_natural_key(self):
        self.assertEqual(sorted(["shot_10", "shot_2", "Shot_1"], key=natural_key), ["Shot_1", "shot_2", "shot_10"])


if __name__ == "__main__":
    unittest.main()
