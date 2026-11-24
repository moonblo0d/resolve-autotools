"""SMPTE timecode <-> frame conversion, including 29.97 / 59.94 drop-frame."""

from __future__ import annotations

import re
from dataclasses import dataclass

_TC_RE = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2})([:;.])(\d{2,3})$")


@dataclass(frozen=True)
class FrameRate:
    """Timeline frame rate as Resolve reports it ("24", "23.976", "29.97 DF")."""

    fps: float
    drop_frame: bool = False

    @property
    def nominal(self) -> int:
        """Integer frame count per timecode second (23.976 -> 24, 29.97 -> 30)."""
        return int(round(self.fps))

    @property
    def dropped_per_minute(self) -> int:
        # 2 frames for 29.97 DF, 4 frames for 59.94 DF
        return self.nominal // 15 if self.drop_frame else 0

    @classmethod
    def parse(cls, value: str | float | int) -> "FrameRate":
        text = str(value).strip().upper()
        drop = text.endswith("DF")
        if drop:
            text = text[:-2].strip()
        try:
            fps = float(text)
        except ValueError:
            raise ValueError(f"Unknown frame rate: {value!r}") from None
        if fps <= 0:
            raise ValueError(f"Frame rate must be positive: {value!r}")
        if drop and int(round(fps)) not in (30, 60):
            raise ValueError(f"Drop-frame is only defined for 29.97 / 59.94: {value!r}")
        return cls(fps, drop)


def tc_to_frames(tc: str, rate: FrameRate) -> int:
    """'01:00:10:12' -> absolute frame number. ';' separator also means drop-frame."""
    match = _TC_RE.match(tc.strip())
    if not match:
        raise ValueError(f"Bad timecode {tc!r}, expected HH:MM:SS:FF")
    hours, minutes, seconds, sep, frames = match.groups()
    h, m, s, f = int(hours), int(minutes), int(seconds), int(frames)
    nominal = rate.nominal
    if m > 59 or s > 59:
        raise ValueError(f"Bad timecode {tc!r}: minutes/seconds must be < 60")
    if f >= nominal:
        raise ValueError(f"Bad timecode {tc!r}: frame {f} does not exist at {nominal} fps")

    drop = rate.dropped_per_minute
    if sep == ";" and not drop:
        raise ValueError(f"Timecode {tc!r} is drop-frame but the rate {rate.fps} is not")
    total = (h * 3600 + m * 60 + s) * nominal + f
    if drop:
        if s == 0 and f < drop and m % 10 != 0:
            raise ValueError(f"Timecode {tc!r} does not exist in drop-frame")
        total_minutes = h * 60 + m
        total -= drop * (total_minutes - total_minutes // 10)
    return total


def frames_to_tc(frames: int, rate: FrameRate) -> str:
    """Absolute frame number -> 'HH:MM:SS:FF' (or 'HH:MM:SS;FF' for drop-frame)."""
    if frames < 0:
        raise ValueError("Frame number cannot be negative")
    nominal = rate.nominal
    drop = rate.dropped_per_minute
    if drop:
        frames_per_10min = nominal * 600 - drop * 9
        frames_per_min = nominal * 60 - drop
        tens, rest = divmod(frames, frames_per_10min)
        frames += drop * 9 * tens
        if rest > drop:
            frames += drop * ((rest - drop) // frames_per_min)
    seconds, f = divmod(frames, nominal)
    minutes, s = divmod(seconds, 60)
    h, m = divmod(minutes, 60)
    sep = ";" if drop else ":"
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{f:02d}"
