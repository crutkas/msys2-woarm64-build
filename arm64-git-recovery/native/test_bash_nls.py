import importlib
import unittest

from sources import ContractError

nls = importlib.import_module("build-bash-nls")


class BashNlsInputControls(unittest.TestCase):
    def test_bare_relocation_macro_is_rejected_before_launch(self):
        for invocation in ("gl_RELOCATABLE", "  gl_RELOCATABLE   ", "gl_RELOCATABLE([src])"):
            with self.subTest(invocation=invocation):
                with self.assertRaisesRegex(ContractError, "source generation"):
                    nls.validate_generated_configure("#!/bin/sh\n" + invocation + "\n", "configure")

    def test_expanded_configure_and_comments_are_not_macro_calls(self):
        nls.validate_generated_configure("# gl_RELOCATABLE\nchecking_relocatable=yes\n", "configure")

    def test_bridge_and_runtime_keep_static_shared_payload_contracts(self):
        for path in ("usr/lib/libiconv.a", "usr/lib/libiconv.dll.a", "usr/bin/iconv.exe"):
            self.assertIn(path, nls.required("iconv-bridge"))
            self.assertIn(path, nls.required("iconv-full"))
        for path in ("usr/bin/msys-intl-8.dll", "usr/lib/libintl.a", "usr/lib/libintl.dll.a"):
            self.assertIn(path, nls.required("gettext-runtime"))


if __name__ == "__main__":
    unittest.main()
