import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from sources import ContractError, digest, load_lock

spec = importlib.util.spec_from_file_location("native_posix", Path(__file__).with_name("build-native-posix.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class NativePosixControls(unittest.TestCase):
    def record(self, package="bash"):
        return {"schema": 1, "status": "source-prepared-not-built", "package": package, "source_id": package,
                "recipe_id": module.PROFILES[package]["recipe"],
                "source_manifest_sha256": "1" * 64, "recipe_manifest_sha256": "2" * 64,
                "generators": [{"command": module.PROFILES[package].get("generator", [])}]}

    def test_exact_prepared_source_boundary(self):
        record = self.record()
        module.validate_prepared("bash", record)
        with self.assertRaises(ContractError):
            module.validate_prepared("make", record)
        del record["recipe_manifest_sha256"]
        with self.assertRaises(ContractError):
            module.validate_prepared("bash", record)

    def test_wrong_recipe_and_malformed_hashes_are_rejected(self):
        for field, value in (("recipe_id", "msys-upstream-recipes"),
                             ("source_manifest_sha256", "nonempty"),
                             ("recipe_manifest_sha256", "z" * 64),
                             ("recipe_manifest_sha256", None)):
            with self.subTest(field=field, value=value):
                record = self.record()
                record[field] = value
                with self.assertRaises(ContractError):
                    module.validate_prepared("bash", record)

    def test_required_regeneration_is_not_silently_skipped(self):
        for package in ("bash", "coreutils"):
            record = self.record(package)
            module.validate_prepared(package, record)
            record["generators"] = []
            with self.assertRaisesRegex(ContractError, "regeneration"):
                module.validate_prepared(package, record)
        record = self.record("make")
        record["generators"] = []
        module.validate_prepared("make", record)

    def test_origins_bind_both_inventory_bytes_and_locked_source(self):
        lock = Path(__file__).with_name("sources.lock.json")
        locked = {row["id"]: row for row in load_lock(lock)["sources"]}
        with tempfile.TemporaryDirectory(prefix="native-posix-origins-") as temporary:
            root = Path(temporary)
            source, recipe = root / "source.json", root / "recipe.json"
            source.write_text(json.dumps({"source": locked["bash"]}))
            recipe.write_text(json.dumps({"source": locked["msys-recipes"]}))
            record = self.record()
            record.update(source_manifest_sha256=digest(source), recipe_manifest_sha256=digest(recipe))
            module.verify_origins("bash", record, source, recipe, lock)
            source.write_text(json.dumps({"source": locked["coreutils"]}))
            with self.assertRaises(ContractError):
                module.verify_origins("bash", record, source, recipe, lock)
            record["source_manifest_sha256"] = digest(source)
            with self.assertRaises(ContractError):
                module.verify_origins("bash", record, source, recipe, lock)

    def test_output_cannot_overlap_inputs_or_replace_evidence(self):
        with tempfile.TemporaryDirectory(prefix="native-posix-output-") as temporary:
            root = Path(temporary)
            source, output = root / "source", root / "output"
            source.mkdir()
            module.validate_output(output, [source])
            for invalid in (source, source / "build", root):
                with self.subTest(output=invalid), self.assertRaises(ContractError):
                    module.validate_output(invalid, [source])
            output.with_name(output.name + ".result.json").write_text("retained failure")
            with self.assertRaises(ContractError):
                module.validate_output(output, [source])

    def test_bootstrap_omissions_remain_explicit(self):
        self.assertIn("Readline disabled", module.PROFILES["bash"]["limitations"])
        self.assertIn("GMP disabled", module.PROFILES["coreutils"]["limitations"])
        self.assertIn("Guile disabled", module.PROFILES["make"]["limitations"])


if __name__ == "__main__":
    unittest.main()
