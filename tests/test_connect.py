import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from resolve_autotools import connect
from resolve_autotools.connect import ResolveError, get_resolve


class ConnectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.modules = Path(self.tmp.name) / "Modules"
        self.modules.mkdir()
        sys.modules.pop("DaVinciResolveScript", None)
        self.env = mock.patch.dict(os.environ, {"RESOLVE_SCRIPT_API": self.tmp.name})
        self.env.start()
        self.no_defaults = mock.patch.object(connect, "_DEFAULT_MODULE_DIRS", {})
        self.no_defaults.start()

    def tearDown(self):
        self.no_defaults.stop()
        self.env.stop()
        sys.modules.pop("DaVinciResolveScript", None)
        self.tmp.cleanup()

    def write_module(self, body: str) -> None:
        (self.modules / "DaVinciResolveScript.py").write_text(body, encoding="utf-8")

    def test_existing_object_is_used_as_is(self):
        marker = object()
        self.assertIs(get_resolve(marker), marker)

    def test_connects_through_official_module(self):
        self.write_module("def scriptapp(name):\n    return {'app': name}\n")
        self.assertEqual(get_resolve(), {"app": "Resolve"})

    def test_resolve_not_running(self):
        self.write_module("def scriptapp(name):\n    return None\n")
        with self.assertRaisesRegex(ResolveError, "External scripting using"):
            get_resolve()

    def test_fusionscript_init_failure_is_explained(self):
        # Real case: Resolve 20.1's fusionscript.dll under Python 3.13 raises SystemError, not ImportError.
        self.write_module("raise SystemError('initialization of fusionscript failed')\n")
        with self.assertRaisesRegex(ResolveError, "fusionscript failed to load .*SystemError"):
            get_resolve()
        self.assertNotIn("DaVinciResolveScript", sys.modules)

    def test_module_missing(self):
        with self.assertRaisesRegex(ResolveError, "module not found"):
            get_resolve()


if __name__ == "__main__":
    unittest.main()
