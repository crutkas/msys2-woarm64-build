import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("capture", Path(__file__).with_name("capture-native-exception.py"))
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


class CaptureArgumentsTests(unittest.TestCase):
    def test_child_option_separator_is_not_forwarded(self):
        argv = ["capture", "--executable", "sqlite3.exe", "--output", "proof", "--", "-batch", ":memory:", "SELECT 1"]
        with patch("sys.argv", argv), patch.object(capture, "capture") as called:
            capture.main()
        self.assertEqual(called.call_args.args[1], ["-batch", ":memory:", "SELECT 1"])

    def test_existing_positional_arguments_unchanged(self):
        argv = ["capture", "--executable", "tclsh.exe", "--output", "proof", "fixture.tcl"]
        with patch("sys.argv", argv), patch.object(capture, "capture") as called:
            capture.main()
        self.assertEqual(called.call_args.args[1], ["fixture.tcl"])
