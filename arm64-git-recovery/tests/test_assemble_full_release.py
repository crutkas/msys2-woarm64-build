import importlib.util
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "assemble-full-release.py"
CONTRACT = Path(__file__).resolve().parents[1] / "contracts" / "full-release-v1.json"
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


class ProviderPayloadFilterTests(unittest.TestCase):
    def test_terminal_libraries_do_not_override_git_inputrc(self):
        package = {"roles": ["native-msys-terminal-libraries"]}
        contract = {
            "excluded_payload_globs": [],
            "provider_role_payload_globs": {
                "native-msys-terminal-libraries": ["usr/**"],
            },
            "required_files": [],
        }

        self.assertTrue(
            ASSEMBLER.include_payload_file(package, "usr/bin/msys-readline8.dll", contract)
        )
        self.assertFalse(
            ASSEMBLER.include_payload_file(package, "etc/inputrc", contract)
        )


class ImportProviderTests(unittest.TestCase):
    def test_executable_export_module_can_satisfy_an_import(self):
        self.assertTrue(ASSEMBLER.is_import_provider("usr/bin/bash.exe"))

    def test_dll_can_satisfy_an_import(self):
        self.assertTrue(ASSEMBLER.is_import_provider("usr/bin/msys-2.0.dll"))

    def test_python_extension_is_not_a_general_import_provider(self):
        self.assertFalse(ASSEMBLER.is_import_provider("usr/lib/example.pyd"))


class RejectedArchiveTests(unittest.TestCase):
    def rejection_contract(self, rejected_hash):
        return {
            "rejected_package_archives": [{
                "name": "mingw-w64-aarch64-gettext",
                "sha256": rejected_hash,
                "evidence_sha256": "9" * 64,
                "reason": "mislabeled payload",
            }],
        }

    def test_rejected_declared_archive_identity_is_a_hard_failure(self):
        rejected_hash = "7" * 64
        declarations = [{
            "name": "mingw-w64-aarch64-gettext",
            "sha256": rejected_hash,
        }]

        with self.assertRaisesRegex(
            ASSEMBLER.ContractError,
            "Rejected package archive supplied",
        ):
            ASSEMBLER.validate_rejected_archives(
                self.rejection_contract(rejected_hash),
                declarations,
            )

    def test_rejected_inspected_archive_identity_is_a_hard_failure(self):
        rejected_hash = "7" * 64
        packages = {
            "mingw-w64-aarch64-gettext": {
                "name": "mingw-w64-aarch64-gettext",
                "archive_sha256": rejected_hash,
            },
        }

        with self.assertRaisesRegex(
            ASSEMBLER.ContractError,
            "Rejected package archive supplied",
        ):
            ASSEMBLER.validate_rejected_archives(
                self.rejection_contract(rejected_hash),
                packages,
            )

    def test_different_archive_identity_is_not_rejected(self):
        ASSEMBLER.validate_rejected_archives(
            self.rejection_contract("7" * 64),
            {
                "mingw-w64-aarch64-gettext": {
                    "name": "mingw-w64-aarch64-gettext",
                    "archive_sha256": "8" * 64,
                },
            },
        )


class PrivatePayloadMarkerTests(unittest.TestCase):
    def test_private_producer_root_spellings_are_blocked(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        for marker in (
            rb"C:\ap12-ca5f\stage",
            rb"C:\\ag-utils-e138-01\\stage",
            b"C:/ag-readline-e138-01/stage",
            b"/c/ap11-native-provider-intake/stage",
            b"/mnt/c/ag-bash-e138-01/stage",
        ):
            with self.subTest(marker=marker):
                blockers, _ = ASSEMBLER.validate_payload(
                    contract,
                    {
                        "usr/share/doc/private-path.txt": {
                            "data": marker,
                            "sha256": hashlib.sha256(marker).hexdigest(),
                            "size": len(marker),
                        },
                    },
                    set(),
                    None,
                )
                self.assertTrue(any(
                    blocker.startswith(
                        "private-path-or-marker:usr/share/doc/private-path.txt:"
                    )
                    for blocker in blockers
                ))

    def arm64_pe_with_marker(self, marker):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        data = bytearray(512)
        data[0:2] = b"MZ"
        struct.pack_into("<I", data, 0x3C, 0x80)
        data[0x80:0x84] = b"PE\0\0"
        struct.pack_into("<H", data, 0x84, 0xAA64)
        struct.pack_into("<H", data, 0x86, 0)
        struct.pack_into("<H", data, 0x94, 0xF0)
        struct.pack_into("<H", data, 0x98, 0x20B)
        data.extend(marker)
        return contract, bytes(data)

    def test_private_operational_prefix_in_arm64_pe_is_blocked(self):
        contract, payload = self.arm64_pe_with_marker(
            b"C:/ag-producer/private/msys64/usr/share/locale"
        )
        blockers, classifications = ASSEMBLER.validate_payload(
            contract,
            {
                "usr/bin/private.exe": {
                    "data": payload,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                },
            },
            set(),
            None,
        )

        self.assertIn("usr/bin/private.exe", classifications["native_pe_arm64"])
        self.assertTrue(any(
            blocker.startswith(
                "private-runtime-path:usr/bin/private.exe:"
            )
            for blocker in blockers
        ))

    def test_source_provenance_path_in_arm64_pe_is_not_a_relocation_blocker(self):
        contract, payload = self.arm64_pe_with_marker(
            b"/root/arm64-vnext-20260905/private/source.c"
        )
        blockers, _ = ASSEMBLER.validate_payload(
            contract,
            {
                "usr/bin/private.exe": {
                    "data": payload,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                },
            },
            set(),
            None,
        )

        self.assertFalse(any(
            blocker.startswith("private-runtime-path:usr/bin/private.exe:")
            for blocker in blockers
        ))

    def test_staged_include_path_in_arm64_pe_is_not_a_relocation_blocker(self):
        contract, payload = self.arm64_pe_with_marker(
            b"C:/ag-producer/private/stage/usr/include/readline/readline.h"
        )
        blockers, _ = ASSEMBLER.validate_payload(
            contract,
            {
                "usr/bin/private.exe": {
                    "data": payload,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                },
            },
            set(),
            None,
        )

        self.assertFalse(any(
            blocker.startswith("private-runtime-path:usr/bin/private.exe:")
            for blocker in blockers
        ))

    def test_toolchain_include_path_in_arm64_pe_is_not_a_relocation_blocker(self):
        contract, payload = self.arm64_pe_with_marker(
            b"C:/ap-builder/prefix/mingwarm64/aarch64-w64-mingw32/include/sys"
        )
        blockers, _ = ASSEMBLER.validate_payload(
            contract,
            {
                "mingwarm64/bin/private.dll": {
                    "data": payload,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                },
            },
            set(),
            None,
        )

        self.assertFalse(any(
            blocker.startswith(
                "private-runtime-path:mingwarm64/bin/private.dll:"
            )
            for blocker in blockers
        ))

    def test_private_mingwarm64_bin_path_in_arm64_pe_is_blocked(self):
        contract, payload = self.arm64_pe_with_marker(
            b"C:/ap-builder/prefix/mingwarm64/bin"
        )
        blockers, _ = ASSEMBLER.validate_payload(
            contract,
            {
                "mingwarm64/bin/private.dll": {
                    "data": payload,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                },
            },
            set(),
            None,
        )

        self.assertTrue(any(
            blocker.startswith(
                "private-runtime-path:mingwarm64/bin/private.dll:"
            )
            for blocker in blockers
        ))


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
