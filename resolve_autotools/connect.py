"""Connect to a running DaVinci Resolve instance."""

from __future__ import annotations

import importlib.util
import os
import sys


class ResolveError(RuntimeError):
    """Anything that stops an operation: no Resolve, no project, missing timeline..."""


_DEFAULT_MODULE_DIRS = {
    "win": r"%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules",
    "darwin": "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
    "linux": "/opt/resolve/Developer/Scripting/Modules",
}


def _load_script_module():
    try:
        import DaVinciResolveScript  # noqa: F401  (on PYTHONPATH)

        return sys.modules["DaVinciResolveScript"]
    except ImportError:
        pass

    candidates = []
    if os.getenv("RESOLVE_SCRIPT_API"):
        candidates.append(os.path.join(os.environ["RESOLVE_SCRIPT_API"], "Modules"))
    for platform, path in _DEFAULT_MODULE_DIRS.items():
        if sys.platform.startswith(platform):
            candidates.append(os.path.expandvars(path))

    for folder in candidates:
        path = os.path.join(folder, "DaVinciResolveScript.py")
        if not os.path.isfile(path):
            continue
        spec = importlib.util.spec_from_file_location("DaVinciResolveScript", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["DaVinciResolveScript"] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:  # ImportError, or SystemError when fusionscript can't initialise
            sys.modules.pop("DaVinciResolveScript", None)
            raise ResolveError(
                f"Found the Resolve scripting module but fusionscript failed to load ({type(exc).__name__}: "
                f"{exc or 'no details'}). Use a 64-bit Python version supported by your Resolve "
                f"(see README, section 'Setup'), not {sys.version.split()[0]}."
            ) from exc
        return sys.modules["DaVinciResolveScript"]

    raise ResolveError(
        "DaVinciResolveScript module not found. Install DaVinci Resolve or set RESOLVE_SCRIPT_API "
        "(see README, section 'Setup')."
    )


def get_resolve(existing=None):
    """Return the Resolve app object.

    Inside Resolve (Workspace > Scripts or the Console) pass the global `resolve`
    as `existing`. Outside Resolve the official scripting module is used.
    """
    if existing is not None:
        return existing
    module = _load_script_module()
    resolve = module.scriptapp("Resolve")
    if resolve is None:
        raise ResolveError(
            "Could not connect to DaVinci Resolve. Make sure Resolve is running and "
            "Preferences > System > General > 'External scripting using' is set to 'Local'."
        )
    return resolve
