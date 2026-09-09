import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "assemble-full-release.py"
SPEC = importlib.util.spec_from_file_location("assemble_full_release", SCRIPT)
ASSEMBLER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(ASSEMBLER)


class VersionConstraintTests(unittest.TestCase):
    def test_newer_package_does_not_match_older_conflict_range(self):
        self.assertFalse(
            ASSEMBLER.version_satisfies("1.19-1", "libiconv<1.18-2")
        )

    def test_matching_package_matches_conflict_range(self):
        self.assertTrue(
            ASSEMBLER.version_satisfies("1.18-1", "libiconv<1.18-2")
        )

    def test_dependency_without_pkgrel_matches_package_release(self):
        self.assertTrue(
            ASSEMBLER.version_satisfies("1.19-1", "libiconv=1.19")
        )

    def test_epoch_takes_precedence(self):
        self.assertGreater(
            ASSEMBLER.compare_versions("2:1.0-1", "1:99.0-1"),
            0,
        )


class PackageLinkTests(unittest.TestCase):
    def test_relative_directory_symlink_materializes_descendants(self):
        packages = {
            "ncurses": {
                "roles": ["native-msys-ncurses"],
                "files": {
                    "usr/share/terminfo/x/xterm": {
                        "sha256": "0" * 64,
                        "size": 1,
                        "data": b"x",
                    }
                },
                "links": {
                    "usr/lib/terminfo": {
                        "target": "../share/terminfo",
                        "kind": "symlink",
                    }
                },
            }
        }
        files, links = ASSEMBLER.merge_payload(
            packages,
            {"ncurses"},
            {"excluded_payload_globs": []},
        )

        self.assertEqual({}, links)
        self.assertEqual(
            "usr/share/terminfo/x/xterm",
            files["usr/lib/terminfo/x/xterm"]["materialized_from"],
        )
        self.assertEqual(["ncurses"], files["usr/lib/terminfo/x/xterm"]["owners"])

    def test_relative_symlink_cannot_escape_archive_root(self):
        with self.assertRaises(ASSEMBLER.ContractError):
            ASSEMBLER.safe_symlink_target("usr/lib/terminfo", "../../../outside")


if __name__ == "__main__":
    unittest.main()
