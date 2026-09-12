import unittest

from fido_build_inputs import rewrite_pc
from sources import ContractError


class FidoMetadataControls(unittest.TestCase):
    text = "prefix=/usr\nlibdir=${prefix}/lib\nincludedir=${prefix}/include\nVersion: 0.14.0\nLibs: -L${libdir} -lcbor\nCflags: -I${includedir}\n"

    def test_only_real_path_variables_and_header_roots_change(self):
        result = rewrite_pc(self.text, {"libdir": "C:/build/src", "includedir": "C:/source/src"}, ["C:/build", "C:/build/src"])
        self.assertIn("Version: 0.14.0\nLibs: -L${libdir} -lcbor", result)
        self.assertIn("Cflags: -I${includedir} -IC:/build -IC:/build/src", result)
        self.assertIn("prefix=/usr", result)

    def test_ambiguous_or_unrepresentable_metadata_rejected(self):
        for text, variables in ((self.text + "libdir=duplicate\n", {"libdir": "C:/build"}),
                                (self.text, {"missing": "C:/build"}),
                                (self.text, {"libdir": "C:/ambiguous path"})):
            with self.assertRaises(ContractError):
                rewrite_pc(text, variables)


if __name__ == "__main__":
    unittest.main()
