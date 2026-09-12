import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
import zipfile


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "arm64-git-recovery"
    / "scripts"
    / "assemble-full-release.py"
)
SPEC = importlib.util.spec_from_file_location("full_release_assembler", SCRIPT)
ASSEMBLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ASSEMBLER)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return sha256(path)


def minimal_pe(machine=0xAA64):
    data = bytearray(0x200)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 0x84, machine, 0, 0, 0, 0, 0xF0, 0)
    struct.pack_into("<H", data, 0x98, 0x20B)
    return bytes(data)


def package(path, name, files, depends=(), provides=(), conflicts=()):
    info = [
        f"pkgname = {name}",
        "pkgver = 1-1",
        "arch = any",
        *[f"depend = {value}" for value in depends],
        *[f"provides = {value}" for value in provides],
        *[f"conflict = {value}" for value in conflicts],
    ]
    with tarfile.open(path, "w:zst") as archive:
        payload = ("\n".join(info) + "\n").encode()
        member = tarfile.TarInfo(".PKGINFO")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))
        for rel, data in files.items():
            member = tarfile.TarInfo(rel)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return {"name": name, "path": str(path), "sha256": sha256(path)}


class FullReleaseAssemblerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_hash_mismatch_fails_closed(self):
        path = self.root / "one.pkg.tar.zst"
        item = package(path, "one", {"mingwarm64/bin/one.exe": minimal_pe()})
        with self.assertRaisesRegex(ASSEMBLER.ContractError, "hash mismatch"):
            ASSEMBLER.inspect_archive(path, "0" * 64, item["name"])

    def test_wrong_architecture_is_rejected(self):
        files = {
            "mingwarm64/bin/tool.exe": {
                "data": minimal_pe(0x8664), "size": 512, "sha256": "x", "owners": ["tool"]
            }
        }
        contract = {
            "required_files": [],
            "required_documentation_globs": [],
            "required_license_globs": [],
            "managed_files": [],
            "system_dlls": [],
            "forbidden_payload_markers": [],
            "forbidden_nonrelease_markers": [],
            "generated_gitconfig": {"path": "etc/gitconfig"},
        }
        with self.assertRaisesRegex(ASSEMBLER.ContractError, "Non-ARM64"):
            ASSEMBLER.validate_payload(contract, files, {"tool"}, {"sha256": "x"})

    def test_private_path_leak_is_rejected(self):
        data = b"producer=C:\\ap99-private\\build\n"
        files = {
            "mingwarm64/share/config.txt": {
                "data": data, "size": len(data), "sha256": "x", "owners": ["tool"]
            }
        }
        contract = {
            "required_files": [],
            "required_documentation_globs": [],
            "required_license_globs": [],
            "managed_files": [],
            "system_dlls": [],
            "forbidden_payload_markers": ["C:\\ap"],
            "forbidden_nonrelease_markers": [],
            "generated_gitconfig": {"path": "etc/gitconfig"},
        }
        blockers, _ = ASSEMBLER.validate_payload(
            contract, files, {"tool"}, {"sha256": "x"}
        )
        self.assertIn(
            "private-path-or-marker:mingwarm64/share/config.txt:c:\\ap", blockers
        )

    def test_tls_alternatives_cannot_collide(self):
        packages = {
            "curl-a": {
                "name": "curl-a", "depends": [], "provides": ["curl=1"],
                "conflicts": ["curl-b"], "files": {}, "links": {}
            },
            "curl-b": {
                "name": "curl-b", "depends": [], "provides": ["curl=1"],
                "conflicts": ["curl-a"], "files": {}, "links": {}
            },
        }
        with self.assertRaisesRegex(ASSEMBLER.ContractError, "conflict"):
            ASSEMBLER.resolve_packages(packages, ["curl-a", "curl-b"], {})

    def test_missing_python_and_git_split_are_reported(self):
        packages = {
            "mingw-w64-aarch64-git": {
                "name": "mingw-w64-aarch64-git", "depends": [],
                "provides": [], "conflicts": [],
                "files": {}, "links": {}
            }
        }
        selected, blockers = ASSEMBLER.resolve_packages(
            packages, ["mingw-w64-aarch64-git", "mingw-w64-aarch64-python"], {}
        )
        self.assertEqual({"mingw-w64-aarch64-git"}, selected)
        self.assertEqual(["mingw-w64-aarch64-python"], blockers)
        split_blockers = ASSEMBLER.validate_git_splits(
            {
                "expected_git_splits": [
                    "mingw-w64-aarch64-git",
                    "mingw-w64-aarch64-git-p4",
                ]
            },
            packages,
        )
        self.assertEqual(
            ["missing-git-split:mingw-w64-aarch64-git-p4"], split_blockers
        )

    def test_archive_identity_and_arm64_payload(self):
        path = self.root / "native.pkg.tar.zst"
        item = package(path, "native", {"mingwarm64/bin/native.exe": minimal_pe()})
        inspected = ASSEMBLER.inspect_archive(path, item["sha256"], "native")
        self.assertEqual("native", inspected["name"])
        self.assertEqual("0xaa64", ASSEMBLER.pe_info(
            inspected["files"]["mingwarm64/bin/native.exe"]["data"]
        )["machine"])

    def test_managed_allowlist_does_not_grant_admission(self):
        contract = {
            "managed_components": [{
                "package": "gcm",
                "admission_version": 1,
                "status": "approved-for-native-arm64-distribution",
                "decision": "user-approved",
                "host_architecture": "arm64",
                "runtime_support_status": "verified",
                "files": ["mingwarm64/bin/gcm.exe"],
            }]
        }
        blockers, admitted = ASSEMBLER.validate_managed_admissions(
            contract,
            {"managed_admissions": []},
            {
                "gcm": {
                    "version": "1-1",
                    "files": {
                        "mingwarm64/bin/gcm.exe": {"sha256": "a" * 64}
                    },
                }
            },
        )
        self.assertEqual(["managed-admission-not-supplied:gcm"], blockers)
        self.assertEqual([], admitted)

    def test_source_identity_mismatch_is_rejected(self):
        contract = {
            "source_identity": {
                "git_tag": "v2.55.0.windows.5",
                "git_commit": "a" * 40,
                "git_recipe_sha256": "b" * 64,
                "network_recipe_commit": "c" * 40,
            }
        }
        git = {
            "source": {
                "tag": "v2.55.0.windows.5",
                "commit": "d" * 40,
                "recipeSha256": "b" * 64,
            }
        }
        network = {"pinned_recipe": {"commit": "c" * 40}}
        with self.assertRaisesRegex(ASSEMBLER.ContractError, "Git commit"):
            ASSEMBLER.validate_source_identity(contract, git, network)

    def test_provider_export_accepts_package_name_and_archive_aliases(self):
        archive = self.root / "native.pkg.tar.zst"
        item = package(
            archive, "mingw-w64-aarch64-native",
            {"mingwarm64/bin/native.exe": minimal_pe()},
        )
        declarations = ASSEMBLER.generic_packages(
            self.root / "export.json",
            {
                "schema": 1,
                "status": "exported",
                "packages": [{
                    "packageName": item["name"],
                    "archive": archive.name,
                    "sha256": item["sha256"],
                }],
            },
            "native-provider",
        )
        self.assertEqual(item["name"], declarations[0]["name"])
        self.assertEqual(archive, declarations[0]["path"])

    def test_filtered_provider_role_excludes_build_tools(self):
        package_record = {
            "roles": ["native-python"],
            "name": "mingw-w64-aarch64-gcc",
        }
        contract = {
            "required_files": ["mingwarm64/bin/python.exe"],
            "excluded_payload_globs": [],
            "provider_role_payload_globs": {
                "native-python": [
                    "mingwarm64/bin/*.dll",
                    "mingwarm64/lib/python*/**",
                ]
            },
        }
        self.assertTrue(ASSEMBLER.include_payload_file(
            package_record, "mingwarm64/bin/libgcc_s_seh-1.dll", contract
        ))
        self.assertFalse(ASSEMBLER.include_payload_file(
            package_record, "mingwarm64/bin/gcc.exe", contract
        ))
        self.assertTrue(ASSEMBLER.include_payload_file(
            package_record, "mingwarm64/bin/python.exe", contract
        ))

    def test_corrected_git_handoff_inherits_prior_recipe_identity(self):
        prior_path = self.root / "prior.json"
        prior = {
            "source": {
                "tag": "v2.55.0.windows.5",
                "commit": "a" * 40,
                "makepkgArchiveSha256": "b" * 64,
                "recipeSha256": "c" * 64,
            },
            "build": {
                "packages": [
                    {
                        "packageName": "mingw-w64-aarch64-git",
                        "file": "git.pkg.tar.zst",
                        "sha256": "d" * 64,
                    },
                    {
                        "packageName": "mingw-w64-aarch64-git-p4",
                        "file": "git-p4.pkg.tar.zst",
                        "sha256": "e" * 64,
                    },
                ]
            },
        }
        prior_hash = write_json(prior_path, prior)
        current = {
            "source": {
                "tag": "v2.55.0.windows.5",
                "commit": "a" * 40,
                "makepkgArchiveSha256": "b" * 64,
            },
            "immutablePriorHandoff": {
                "path": str(prior_path),
                "sha256": prior_hash,
                "preserved": True,
            },
            "gitP4Integration": {
                "oldArchiveSha256": "e" * 64,
                "newArchiveSha256": "f" * 64,
                "declaredDependency": "mingw-w64-aarch64-python",
            },
            "packages": [
                {
                    "packageName": "mingw-w64-aarch64-git",
                    "archive": "git.pkg.tar.zst",
                    "sha256": "d" * 64,
                },
                {
                    "packageName": "mingw-w64-aarch64-git-p4",
                    "archive": "git-p4.pkg.tar.zst",
                    "sha256": "f" * 64,
                },
            ],
        }
        source, references = ASSEMBLER.resolve_git_source_identity(
            self.root / "current.json", current
        )
        self.assertEqual("c" * 64, source["recipeSha256"])
        self.assertEqual("git-source-provenance", references[0]["role"])

    def test_corrected_git_handoff_rejects_unrelated_split_changes(self):
        prior_path = self.root / "prior.json"
        prior_hash = write_json(prior_path, {
            "source": {
                "tag": "v2.55.0.windows.5",
                "commit": "a" * 40,
                "makepkgArchiveSha256": "b" * 64,
                "recipeSha256": "c" * 64,
            },
            "build": {
                "packages": [{
                    "packageName": "mingw-w64-aarch64-git",
                    "file": "git.pkg.tar.zst",
                    "sha256": "d" * 64,
                }]
            },
        })
        current = {
            "source": {
                "tag": "v2.55.0.windows.5",
                "commit": "a" * 40,
                "makepkgArchiveSha256": "b" * 64,
            },
            "immutablePriorHandoff": {
                "path": str(prior_path),
                "sha256": prior_hash,
                "preserved": True,
            },
            "packages": [{
                "packageName": "mingw-w64-aarch64-git",
                "archive": "git.pkg.tar.zst",
                "sha256": "e" * 64,
            }],
        }
        with self.assertRaisesRegex(
            ASSEMBLER.ContractError, "packages other than git-p4"
        ):
            ASSEMBLER.resolve_git_source_identity(
                self.root / "current.json", current
            )

    def test_complete_synthetic_release_assembles(self):
        git_dir = self.root / "git"
        package_dir = git_dir / "git-packages"
        package_dir.mkdir(parents=True)
        git = package(
            package_dir / "git.pkg.tar.zst",
            "mingw-w64-aarch64-git",
            {
                "mingwarm64/bin/git.exe": minimal_pe(),
                "mingwarm64/share/doc/git-doc/readme.html": b"docs\n",
                "mingwarm64/share/licenses/git/COPYING": b"license\n",
            },
            depends=("mingw-w64-aarch64-curl",),
        )
        p4 = package(
            package_dir / "git-p4.pkg.tar.zst",
            "mingw-w64-aarch64-git-p4",
            {"mingwarm64/libexec/git-core/git-p4": b"#!/usr/bin/env python\n"},
            depends=("mingw-w64-aarch64-git", "mingw-w64-aarch64-python"),
        )
        handoff = git_dir / "git-package-handoff.json"
        handoff_hash = write_json(handoff, {
            "build": {
                "packages": [
                    {
                        "file": Path(git["path"]).name,
                        "sha256": git["sha256"],
                        "packageName": git["name"],
                    },
                    {
                        "file": Path(p4["path"]).name,
                        "sha256": p4["sha256"],
                        "packageName": p4["name"],
                    },
                ]
            }
        })
        providers = self.root / "providers"
        providers.mkdir()
        curl = package(
            providers / "curl.pkg.tar.zst",
            "mingw-w64-aarch64-curl",
            {"mingwarm64/etc/ssl/certs/ca-bundle.crt": b"certificate\n"},
        )
        python = package(
            providers / "python.pkg.tar.zst",
            "mingw-w64-aarch64-python",
            {"mingwarm64/bin/python.exe": minimal_pe()},
        )
        export = providers / "export.json"
        export_hash = write_json(export, {
            "schema": 1,
            "status": "admitted",
            "packages": [curl, python],
        })
        evidence = self.root / "self-hosting.json"
        evidence_hash = write_json(evidence, {
            "schema": 1,
            "status": "verified-native-self-hosting",
            "target": "aarch64-pc-msys",
            "evidence": [{"name": "native-build", "sha256": "1" * 64}],
        })
        contract = self.root / "contract.json"
        write_json(contract, {
            "schema": 1,
            "profile": "test-full",
            "archive_name": "test.zip",
            "self_hosting_evidence": {
                "schema": 1,
                "status": "verified-native-self-hosting",
                "target": "aarch64-pc-msys",
            },
            "expected_git_splits": [
                "mingw-w64-aarch64-git",
                "mingw-w64-aarch64-git-p4",
            ],
            "tls_alternatives": {"openssl": "mingw-w64-aarch64-curl"},
            "required_packages": ["mingw-w64-aarch64-python"],
            "required_files": [
                "mingwarm64/bin/git.exe",
                "mingwarm64/bin/python.exe",
                "mingwarm64/etc/ssl/certs/ca-bundle.crt",
                "mingwarm64/libexec/git-core/git-p4",
            ],
            "required_documentation_globs": ["mingwarm64/share/doc/git-doc/**"],
            "required_license_globs": ["mingwarm64/share/licenses/**"],
            "managed_files": [],
            "managed_components": [],
            "provider_role_payload_globs": {"network-runtime": []},
            "excluded_payload_globs": [],
            "generated_gitconfig": {
                "path": "etc/gitconfig",
                "content": (
                    "[http]\n"
                    "\tsslCAInfo = %(prefix)/mingwarm64/etc/ssl/certs/ca-bundle.crt\n"
                ),
            },
            "system_dlls": [],
            "forbidden_payload_markers": ["C:\\ap", "/c/ap"],
            "forbidden_nonrelease_markers": ["NON-FUNCTIONAL STUB"],
        })
        input_path = self.root / "input.json"
        write_json(input_path, {
            "schema": 1,
            "tls": "openssl",
            "git_handoff": {"path": str(handoff), "sha256": handoff_hash},
            "network_export": {"path": str(export), "sha256": export_hash},
            "provider_exports": [],
            "managed_admissions": [],
            "self_hosting_evidence": {
                "path": str(evidence),
                "sha256": evidence_hash,
            },
        })
        output = self.root / "release"
        manifest_path = ASSEMBLER.assemble(input_path, contract, output)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("assembled-complete", manifest["status"])
        self.assertEqual(2, manifest["git_split_count"])
        with zipfile.ZipFile(output / "test.zip") as archive:
            self.assertIn("mingwarm64/bin/git.exe", archive.namelist())
            self.assertIn("mingwarm64/bin/python.exe", archive.namelist())
            self.assertIn("etc/gitconfig", archive.namelist())
        verified = ASSEMBLER.verify_release(manifest_path)
        self.assertEqual("verified", verified["status"])
        self.assertEqual(len(manifest["payload"]), verified["payload_files"])


if __name__ == "__main__":
    unittest.main()
