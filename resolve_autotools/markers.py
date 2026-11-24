"""Review notes (CSV) -> timeline markers.

CSV columns (header required, ',' or ';' delimiter):
    timecode,color,name,note,duration
Only `timecode` is required. `duration` is in frames (default 1).
"""

from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass, field

from .timecode import FrameRate, tc_to_frames

MARKER_COLORS = (
    "Blue", "Cyan", "Green", "Yellow", "Red", "Pink", "Purple", "Fuchsia",
    "Rose", "Lavender", "Sky", "Mint", "Lemon", "Sand", "Cocoa", "Cream",
)
_COLOR_LOOKUP = {c.lower(): c for c in MARKER_COLORS}
DEFAULT_COLOR = "Blue"


@dataclass
class Marker:
    timecode: str
    color: str = DEFAULT_COLOR
    name: str = ""
    note: str = ""
    duration: int = 1
    line: int = 0  # line in the source CSV, for error messages


@dataclass
class MarkerFile:
    markers: list[Marker] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _normalize_header(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def parse_markers_csv(source: str | os.PathLike | io.TextIOBase) -> MarkerFile:
    """Parse the CSV and collect every bad row instead of stopping at the first one."""
    if isinstance(source, (str, os.PathLike)):
        with open(source, encoding="utf-8-sig", newline="") as fh:
            text = fh.read()
    else:
        text = source.read()

    result = MarkerFile()
    if not text.strip():
        result.errors.append("CSV file is empty")
        return result

    first_line = text.splitlines()[0]
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    reader.fieldnames = [_normalize_header(h) for h in reader.fieldnames or []]
    if "timecode" not in reader.fieldnames:
        result.errors.append(f"Missing 'timecode' column (found: {', '.join(reader.fieldnames)})")
        return result

    for row in reader:
        line = reader.line_num
        values = {k: (v or "").strip() for k, v in row.items() if k}
        if not any(values.values()):
            continue
        tc = values.get("timecode", "")
        if not tc:
            result.errors.append(f"line {line}: empty timecode")
            continue

        color_text = values.get("color", "")
        color = _COLOR_LOOKUP.get(color_text.lower()) if color_text else DEFAULT_COLOR
        if color is None:
            result.errors.append(f"line {line}: unknown color {color_text!r} (allowed: {', '.join(MARKER_COLORS)})")
            continue

        duration_text = values.get("duration", "")
        try:
            duration = int(duration_text) if duration_text else 1
            if duration < 1:
                raise ValueError
        except ValueError:
            result.errors.append(f"line {line}: duration must be a positive whole number of frames")
            continue

        result.markers.append(
            Marker(tc, color, values.get("name", ""), values.get("note", ""), duration, line)
        )
    return result


def marker_frame(marker: Marker, rate: FrameRate, timeline_start_tc: str) -> int:
    """Frame offset from the timeline start, as Timeline.AddMarker expects.

    Absolute timecodes ("01:00:05:00" on a 01:00:00:00 timeline) are used as is.
    Earlier timecodes ("00:00:05:00") are treated as relative to the timeline start,
    which is how most review tools export notes.
    """
    frames = tc_to_frames(marker.timecode, rate)
    start = tc_to_frames(timeline_start_tc, rate)
    return frames - start if frames >= start else frames
