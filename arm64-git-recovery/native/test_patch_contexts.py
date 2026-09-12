import importlib.util
from pathlib import Path
import unittest

from sources import ContractError

spec = importlib.util.spec_from_file_location("package_prepare", Path(__file__).with_name("prepare-posix-tools.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PackageContextControls(unittest.TestCase):
    def test_context_only_changes_preserve_patch_operations(self):
        for key, replacements in module.PATCH_CONTEXTS.items():
            with self.subTest(key=key):
                original = "-old operation\n+new operation\n" + "".join(before for before, _ in replacements)
                adapted = module.adapt_package_context(key, original)
                self.assertTrue(adapted.startswith("-old operation\n+new operation\n"))
                for before, after in reversed(replacements):
                    adapted = adapted.replace(after, before)
                self.assertEqual(adapted, original)

    def test_missing_or_duplicate_context_is_rejected(self):
        for key, replacements in module.PATCH_CONTEXTS.items():
            original = "".join(before for before, _ in replacements)
            for text in ("unrelated", original + original):
                with self.subTest(key=key, text=text), self.assertRaises(ContractError):
                    module.adapt_package_context(key, text)


if __name__ == "__main__":
    unittest.main()
