"""Scan a folder and group frame sequences (shot_0001.png ... shot_0120.png) into clips."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

VIDEO_EXT = {"mov", "mp4", "mxf", "avi", "mkv", "m4v", "webm", "braw", "r3d", "mts"}
AUDIO_EXT = {"wav", "mp3", "aac", "m4a", "flac", "aif", "aiff"}
IMAGE_EXT = {"png", "jpg", "jpeg", "tif", "tiff", "exr", "dpx", "tga", "bmp", "webp"}

_NUMBERED = re.compile(r"^(?P<prefix>.*?)(?P<num>\d+)\.(?P<ext>[A-Za-z0-9]+)$")


def natural_key(text: str):
    """'shot_2' sorts before 'shot_10'."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


@dataclass
class Sequence:
    folder: Path
    prefix: str
    padding: int
    ext: str
    start: int
    end: int

    def _num(self, n: int) -> str:
        return str(n).zfill(self.padding)

    @property
    def name(self) -> str:
        return f"{self.prefix}[{self._num(self.start)}-{self._num(self.end)}].{self.ext}"

    @property
    def frame_count(self) -> int:
        return self.end - self.start + 1

    def clip_info(self) -> dict:
        """Dict accepted by MediaPool.ImportMedia([{clipInfo}])."""
        token = f"%0{self.padding}d" if self.padding else "%d"
        pattern = f"{self.prefix}{token}.{self.ext}"
        return {"FilePath": str(self.folder / pattern), "StartIndex": self.start, "EndIndex": self.end}


@dataclass
class ScanResult:
    files: list[Path] = field(default_factory=list)  # video, audio, single images
    sequences: list[Sequence] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)  # unsupported extensions
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.files and not self.sequences


def _kind(ext: str) -> str | None:
    ext = ext.lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in IMAGE_EXT:
        return "image"
    return None


def _padding(digit_strings: list[str]) -> int | None:
    """Common zero-padding of frame numbers; 0 = unpadded; None = mixed widths."""
    lengths = {len(d) for d in digit_strings}
    zero_led = {len(d) for d in digit_strings if len(d) > 1 and d.startswith("0")}
    if not zero_led:
        return lengths.pop() if len(lengths) == 1 else 0
    if len(zero_led) == 1:
        width = zero_led.pop()
        if min(lengths) >= width:  # 0998, 0999, 1000, 10000 -> still %04d
            return width
    return None


def _contiguous_runs(numbers: list[int]) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start = prev = numbers[0]
    for n in numbers[1:]:
        if n != prev + 1:
            runs.append((start, prev))
            start = n
        prev = n
    runs.append((start, prev))
    return runs


def scan_folder(folder: str | os.PathLike, recursive: bool = False) -> ScanResult:
    root = Path(folder)
    if not root.is_dir():
        raise FileNotFoundError(f"Folder not found: {root}")

    paths = sorted(root.rglob("*") if recursive else root.iterdir(), key=lambda p: natural_key(str(p)))
    result = ScanResult()
    # (folder, prefix, ext) -> [(digits, path)]
    numbered: dict[tuple[Path, str, str], list[tuple[str, Path]]] = {}

    for path in paths:
        if not path.is_file() or path.name.startswith("."):
            continue
        kind = _kind(path.suffix.lstrip("."))
        if kind is None:
            result.skipped.append(path)
            continue
        match = _NUMBERED.match(path.name)
        if kind == "image" and match:
            numbered.setdefault((path.parent, match["prefix"], match["ext"]), []).append((match["num"], path))
        else:
            result.files.append(path)

    # (folder, prefix, ext, padding) -> {frame: path}
    groups: dict[tuple[Path, str, str, int], dict[int, Path]] = {}
    for (parent, prefix, ext), items in numbered.items():
        padding = _padding([digits for digits, _ in items])
        for digits, path in items:
            pad = len(digits) if padding is None else padding  # mixed widths: split by width
            groups.setdefault((parent, prefix, ext, pad), {})[int(digits)] = path

    for (parent, prefix, ext, padding), frames in groups.items():
        numbers = sorted(frames)
        if len(numbers) == 1:
            result.files.append(frames[numbers[0]])
            continue
        runs = _contiguous_runs(numbers)
        for start, end in runs:
            if start == end:
                result.files.append(frames[start])
            else:
                result.sequences.append(Sequence(parent, prefix, padding, ext, start, end))
        if len(runs) > 1:
            gaps = [f"{a + 1}-{b - 1}" if b - a > 2 else str(a + 1) for (_, a), (b, _) in zip(runs, runs[1:])]
            result.warnings.append(
                f"{prefix}*.{ext}: missing frames {', '.join(gaps)} - imported as {len(runs)} separate clips"
            )

    result.files.sort(key=lambda p: natural_key(p.name))
    result.sequences.sort(key=lambda s: natural_key(s.name))
    return result
