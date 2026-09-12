import importlib.util
from pathlib import Path
import unittest

from sources import ContractError

spec = importlib.util.spec_from_file_location("posix_prepare", Path(__file__).with_name("prepare-posix-tools.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AutopointArchiveControls(unittest.TestCase):
    def patch(self):
        return "".join(
            f"--- archive-orig/gettext-0.22.{version}/m4/build-to-host.m4.orig\n"
            f"+++ archive/gettext-0.22.{version}/m4/build-to-host.m4\n"
            "@@ -1,3 +1,3 @@\n-    cygwin*)\n+    cygwin* | msys*)\n"
            "       case \"$host_os\" in\n         mingw*)\n"
            for version in range(1, 5))

    def test_only_four_context_lines_change(self):
        original = self.patch()
        adapted, paths = module.adapt_autopoint_patch(original)
        self.assertEqual(len(paths), 4)
        self.assertEqual(adapted.replace("         mingw* | windows*)\n", "         mingw*)\n"), original)
        self.assertEqual(adapted.count("+    cygwin* | msys*)"), 4)

    def test_missing_duplicate_or_changed_context_is_rejected(self):
        original = self.patch()
        for text in (original.replace("gettext-0.22.4", "gettext-0.22.5"),
                     original + original, original.replace("         mingw*)", "         different*)", 1)):
            with self.subTest(text=text), self.assertRaises(ContractError):
                module.adapt_autopoint_patch(text)


if __name__ == "__main__":
    unittest.main()
