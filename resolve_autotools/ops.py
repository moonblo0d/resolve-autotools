"""Operations on the Resolve scripting API (works the same inside and outside Resolve)."""

from __future__ import annotations

import csv
import re
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .connect import ResolveError
from .markers import Marker, marker_frame
from .media import ScanResult, natural_key, scan_folder
from .timecode import FrameRate, frames_to_tc


# ---------------------------------------------------------------- project helpers

def current_project(resolve):
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        raise ResolveError("No project is open in DaVinci Resolve")
    return project


def timelines(project) -> list:
    return [project.GetTimelineByIndex(i) for i in range(1, int(project.GetTimelineCount()) + 1)]


def find_timeline(project, name: str | None = None):
    """Timeline by name, or the current one when name is None."""
    if name is None:
        timeline = project.GetCurrentTimeline()
        if not timeline:
            raise ResolveError("No timeline is open - pass a timeline name")
        return timeline
    for timeline in timelines(project):
        if timeline.GetName() == name:
            return timeline
    names = ", ".join(t.GetName() for t in timelines(project)) or "none"
    raise ResolveError(f"Timeline {name!r} not found (available: {names})")


def timeline_rate(timeline) -> FrameRate:
    fps = timeline.GetSetting("timelineFrameRate")
    drop = str(timeline.GetSetting("timelineDropFrameTimecode")) in ("1", "True", "true")
    rate = FrameRate.parse(fps)
    return FrameRate(rate.fps, rate.drop_frame or (drop and rate.nominal in (30, 60)))


def unique_timeline_name(project, wanted: str) -> str:
    existing = {t.GetName() for t in timelines(project)}
    if wanted not in existing:
        return wanted
    n = 2
    while f"{wanted} {n}" in existing:
        n += 1
    return f"{wanted} {n}"


# ---------------------------------------------------------------- import

@dataclass
class ImportReport:
    scan: ScanResult
    clips: list = field(default_factory=list)
    bin_name: str = ""
    timeline_name: str | None = None


def _get_or_create_bin(media_pool, name: str):
    root = media_pool.GetRootFolder()
    for folder in root.GetSubFolderList() or []:
        if folder.GetName() == name:
            return folder
    folder = media_pool.AddSubFolder(root, name)
    if not folder:
        raise ResolveError(f"Could not create bin {name!r}")
    return folder


def import_folder(resolve, folder, bin_name: str | None = None, timeline_name: str | None = None,
                  recursive: bool = False) -> ImportReport:
    """Import media into its own bin; frame sequences become single clips.

    With `timeline_name` the imported video/image clips are laid out on a new
    timeline in natural order (shot_2 before shot_10).
    """
    scan = scan_folder(folder, recursive=recursive)
    if scan.is_empty:
        raise ResolveError(f"No supported media found in {folder}")

    project = current_project(resolve)
    media_pool = project.GetMediaPool()
    report = ImportReport(scan=scan, bin_name=bin_name or Path(folder).name)
    media_pool.SetCurrentFolder(_get_or_create_bin(media_pool, report.bin_name))

    # Plain paths and clipInfo dicts go in separate calls - the API takes one form per call.
    if scan.files:
        report.clips += media_pool.ImportMedia([str(p) for p in scan.files]) or []
    if scan.sequences:
        report.clips += media_pool.ImportMedia([s.clip_info() for s in scan.sequences]) or []
    if not report.clips:
        raise ResolveError("Resolve did not import any clips (check the file formats)")

    if timeline_name:
        visual = [c for c in report.clips if (c.GetClipProperty("Type") or "").lower() != "audio"]
        visual.sort(key=lambda c: natural_key(c.GetName()))
        name = unique_timeline_name(project, timeline_name)
        if not media_pool.CreateTimelineFromClips(name, visual):
            raise ResolveError(f"Could not create timeline {name!r}")
        report.timeline_name = name
    return report


# ---------------------------------------------------------------- markers

@dataclass
class MarkerReport:
    added: list[Marker] = field(default_factory=list)
    failed: list[tuple[Marker, str]] = field(default_factory=list)


def apply_markers(timeline, markers: list[Marker]) -> MarkerReport:
    rate = timeline_rate(timeline)
    start_tc = timeline.GetStartTimecode()
    length = int(timeline.GetEndFrame()) - int(timeline.GetStartFrame())
    report = MarkerReport()
    for marker in markers:
        try:
            frame = marker_frame(marker, rate, start_tc)
        except ValueError as exc:
            report.failed.append((marker, str(exc)))
            continue
        if not 0 <= frame < length:
            report.failed.append((marker, f"outside the timeline ({frames_to_tc(length, rate)} long)"))
            continue
        if timeline.AddMarker(frame, marker.color, marker.name, marker.note, marker.duration):
            report.added.append(marker)
        else:
            report.failed.append((marker, "Resolve rejected it (a marker already exists on that frame?)"))
    return report


# ---------------------------------------------------------------- shot list

SHOT_LIST_FIELDS = ["track", "index", "name", "record_in", "record_out", "duration_frames", "duration", "source_file"]


def shot_list(timeline) -> list[dict]:
    """One row per clip on every video track, in record order."""
    rate = timeline_rate(timeline)
    rows = []
    for track in range(1, int(timeline.GetTrackCount("video")) + 1):
        items = sorted(timeline.GetItemListInTrack("video", track) or [], key=lambda i: i.GetStart())
        for index, item in enumerate(items, start=1):
            pool_item = item.GetMediaPoolItem()
            source = pool_item.GetClipProperty("File Path") if pool_item else ""
            duration = int(item.GetDuration())
            rows.append({
                "track": f"V{track}",
                "index": index,
                "name": item.GetName(),
                "record_in": frames_to_tc(int(item.GetStart()), rate),
                "record_out": frames_to_tc(int(item.GetEnd()), rate),
                "duration_frames": duration,
                "duration": frames_to_tc(duration, rate),
                "source_file": source or "",
            })
    return rows


def write_shot_list(timeline, path) -> int:
    rows = shot_list(timeline)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SHOT_LIST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


# ---------------------------------------------------------------- render

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def render_name(template: str, project_name: str, timeline_name: str, today: date | None = None) -> str:
    """'{project}_{timeline}_{date}' -> 'My_Project_Edit_v2_2026-11-24' (safe on every OS)."""
    name = template.format(project=project_name, timeline=timeline_name,
                           date=(today or date.today()).isoformat())
    name = _UNSAFE.sub("_", name)
    name = re.sub(r"[\s_]+", "_", name.strip())
    return name.strip("._") or "render"


@dataclass
class RenderJob:
    timeline: str
    job_id: str
    file_name: str


def queue_renders(resolve, preset: str, target_dir, timeline_names: list[str] | None = None,
                  name_template: str = "{project}_{timeline}_{date}") -> list[RenderJob]:
    """Add one render job per timeline with the same preset; the current timeline is restored."""
    project = current_project(resolve)
    presets = project.GetRenderPresetList() or []
    if preset not in presets:
        raise ResolveError(f"Render preset {preset!r} not found (available: {', '.join(presets) or 'none'})")

    targets = [find_timeline(project, n) for n in timeline_names] if timeline_names else timelines(project)
    if not targets:
        raise ResolveError("The project has no timelines")
    Path(target_dir).mkdir(parents=True, exist_ok=True)

    original = project.GetCurrentTimeline()
    jobs: list[RenderJob] = []
    try:
        for timeline in targets:
            if not project.SetCurrentTimeline(timeline):
                raise ResolveError(f"Could not open timeline {timeline.GetName()!r}")
            if not project.LoadRenderPreset(preset):
                raise ResolveError(f"Could not load render preset {preset!r}")
            file_name = render_name(name_template, project.GetName(), timeline.GetName())
            if not project.SetRenderSettings({"SelectAllFrames": True, "TargetDir": str(target_dir),
                                              "CustomName": file_name}):
                raise ResolveError(f"Could not apply render settings for {timeline.GetName()!r}")
            job_id = project.AddRenderJob()
            if not job_id:
                raise ResolveError(f"Could not add a render job for {timeline.GetName()!r}")
            jobs.append(RenderJob(timeline.GetName(), job_id, file_name))
    finally:
        if original:
            project.SetCurrentTimeline(original)
    return jobs


def start_and_wait(resolve, jobs: list[RenderJob], on_progress=None, poll_seconds: float = 2.0) -> dict:
    """Start the given jobs; with `on_progress` block until rendering is done.

    Returns {job_id: final status dict}.
    """
    project = current_project(resolve)
    ids = [job.job_id for job in jobs]
    if not project.StartRendering(ids):
        raise ResolveError("Resolve refused to start rendering")
    if on_progress is None:
        return {}
    while project.IsRenderingInProgress():
        for job in jobs:
            on_progress(job, project.GetRenderJobStatus(job.job_id) or {})
        time.sleep(poll_seconds)
    return {job.job_id: project.GetRenderJobStatus(job.job_id) or {} for job in jobs}
