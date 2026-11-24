"""Workspace > Scripts > AutoTools - Export Shot List

Copy this file to the Resolve scripts folder (see README) and set RESOLVE_AUTOTOOLS_PATH
to the repository folder, or edit REPO_PATH below.
Exports the current timeline as <Desktop>/<timeline>_shotlist.csv
"""

import os
import sys
from pathlib import Path

REPO_PATH = os.getenv("RESOLVE_AUTOTOOLS_PATH", r"")  # e.g. r"C:\tools\resolve-autotools"
if REPO_PATH and REPO_PATH not in sys.path:
    sys.path.insert(0, REPO_PATH)

from resolve_autotools import connect, ops  # noqa: E402

try:
    app = resolve  # noqa: F821  (injected by Resolve)
except NameError:
    try:
        app = bmd.scriptapp("Resolve")  # noqa: F821
    except NameError:
        app = None

try:
    timeline = ops.find_timeline(ops.current_project(connect.get_resolve(app)))
    safe = ops.render_name("{timeline}", "", timeline.GetName())
    out = Path.home() / "Desktop" / f"{safe}_shotlist.csv"
    count = ops.write_shot_list(timeline, out)
    print(f"[AutoTools] {count} shots -> {out}")
except Exception as exc:  # shown in Workspace > Console
    print(f"[AutoTools] Error: {exc}")
