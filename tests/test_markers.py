import io
import tempfile
import unittest
from pathlib import Path

from resolve_autotools.markers import Marker, marker_frame, parse_markers_csv
from resolve_autotools.timecode import FrameRate

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "review_notes.csv"


class ParseTest(unittest.TestCase):
    def test_example_file(self):
        result = parse_markers_csv(EXAMPLE)
        self.assertEqual(result.errors, [])
        self.assertEqual([m.color for m in result.markers], ["Red", "Yellow", "Green", "Blue"])
        self.assertEqual([m.duration for m in result.markers], [12, 1, 1, 24])
        self.assertEqual(result.markers[0].name, "Jump cut")

    def test_semicolon_and_header_case(self):
        text = "Timecode;COLOR;Note\n00:00:01:00;red;Fix colour\n"
        result = parse_markers_csv(io.StringIO(text))
        self.assertEqual(result.errors, [])
        self.assertEqual(result.markers[0].color, "Red")
        self.assertEqual(result.markers[0].note, "Fix colour")

    def test_collects_all_errors_with_line_numbers(self):
        text = ("timecode,color,duration\n"
                "00:00:01:00,Orange,1\n"
                ",Red,1\n"
                "00:00:02:00,Red,abc\n"
                "00:00:03:00,Red,0\n"
                "00:00:04:00,,\n")
        result = parse_markers_csv(io.StringIO(text))
        self.assertEqual(len(result.markers), 1)
        self.assertEqual(result.markers[0].color, "Blue")  # empty color -> default
        self.assertEqual(len(result.errors), 4)
        self.assertTrue(result.errors[0].startswith("line 2: unknown color 'Orange'"))
        self.assertTrue(result.errors[1].startswith("line 3: empty timecode"))

    def test_missing_timecode_column(self):
        result = parse_markers_csv(io.StringIO("time,color\n00:00:01:00,Red\n"))
        self.assertEqual(result.markers, [])
        self.assertIn("Missing 'timecode' column", result.errors[0])

    def test_utf8_bom_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.csv"
            path.write_text("timecode,note\n00:00:01:00,Прибрати шум\n", encoding="utf-8-sig")
            result = parse_markers_csv(path)
        self.assertEqual(result.markers[0].note, "Прибрати шум")


class MarkerFrameTest(unittest.TestCase):
    def test_relative_and_absolute(self):
        rate = FrameRate.parse("24")
        self.assertEqual(marker_frame(Marker("00:00:02:00"), rate, "01:00:00:00"), 48)
        self.assertEqual(marker_frame(Marker("01:00:12:00"), rate, "01:00:00:00"), 288)
        self.assertEqual(marker_frame(Marker("00:00:02:00"), rate, "00:00:00:00"), 48)


if __name__ == "__main__":
    unittest.main()
