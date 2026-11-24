"""Command line: python -m resolve_autotools <command> ..."""

from __future__ import annotations

import argparse
import sys

from . import __version__, connect, ops
from .connect import ResolveError
from .markers import parse_markers_csv
from .timecode import frames_to_tc


def _cmd_info(resolve, args) -> int:
    project = ops.current_project(resolve)
    print(f"Resolve: {resolve.GetProductName()} {resolve.GetVersionString()}")
    print(f"Project: {project.GetName()}")
    current = project.GetCurrentTimeline()
    for timeline in ops.timelines(project):
        rate = ops.timeline_rate(timeline)
        length = int(timeline.GetEndFrame()) - int(timeline.GetStartFrame())
        mark = "*" if current and timeline.GetName() == current.GetName() else " "
        print(f" {mark} {timeline.GetName()}  ({rate.fps:g} fps{' DF' if rate.drop_frame else ''}, "
              f"{frames_to_tc(length, rate)}, start {timeline.GetStartTimecode()})")
    presets = project.GetRenderPresetList() or []
    print(f"Render presets: {', '.join(presets) or 'none'}")
    return 0


def _cmd_import(resolve, args) -> int:
    report = ops.import_folder(resolve, args.folder, args.bin, args.timeline, args.recursive)
    print(f"Imported {len(report.clips)} clips into bin '{report.bin_name}' "
          f"({len(report.scan.sequences)} frame sequences, {len(report.scan.files)} files)")
    for seq in report.scan.sequences:
        print(f"  sequence {seq.name}: {seq.frame_count} frames")
    for warning in report.scan.warnings:
        print(f"  warning: {warning}")
    if report.scan.skipped:
        print(f"  skipped {len(report.scan.skipped)} unsupported files: "
              + ", ".join(p.name for p in report.scan.skipped[:5]) + (" ..." if len(report.scan.skipped) > 5 else ""))
    if report.timeline_name:
        print(f"Created timeline '{report.timeline_name}'")
    return 0


def _cmd_markers(resolve, args) -> int:
    parsed = parse_markers_csv(args.csv)
    for error in parsed.errors:
        print(f"  CSV error: {error}", file=sys.stderr)
    if not parsed.markers:
        print("No valid markers in the CSV", file=sys.stderr)
        return 1
    timeline = ops.find_timeline(ops.current_project(resolve), args.timeline)
    report = ops.apply_markers(timeline, parsed.markers)
    print(f"Added {len(report.added)} markers to '{timeline.GetName()}'")
    for marker, reason in report.failed:
        print(f"  line {marker.line} ({marker.timecode}): {reason}", file=sys.stderr)
    return 0 if not (report.failed or parsed.errors) else 2


def _cmd_shotlist(resolve, args) -> int:
    timeline = ops.find_timeline(ops.current_project(resolve), args.timeline)
    count = ops.write_shot_list(timeline, args.output)
    print(f"Wrote {count} shots from '{timeline.GetName()}' to {args.output}")
    return 0


def _cmd_render(resolve, args) -> int:
    jobs = ops.queue_renders(resolve, args.preset, args.out, args.timelines, args.name)
    for job in jobs:
        print(f"Queued '{job.timeline}' -> {job.file_name}  (job {job.job_id})")
    if not (args.start or args.wait):
        print("Jobs are in the Render Queue. Use --start to render now.")
        return 0

    def progress(job, status):
        print(f"  {job.timeline}: {status.get('JobStatus', '?')} {status.get('CompletionPercentage', 0)}%")

    results = ops.start_and_wait(resolve, jobs, progress if args.wait else None)
    if not args.wait:
        print("Rendering started.")
        return 0
    failed = [jid for jid, st in results.items() if st.get("JobStatus") not in ("Complete", "Completed")]
    print("All renders finished." if not failed else f"{len(failed)} job(s) did not complete: {failed}")
    return 0 if not failed else 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="resolve_autotools", description="Automate repetitive DaVinci Resolve tasks.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("info", help="show project, timelines and render presets").set_defaults(func=_cmd_info)

    p = sub.add_parser("import", help="import a folder (frame sequences become single clips)")
    p.add_argument("folder")
    p.add_argument("--bin", help="bin name (default: folder name)")
    p.add_argument("--timeline", help="also create a timeline with this name")
    p.add_argument("--recursive", action="store_true", help="include subfolders")
    p.set_defaults(func=_cmd_import)

    p = sub.add_parser("markers", help="add markers from a review-notes CSV")
    p.add_argument("csv")
    p.add_argument("--timeline", help="timeline name (default: current)")
    p.set_defaults(func=_cmd_markers)

    p = sub.add_parser("shotlist", help="export the edit as a CSV shot list")
    p.add_argument("output")
    p.add_argument("--timeline", help="timeline name (default: current)")
    p.set_defaults(func=_cmd_shotlist)

    p = sub.add_parser("render", help="queue (and optionally run) renders for several timelines")
    p.add_argument("--preset", required=True, help="render preset name, e.g. 'YouTube - 1080p'")
    p.add_argument("--out", required=True, help="output folder")
    p.add_argument("--timelines", nargs="+", help="timeline names (default: all)")
    p.add_argument("--name", default="{project}_{timeline}_{date}", help="file name template")
    p.add_argument("--start", action="store_true", help="start rendering after queueing")
    p.add_argument("--wait", action="store_true", help="start and wait, printing progress")
    p.set_defaults(func=_cmd_render)
    return parser


def main(argv: list[str] | None = None, resolve=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(connect.get_resolve(resolve), args)
    except (ResolveError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
