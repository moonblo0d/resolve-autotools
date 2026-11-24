import unittest

from resolve_autotools.timecode import FrameRate, frames_to_tc, tc_to_frames

R24 = FrameRate.parse("24")
R25 = FrameRate.parse("25")
DF2997 = FrameRate.parse("29.97 DF")
DF5994 = FrameRate.parse("59.94DF")


class FrameRateTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(FrameRate.parse("23.976"), FrameRate(23.976, False))
        self.assertEqual(FrameRate.parse("23.976").nominal, 24)
        self.assertEqual(DF2997, FrameRate(29.97, True))
        self.assertEqual(DF2997.dropped_per_minute, 2)
        self.assertEqual(DF5994.dropped_per_minute, 4)
        self.assertEqual(R25.dropped_per_minute, 0)

    def test_parse_errors(self):
        for bad in ("abc", "0", "-24", "25 DF"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                FrameRate.parse(bad)


class NonDropTest(unittest.TestCase):
    def test_known_values(self):
        self.assertEqual(tc_to_frames("01:00:00:00", R24), 86400)
        self.assertEqual(tc_to_frames("00:00:01:12", R25), 37)
        self.assertEqual(frames_to_tc(86400 + 48, R24), "01:00:02:00")

    def test_round_trip(self):
        for rate in (R24, R25, FrameRate.parse("30"), FrameRate.parse("23.976")):
            for frames in (0, 1, 23, 24, 86399, 123456, 2_000_000):
                with self.subTest(rate=rate, frames=frames):
                    self.assertEqual(tc_to_frames(frames_to_tc(frames, rate), rate), frames)

    def test_invalid(self):
        for tc in ("00:00:00:24", "00:60:00:00", "1:2:3", "aa:bb:cc:dd", "00:00:00;10"):
            with self.subTest(tc=tc), self.assertRaises(ValueError):
                tc_to_frames(tc, R24)
        with self.assertRaises(ValueError):
            frames_to_tc(-1, R24)


class DropFrameTest(unittest.TestCase):
    def test_known_values_2997(self):
        self.assertEqual(tc_to_frames("00:00:59;29", DF2997), 1799)
        self.assertEqual(tc_to_frames("00:01:00;02", DF2997), 1800)  # ;00 and ;01 are skipped
        self.assertEqual(tc_to_frames("00:10:00;00", DF2997), 17982)  # every 10th minute keeps them
        self.assertEqual(tc_to_frames("01:00:00;00", DF2997), 107892)
        self.assertEqual(frames_to_tc(1800, DF2997), "00:01:00;02")
        self.assertEqual(frames_to_tc(17982, DF2997), "00:10:00;00")

    def test_known_values_5994(self):
        self.assertEqual(tc_to_frames("00:01:00;04", DF5994), 3600)
        self.assertEqual(frames_to_tc(3600, DF5994), "00:01:00;04")

    def test_round_trip(self):
        for rate in (DF2997, DF5994):
            for frames in list(range(0, 250_000, 997)) + [1799, 1800, 17981, 17982, 107892]:
                with self.subTest(rate=rate, frames=frames):
                    self.assertEqual(tc_to_frames(frames_to_tc(frames, rate), rate), frames)

    def test_skipped_codes_are_rejected(self):
        with self.assertRaises(ValueError):
            tc_to_frames("00:01:00;00", DF2997)
        # ...but minute 10 keeps frame ;00
        self.assertEqual(tc_to_frames("00:10:00;00", DF2997), 17982)


if __name__ == "__main__":
    unittest.main()
