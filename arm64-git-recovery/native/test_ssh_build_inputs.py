import copy
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest import mock
import uuid

from sources import ContractError, digest, inventory, load_lock
from ssh_build_inputs import (
    HERE, adopt_source, contract, prerequisite_closure, validate_openssh_configuration, validate_preparation,
)


class SshInputsTests(unittest.TestCase):
    def setUp(self):
        self.rules = contract()
        self.lock = load_lock(HERE / "sources.lock.json")

    def record(self, package="openssh"):
        profile = self.rules["profiles"][package]
        return {
            "source": next(row for row in self.lock["sources"] if row["id"] == package),
            "scope": "prepared MSYS-target sources, not built",
            "dependency_abi": "MSYS runtime; MinGW/UCRT libraries are not substitutes",
            "recipe_sha256": profile["recipe_sha256"],
            "recipe_manifest_sha256": self.rules["recipe_collection"]["prepared_inventory_sha256"],
            "dependencies": list(profile["dependencies"]),
            "libtool_dependency": {"manifest_sha256": "a" * 64},
            "steps": [
                *[{"patch_sha256": p["sha256"], "upstream_patch_sha256": p["upstream_sha256"], "exit": 0}
                  for p in profile["patches"]],
                {"command": profile["generation"], "exit": 0},
            ],
            "files": {"configure": {"sha256": "a" * 64, "size": 1}},
        }

    def config(self):
        return "\n".join("#define " + name + (" /**/" if name.startswith("ENABLE_") else " 1")
                         for name in self.rules["profiles"]["openssh"]["required_defines"])

    @staticmethod
    def makefile():
        return ("LIBEDIT=-ledit -lncursesw\nLIBFIDO2=-lfido2 -lcbor\n"
                "K5LIBS=-lkrb5 -lasn1 -lroken\nGSSLIBS=-lgssapi -lkrb5\n"
                "LIBS=-lcrypto -lz\nSSHDLIBS=-lcrypt\n")

    def test_all_prepared_profiles(self):
        for package in self.rules["profiles"]:
            with self.subTest(package=package):
                validate_preparation(package, self.record(package), self.lock)

    def test_reject_preparation_drift(self):
        cases = [
            ("source", {**self.record()["source"], "version": "10.4p1"}),
            ("dependencies", ["openssl"]),
            ("recipe_sha256", "0" * 64),
            ("recipe_manifest_sha256", "0" * 64),
            ("dependency_abi", "MinGW"),
            ("scope", "built"),
            ("steps", []),
            ("files", {"configure": {"symlink": "elsewhere"}}),
        ]
        for key, value in cases:
            with self.subTest(key=key):
                record = self.record()
                record[key] = value
                with self.assertRaises(ContractError):
                    validate_preparation("openssh", record, self.lock)

    def test_reject_failed_generation_and_patch_reordering(self):
        for mutation in ("failed", "missing-generation", "reordered", "missing-patch"):
            with self.subTest(mutation=mutation):
                record = self.record()
                if mutation == "failed":
                    record["steps"][-1]["exit"] = 1
                elif mutation == "missing-generation":
                    record["steps"][-1]["command"] = ["true"]
                elif mutation == "reordered":
                    record["steps"][0], record["steps"][1] = record["steps"][1], record["steps"][0]
                else:
                    record["steps"].pop(0)
                with self.assertRaises(ContractError):
                    validate_preparation("openssh", record, self.lock)

    def test_shared_libraries_require_generator(self):
        record = self.record("libedit")
        record["libtool_dependency"] = None
        with self.assertRaises(ContractError):
            validate_preparation("libedit", record, self.lock)

    def test_recipe_lock_must_match(self):
        lock = copy.deepcopy(self.lock)
        next(row for row in lock["sources"] if row["id"] == "msys-upstream-recipes")["version"] = "other"
        with self.assertRaises(ContractError):
            validate_preparation("openssh", self.record(), lock)

    def test_full_prerequisite_closure_and_ancillary_gates(self):
        result = prerequisite_closure(self.lock)
        order = result["topological_build_order"]
        for name, dependencies in result["source_dependencies"].items():
            for dependency in dependencies:
                self.assertLess(order.index(dependency), order.index(name))
        self.assertEqual(result["readline_package_version"], "8.3.003")
        self.assertEqual([row["id"] for row in result["parent_owned_test_source_pins"]], ["cmocka"])
        self.assertEqual(result["execution_boundary"]["required_environment"]["WOARM64_NATIVE_ARG_CONVERSION"],
                         "none")
        self.assertEqual(result["execution_boundary"]["jobs"], 1)
        self.assertEqual(result["execution_boundary"]["nested_jobs"], 1)
        ancillary = result["ancillary_sources"]
        self.assertEqual([row["status"] for row in ancillary[:3]], ["locked"] * 3)
        self.assertEqual(result["tcl_recipe_binding"]["reference_recipe_version"], "8.6.12")
        self.assertEqual(result["tcl_recipe_binding"]["version"], "8.6.12")
        self.assertEqual(result["tcl_recipe_binding"]["source_id"], "tcl-msys")
        self.assertEqual(result["tcl_recipe_binding"]["mingw_gui_version"], "8.6.18")
        self.assertIn("tcl-msys", order)
        self.assertNotIn("tcl", order)

    def test_ancillary_gate_rejects_unlocked_or_wrong_patch_bytes(self):
        lock = copy.deepcopy(self.lock)
        patch = next(row for row in lock["sources"] if row["id"] == "readline83-001")
        patch["sha256"] = "0" * 64
        result = prerequisite_closure(lock)
        self.assertEqual(result["ancillary_sources"][0]["status"], "missing-from-canonical-lock")

    def test_documentation_pin_gate_without_shared_lock_mutation(self):
        lock = copy.deepcopy(self.lock)
        document = self.rules["ancillary_source_requirements"][-1]
        lock["sources"] = [row for row in lock["sources"] if row["file"] != document["file"]]
        self.assertEqual(prerequisite_closure(lock)["ancillary_sources"][-1]["status"],
                         "missing-from-canonical-lock")
        lock["sources"].append({**document, "id": "sqlite-doc-msys"})
        self.assertEqual(prerequisite_closure(lock)["ancillary_sources"][-1]["status"], "locked")

    def test_missing_transitive_source_fails(self):
        lock = copy.deepcopy(self.lock)
        lock["sources"] = [row for row in lock["sources"] if row["id"] != "tcl-msys"]
        with self.assertRaises(ContractError):
            prerequisite_closure(lock)

    def test_full_feature_configuration(self):
        result = validate_openssh_configuration(self.config(), self.makefile())
        self.assertIn("WITH_ZLIB", result["required_defines"])
        self.assertIn("not native binary", result["scope"])

    def test_each_feature_is_mandatory(self):
        for name in self.rules["profiles"]["openssh"]["required_defines"]:
            for value in (f"/* #undef {name} */", f"#define {name} 0"):
                with self.subTest(feature=name, value=value):
                    lines = [value if line.split()[1] == name else line for line in self.config().splitlines()]
                    with self.assertRaises(ContractError):
                        validate_openssh_configuration("\n".join(lines), self.makefile())

    def test_each_link_input_is_mandatory(self):
        for flag in ("-ledit", "-lfido2", "-lkrb5", "-lgssapi", "-lcrypto", "-lz", "-lcrypt"):
            with self.subTest(flag=flag):
                with self.assertRaises(ContractError):
                    validate_openssh_configuration(self.config(), self.makefile().replace(flag + " ", "")
                                                   .replace(flag + "\n", "\n"))

    def test_folded_makefile_line(self):
        validate_openssh_configuration(self.config(), self.makefile().replace("-lcrypto -lz", "-lcrypto \\\n -lz"))

    def test_comments_and_later_undef_cannot_supply_features(self):
        with self.assertRaises(ContractError):
            validate_openssh_configuration(self.config() + "\n#undef ENABLE_SK", self.makefile())
        with self.assertRaises(ContractError):
            validate_openssh_configuration("/*\n" + self.config() + "\n*/", self.makefile())
        with self.assertRaises(ContractError):
            validate_openssh_configuration(self.config().replace("#define ENABLE_SK /**/",
                                                                "#define ENABLE_SK 0 /* disabled */"),
                                           self.makefile())

    def test_private_adoption_integrity_and_existing_output(self):
        root = Path(os.environ.get("SSH_TEST_ROOT", ".ssh-test-work")) / str(uuid.uuid4())
        root.mkdir(parents=True)
        try:
            source = root / "input"
            source.mkdir()
            (source / "configure").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            manifest = root / "input.json"
            record = self.record()
            record["files"] = inventory(source)
            manifest.write_text(json.dumps(record), encoding="utf-8")
            seal = digest(manifest)
            args = ("openssh", source, manifest, seal, root / "output", HERE / "sources.lock.json")
            report = adopt_source(*args)
            self.assertEqual(report["status"], "sealed-ssh-source-private-copy")
            self.assertEqual(report["target_processes_launched"], 0)
            self.assertEqual(inventory(source), inventory(root / "output" / "source"))
            self.assertEqual(digest(root / "output" / "source.prepare.json"), seal)
            with self.assertRaises(ContractError):
                adopt_source(*args)
            with self.assertRaises(ContractError):
                adopt_source("openssh", source, manifest, "0" * 64, root / "other", HERE / "sources.lock.json")
            self.assertFalse((root / "other").exists())
            with self.assertRaises(ContractError):
                adopt_source("openssh", source, manifest, seal, source / "nested", HERE / "sources.lock.json")
            (source / "configure").write_text("changed", encoding="utf-8")
            with self.assertRaises(ContractError):
                adopt_source("openssh", source, manifest, seal, root / "changed", HERE / "sources.lock.json")
            self.assertFalse((root / "changed").exists())
        finally:
            shutil.rmtree(root)

    def test_maintained_patch_drift_fails(self):
        with mock.patch("ssh_build_inputs.digest", return_value="0" * 64):
            with self.assertRaises(ContractError):
                validate_preparation("openssh", self.record(), self.lock)


if __name__ == "__main__":
    unittest.main()
