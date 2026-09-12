"""Lightweight contract controls. Synthetic MZ files are NOT native PE proof."""

import copy
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

import packages
import sources
from sources import ContractError, digest


HERE = Path(__file__).resolve().parent


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="arm64-contract-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.lock = HERE / "sources.lock.json"
        self.payload = self.root / "payload"
        self.payload.mkdir()
        evidence = self.root / "build-evidence.json"
        evidence.write_text('{"scope": "synthetic-fixture-not-a-real-build"}\n')
        self.meta = {
            "schema": 1, "id": "git", "version": "test-only",
            "target": "aarch64-w64-mingw32", "build_host": "linux-aarch64-cross",
            "classification": "functional", "source_ids": ["git-full"],
            "source_lock_sha256": digest(self.lock), "depends": {},
            "required_files": ["bin/git.exe"], "license_files": ["LICENSE"],
            "build_evidence_sha256": digest(evidence), "build_evidence_path": str(evidence)
        }
        self.put("bin/git.exe", b"MZ-synthetic-content-control-NOT-A-PE")
        self.put("bin/git-add.exe", b"MZ-synthetic-content-control-NOT-A-PE")
        self.put("bin/git-remote-https.exe", b"MZ-transport-control-NOT-A-PE")
        self.put("builtins.txt", b"git-add.exe\n")
        self.put("LICENSE", b"test fixture, no third party payload\n")
        self.metadata = self.root / "metadata.json"
        self.manifest = self.root / "package.json"
        self.contract = {
            "schema": 1, "profile": "synthetic-controls-only",
            "required_packages": ["git"],
            "required_files": ["bin/git.exe", "bin/git-remote-https.exe", "builtins.txt"],
            "builtin_list": "builtins.txt", "git_binary": "bin/git.exe",
            "builtin_directories": ["bin"],
            "preserve_builtin_names": ["git-remote-https.exe"]
        }

    def put(self, rel, data):
        path = self.payload / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def snapshot(self):
        self.metadata.write_text(json.dumps(self.meta), encoding="utf-8")
        packages.snapshot(self.payload, self.metadata, self.manifest, self.lock)

    def plan(self):
        return {"schema": 1, "packages": [
            {"root": str(self.payload), "manifest": str(self.manifest)}]}

    def merge(self):
        return packages.merge_packages(self.plan(), self.contract, self.lock)

    def test_valid_snapshot(self):
        self.snapshot()
        result = packages.verify_package(self.payload, self.manifest, self.lock)
        self.assertEqual(len(result["files"]), 5)

    def test_mutation_rejected(self):
        self.snapshot()
        self.put("bin/git.exe", b"changed")
        with self.assertRaisesRegex(ContractError, "inventory differs"):
            self.merge()

    def test_extra_file_rejected(self):
        self.snapshot()
        self.put("extra.txt", b"unlisted")
        with self.assertRaisesRegex(ContractError, "inventory differs"):
            self.merge()

    def test_missing_file_rejected(self):
        self.snapshot()
        (self.payload / "LICENSE").unlink()
        with self.assertRaisesRegex(ContractError, "inventory differs"):
            self.merge()

    def test_no_pin_rejected(self):
        self.meta["source_lock_sha256"] = ""
        with self.assertRaisesRegex(ContractError, "source lock identity"):
            self.snapshot()

    def test_unknown_source_rejected(self):
        self.meta["source_ids"] = ["imaginary"]
        with self.assertRaisesRegex(ContractError, "source_ids"):
            self.snapshot()

    def test_no_build_evidence_rejected(self):
        del self.meta["build_evidence_sha256"]
        with self.assertRaisesRegex(ContractError, "build evidence"):
            self.snapshot()

    def test_bootstrap_rejected(self):
        self.meta["classification"] = "bootstrap"
        with self.assertRaisesRegex(ContractError, "Bootstrap"):
            self.snapshot()

    def test_pe_mislabeled_data_rejected(self):
        self.meta["target"] = "data"
        with self.assertRaisesRegex(ContractError, "mislabeled as data"):
            self.snapshot()

    def test_known_stub_bytes_rejected(self):
        self.put("bin/git.exe", b"MZ NON-FUNCTIONAL STUB")
        with self.assertRaisesRegex(ContractError, "placeholder"):
            self.snapshot()

    def test_hidden_pe_rejected(self):
        self.put("share/hidden.dat", b"MZ-hidden-code-control")
        with self.assertRaisesRegex(ContractError, "unrecognized extension"):
            self.snapshot()

    def test_explicit_extensionless_loadable_remains_a_pe_candidate(self):
        self.put("usr/lib/bash/print", b"MZ-loadable-content-control-NOT-A-PE")
        self.meta["additional_pe_files"] = ["usr/lib/bash/print"]
        self.snapshot()
        saved = packages.verify_package(self.payload, self.manifest, self.lock)
        self.assertTrue(saved["files"]["usr/lib/bash/print"]["pe_candidate"])

    def test_missing_or_non_pe_loadable_declaration_rejected(self):
        self.meta["additional_pe_files"] = ["usr/lib/bash/print"]
        with self.assertRaisesRegex(ContractError, "Declared PE payload is missing"):
            self.snapshot()
        self.put("usr/lib/bash/print", b"not executable content")
        with self.assertRaisesRegex(ContractError, "MZ header"):
            self.snapshot()

    def test_duplicate_loadable_declaration_rejected(self):
        self.meta["additional_pe_files"] = ["usr/lib/bash/print", "usr/lib/bash/PRINT"]
        with self.assertRaisesRegex(ContractError, "Duplicate declared PE"):
            self.snapshot()

    def test_assembly_retains_required_empty_runtime_directories(self):
        self.put("usr/lib/bash/print", b"MZ-loadable-content-control-NOT-A-PE")
        self.meta["additional_pe_files"] = ["usr/lib/bash/print"]
        self.snapshot()
        self.contract["required_directories"] = ["tmp", "var/tmp"]
        plan, contract = self.root / "plan.json", self.root / "contract.json"
        plan.write_text(json.dumps(self.plan()))
        contract.write_text(json.dumps(self.contract))
        output = self.root / "assembled"
        report = packages.assemble(plan, contract, self.lock, output)
        self.assertTrue((output / "tmp").is_dir())
        self.assertTrue((output / "var/tmp").is_dir())
        assembled = json.loads(report.read_text())
        self.assertEqual(assembled["additional_pe_files"], ["usr/lib/bash/print"])
        self.assertTrue(assembled["files"]["usr/lib/bash/print"]["pe_candidate"])

    def test_required_directory_cannot_shadow_a_file(self):
        self.snapshot()
        self.contract["required_directories"] = ["LICENSE/child"]
        plan, contract = self.root / "plan.json", self.root / "contract.json"
        plan.write_text(json.dumps(self.plan()))
        contract.write_text(json.dumps(self.contract))
        with self.assertRaisesRegex(ContractError, "directory collides"):
            packages.assemble(plan, contract, self.lock, self.root / "assembled")

    def test_changed_build_evidence_rejected(self):
        self.snapshot()
        Path(self.meta["build_evidence_path"]).write_text("changed")
        with self.assertRaisesRegex(ContractError, "evidence is missing or changed"):
            self.merge()

    def test_stub_marker_rejected(self):
        self.put("share/pipeline-stubs/runtime.stub", b"not a runtime")
        with self.assertRaisesRegex(ContractError, "marker"):
            self.snapshot()

    def test_placeholder_license_rejected(self):
        self.put("LICENSE", b"Placeholder license for git")
        with self.assertRaisesRegex(ContractError, "placeholder"):
            self.snapshot()

    def test_empty_required_rejected(self):
        self.put("bin/git.exe", b"")
        with self.assertRaisesRegex(ContractError, "Missing/empty"):
            self.snapshot()

    def test_unknown_target_rejected(self):
        self.meta["target"] = "x86_64-w64-mingw32"
        with self.assertRaisesRegex(ContractError, "supported target"):
            self.snapshot()

    def test_empty_plan_rejected(self):
        with self.assertRaisesRegex(ContractError, "nonempty"):
            packages.merge_packages({"schema": 1, "packages": []}, self.contract, self.lock)

    def test_missing_required_package_rejected(self):
        self.snapshot()
        self.contract["required_packages"].append("bash")
        with self.assertRaisesRegex(ContractError, "Missing required packages"):
            self.merge()

    def test_dependency_missing_rejected(self):
        self.meta["depends"] = {"runtime": "exact-version"}
        self.snapshot()
        with self.assertRaisesRegex(ContractError, "requires runtime"):
            self.merge()

    def test_self_dependency_rejected(self):
        self.meta["depends"] = {"git": "test-only"}
        with self.assertRaisesRegex(ContractError, "itself"):
            self.snapshot()

    def test_duplicate_package_rejected(self):
        self.snapshot()
        plan = self.plan()
        plan["packages"] *= 2
        with self.assertRaisesRegex(ContractError, "Duplicate package"):
            packages.merge_packages(plan, self.contract, self.lock)

    def second_package(self, version="1", depends=None, payload=None):
        root = self.root / "second"
        root.mkdir()
        (root / "LICENSE-SECOND").write_text("fixture-license")
        for rel, data in (payload or {}).items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        meta = {**self.meta, "id": "second", "version": version, "target": "data",
                "build_host": "data", "depends": depends or {},
                "required_files": ["LICENSE-SECOND"], "license_files": ["LICENSE-SECOND"]}
        path = self.root / "second-meta.json"
        path.write_text(json.dumps(meta))
        manifest = self.root / "second-manifest.json"
        packages.snapshot(root, path, manifest, self.lock)
        plan = self.plan()
        plan["packages"].append({"root": str(root), "manifest": str(manifest)})
        return plan

    def test_dependency_version_rejected(self):
        self.meta["depends"] = {"second": "2"}
        self.snapshot()
        with self.assertRaisesRegex(ContractError, "requires second=2"):
            packages.merge_packages(self.second_package(), self.contract, self.lock)

    def test_cycle_rejected(self):
        self.meta["depends"] = {"second": "1"}
        self.snapshot()
        plan = self.second_package(depends={"git": "test-only"})
        with self.assertRaisesRegex(ContractError, "cycle"):
            packages.merge_packages(plan, self.contract, self.lock)

    def test_conflicting_file_rejected(self):
        self.snapshot()
        plan = self.second_package(payload={"LICENSE": b"conflicting license"})
        with self.assertRaisesRegex(ContractError, "Conflicting"):
            packages.merge_packages(plan, self.contract, self.lock)

    def test_identical_shared_file_has_both_owners(self):
        self.snapshot()
        plan = self.second_package(payload={"LICENSE": (self.payload / "LICENSE").read_bytes()})
        _, files = packages.merge_packages(plan, self.contract, self.lock)
        self.assertEqual(files["LICENSE"]["owners"], ["git", "second"])

    def test_case_collision_across_packages_rejected(self):
        self.snapshot()
        plan = self.second_package(payload={"license": b"case collision"})
        with self.assertRaisesRegex(ContractError, "Case-insensitive"):
            packages.merge_packages(plan, self.contract, self.lock)

    def test_missing_transport_rejected(self):
        (self.payload / "bin/git-remote-https.exe").unlink()
        self.snapshot()
        with self.assertRaisesRegex(ContractError, "distribution file"):
            self.merge()

    def test_trim_only_byte_identical_builtin(self):
        self.snapshot()
        _, files = self.merge()
        trim = packages.trim_builtins(files, self.contract)
        self.assertEqual(trim["removed"], ["bin/git-add.exe"])
        self.assertIn("bin/git-remote-https.exe", files)

    def test_wrong_builtin_bytes_rejected(self):
        self.put("bin/git-add.exe", b"MZ different real helper")
        self.snapshot()
        _, files = self.merge()
        with self.assertRaisesRegex(ContractError, "not byte-identical"):
            packages.trim_builtins(files, self.contract)

    def test_empty_builtin_list_rejected(self):
        self.put("builtins.txt", b"\n")
        self.snapshot()
        _, files = self.merge()
        with self.assertRaisesRegex(ContractError, "builtin"):
            packages.trim_builtins(files, self.contract)

    def test_duplicate_builtin_rejected(self):
        self.put("builtins.txt", b"git-add.exe\ngit-add.exe\n")
        self.snapshot()
        _, files = self.merge()
        with self.assertRaisesRegex(ContractError, "duplicate"):
            packages.trim_builtins(files, self.contract)

    def test_builtin_traversal_rejected(self):
        self.put("builtins.txt", b"../../git-add.exe\n")
        self.snapshot()
        _, files = self.merge()
        with self.assertRaisesRegex(ContractError, "Invalid builtin"):
            packages.trim_builtins(files, self.contract)

    def test_already_trimmed_is_explicit(self):
        (self.payload / "bin/git-add.exe").unlink()
        self.snapshot()
        _, files = self.merge()
        trim = packages.trim_builtins(files, self.contract)
        self.assertEqual(trim["removed"], [])
        self.assertEqual(trim["already_absent"], ["bin/git-add.exe"])

    def test_assembly_is_not_acceptance(self):
        self.snapshot()
        plan_path, contract_path = self.root / "plan.json", self.root / "contract.json"
        plan_path.write_text(json.dumps(self.plan()))
        contract_path.write_text(json.dumps(self.contract))
        output = self.root / "assembled"
        report = packages.assemble(plan_path, contract_path, self.lock, output)
        data = packages.read_json(report)
        self.assertEqual(data["status"], "assembled-unverified")
        self.assertIn("raw-native-ARM64-PE", data["pending_gates"])
        self.assertFalse((output / "bin/git-add.exe").exists())
        with self.assertRaisesRegex(ContractError, "new output"):
            packages.assemble(plan_path, contract_path, self.lock, output)

    def test_unsafe_relative_paths(self):
        for path in ("../a", "/a", "C:/a", "a\\b", "a//b", "a/./b", "a/../b"):
            with self.subTest(path=path), self.assertRaises(ContractError):
                sources.relative_path(path)

    def test_manifest_cannot_enter_payload(self):
        self.metadata.write_text(json.dumps(self.meta))
        with self.assertRaisesRegex(ContractError, "outside"):
            packages.snapshot(self.payload, self.metadata, self.payload / "manifest.json", self.lock)

    def archive(self, names):
        cache = self.root / "cache"
        cache.mkdir()
        archive = cache / "fixture.tar"
        with tarfile.open(archive, "w") as tar:
            for name in names:
                member = tarfile.TarInfo(name)
                member.size = 4
                tar.addfile(member, io.BytesIO(b"data"))
        return cache, {"id": "source", "version": "1", "file": archive.name,
                       "prefix": "upstream", "sha256": digest(archive),
                       "url": "https://example.invalid/never-downloaded"}

    def test_source_inventory_set_equality(self):
        cache, item = self.archive(["upstream/one", "upstream/two"])
        output = self.root / "sources"
        self.assertEqual(sources.recover(item, cache, output)["files"], 2)
        self.assertEqual(sources.recover(item, cache, output)["files"], 2)
        (output / "source/extra").write_text("unlisted")
        with self.assertRaisesRegex(ContractError, "inventory differs"):
            sources.recover(item, cache, output)

    def test_source_hash_mismatch(self):
        cache, item = self.archive(["upstream/one"])
        item["sha256"] = "0" * 64
        with self.assertRaisesRegex(ContractError, "SHA-256 mismatch"):
            sources.recover(item, cache)

    def test_archive_traversal(self):
        cache, item = self.archive(["upstream/../escaped"])
        with self.assertRaisesRegex(ContractError, "Unsafe"):
            sources.recover(item, cache, self.root / "sources")
        self.assertFalse((self.root / "sources/escaped").exists())

    def test_archive_duplicate(self):
        cache, item = self.archive(["upstream/file", "upstream/file"])
        with self.assertRaisesRegex(ContractError, "Duplicate archive"):
            sources.recover(item, cache, self.root / "sources")

    def test_archive_wrong_prefix(self):
        cache, item = self.archive(["different/file"])
        with self.assertRaisesRegex(ContractError, "prefix"):
            sources.recover(item, cache, self.root / "sources")

    def test_duplicate_source_lock(self):
        lock = sources.load_lock(self.lock)
        lock["sources"].append(copy.deepcopy(lock["sources"][0]))
        path = self.root / "bad-lock.json"
        path.write_text(json.dumps(lock))
        with self.assertRaisesRegex(ContractError, "Duplicate source"):
            sources.load_lock(path)


if __name__ == "__main__":
    unittest.main()
