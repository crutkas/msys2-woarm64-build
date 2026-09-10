import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
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


class ProviderSchemaTests(unittest.TestCase):
    def test_package_name_archive_rows_are_adapted(self):
        export_path = Path("C:/provider/export.json")
        declarations = ASSEMBLER.generic_packages(
            export_path,
            {
                "schema": 1,
                "status": "complete",
                "packages": [{
                    "packageName": "mingw-w64-aarch64-python",
                    "archive": "packages/python.pkg.tar.zst",
                    "sha256": "1" * 64,
                }],
            },
            "python",
        )
        self.assertEqual("mingw-w64-aarch64-python", declarations[0]["name"])
        self.assertEqual(
            Path("C:/provider/packages/python.pkg.tar.zst"),
            declarations[0]["path"],
        )

    def test_conflicting_producer_row_aliases_are_rejected(self):
        with self.assertRaises(ASSEMBLER.ContractError):
            ASSEMBLER.generic_packages(
                Path("C:/provider/export.json"),
                {
                    "schema": 1,
                    "status": "complete",
                    "packages": [{
                        "name": "mingw-w64-aarch64-python",
                        "packageName": "mingw-w64-aarch64-other",
                        "path": "python.pkg.tar.zst",
                        "sha256": "1" * 64,
                    }],
                },
                "python",
            )

    def test_current_git_rows_are_read_without_legacy_layout(self):
        rows = ASSEMBLER.git_package_records({
            "packages": [{
                "packageName": "mingw-w64-aarch64-git",
                "archive": "packages/git.pkg.tar.zst",
                "sha256": "a" * 64,
            }]
        })
        self.assertEqual(1, len(rows))
        self.assertEqual(
            ("mingw-w64-aarch64-git", "packages/git.pkg.tar.zst", "a" * 64),
            ASSEMBLER.git_package_identity(rows[0]),
        )

    def test_git_handoff_cannot_mix_legacy_and_current_package_lists(self):
        with self.assertRaises(ASSEMBLER.ContractError):
            ASSEMBLER.git_package_records({
                "build": {"packages": []},
                "packages": [],
            })


class NestedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.outer = self.root / "outer.json"
        self.outer.write_text("{}", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def write_receipt(self, name, kind, *, native=True,
                      target="aarch64-pc-cygwin", cohort="d70"):
        receipt = {
            "schema": 1,
            "status": "verified",
            "kind": kind,
            "execution": {
                "native_process": native,
                "host_architecture": "arm64",
                "target": target,
            },
            "runtime": {
                "cohort": cohort,
                "sha256": "2" * 64,
            },
        }
        path = self.root / name
        path.write_text(json.dumps(receipt), encoding="utf-8")
        return {
            "kind": kind,
            "path": name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    def validate(self, evidence):
        return ASSEMBLER.validate_nested_evidence(
            self.outer,
            evidence,
            "Test evidence",
            ["native-build", "native-runtime"],
            ["aarch64-pc-cygwin"],
            "d70",
        )

    def test_valid_hash_bound_native_receipts_are_accepted(self):
        receipts = self.validate([
            self.write_receipt("build.json", "native-build"),
            self.write_receipt("runtime.json", "native-runtime"),
        ])
        self.assertEqual({"native-build", "native-runtime"},
                         {receipt["kind"] for receipt in receipts})

    def test_empty_nested_evidence_is_rejected(self):
        with self.assertRaises(ASSEMBLER.ContractError):
            self.validate([])

    def test_string_evidence_is_rejected(self):
        with self.assertRaises(ASSEMBLER.ContractError):
            self.validate(["verified-native"])

    def test_missing_receipt_is_rejected(self):
        with self.assertRaises(ASSEMBLER.ContractError):
            self.validate([{
                "kind": "native-build",
                "path": "missing.json",
                "sha256": "0" * 64,
            }])

    def test_tampered_receipt_is_rejected(self):
        reference = self.write_receipt("build.json", "native-build")
        (self.root / "build.json").write_text('{"tampered": true}', encoding="utf-8")
        with self.assertRaises(ASSEMBLER.ContractError):
            self.validate([reference])

    def test_non_native_receipt_is_rejected(self):
        with self.assertRaises(ASSEMBLER.ContractError):
            self.validate([
                self.write_receipt("build.json", "native-build", native=False),
                self.write_receipt("runtime.json", "native-runtime"),
            ])

    def test_foreign_target_is_rejected(self):
        with self.assertRaises(ASSEMBLER.ContractError):
            self.validate([
                self.write_receipt(
                    "build.json", "native-build", target="aarch64-w64-mingw32"
                ),
                self.write_receipt("runtime.json", "native-runtime"),
            ])

    def test_foreign_runtime_cohort_is_rejected(self):
        with self.assertRaises(ASSEMBLER.ContractError):
            self.validate([
                self.write_receipt("build.json", "native-build", cohort="old"),
                self.write_receipt("runtime.json", "native-runtime"),
            ])


class SystemDllContractTests(unittest.TestCase):
    def test_narrow_system_exceptions_do_not_allow_unknown_imports(self):
        contract = json.loads(
            (SCRIPT.parents[1] / "contracts" / "full-release-v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("msi.dll", contract["system_dlls"])
        self.assertIn("dbghelp.dll", contract["system_dlls"])
        self.assertNotIn("unknown-provider.dll", contract["system_dlls"])


if __name__ == "__main__":
    unittest.main()
