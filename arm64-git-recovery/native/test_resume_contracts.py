import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from sources import ContractError, digest


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


assembly = load("same_root_assembly", "assemble-native-root.py")
compiler = load("compiler_copy", "copy-toolchain-input.py")
tk_relink = load("tk_relink", "relink-tk-crt.py")
tk_overlay = load("tk_overlay", "stage-tcltk.py")


class AssemblyResumeControls(unittest.TestCase):
    def files(self):
        return {
            "git-stage/usr/bin/msys-2.0.dll": {"sha256": "runtime", "size": 7},
            "posix-root/payload/usr/bin/msys-2.0.dll": {"sha256": "runtime", "size": 7},
            "git-stage/clangarm64/bin/git.exe": {"sha256": "git", "size": 3},
            "git-build-dependencies/bin/libintl-8.dll": {"sha256": "intl", "size": 4},
            "git-build-dependencies/share/licenses/intl/COPYING": {"sha256": "license", "size": 7},
        }

    def test_same_root_and_dependency_licenses(self):
        result = assembly.plan_files(self.files())
        self.assertEqual(len(result["usr/bin/msys-2.0.dll"]["sources"]), 2)
        self.assertIn("clangarm64/bin/libintl-8.dll", result)
        self.assertIn("clangarm64/share/licenses/intl/COPYING", result)

    def test_mixed_runtime_rejected(self):
        files = self.files()
        files["posix-root/payload/usr/bin/msys-2.0.dll"] = {"sha256": "other", "size": 5}
        with self.assertRaises(ContractError):
            assembly.plan_files(files)

    def test_case_alias_collision_rejected(self):
        files = self.files()
        files["git-stage/clangarm64/bin/LIBINTL-8.dll"] = {"sha256": "intl", "size": 4}
        with self.assertRaises(ContractError):
            assembly.plan_files(files)

    def test_distinct_dll_not_overwritten(self):
        files = self.files()
        files["git-stage/clangarm64/bin/libintl-8.dll"] = {"sha256": "wrong", "size": 5}
        with self.assertRaises(ContractError):
            assembly.plan_files(files)

    def test_external_relative_path_rejected(self):
        with self.assertRaises(ContractError):
            assembly.plan_files({"git-stage/../secret": {"sha256": "bad", "size": 3}})


class CompilerCopyControls(unittest.TestCase):
    def test_compiler_delta_cannot_replace_retained_runtime_or_headers(self):
        base = {"bin/cc1.exe": "old", "include/setjmp.h": "header", "bin/msys-2.0.dll": "runtime"}
        successor = {**base, "bin/cc1.exe": "new", "share/proof.json": "proof"}
        compiler.verify_cohort_delta(base, successor, {"bin/cc1.exe"}, {"share/proof.json"})
        for changed in ({**successor, "include/setjmp.h": "wrong"},
                        {name: sha for name, sha in successor.items() if name != "bin/msys-2.0.dll"},
                        {**successor, "bin/extra.exe": "unqualified"}):
            with self.assertRaises(ContractError):
                compiler.verify_cohort_delta(base, changed, {"bin/cc1.exe"}, {"share/proof.json"})

    def test_ucontext_qualification_rejects_bad_stack_and_changed_proof(self):
        with tempfile.TemporaryDirectory(prefix="ucontext-copy-control-") as directory:
            root = Path(directory)
            path = root / "proof"
            path.write_bytes(b"fixture")
            proof = {"Path": "proof", "SHA256": digest(path)}
            record = {"EntryStackAlignment": 16, "ArgumentCounts": [0, 1, 8, 9, 12],
                      "CoroutineYields": 32, "BoundedChildCleanup": True,
                      "InvalidContextReturnsEINVAL": True, "Header": proof,
                      "Consumer": proof, "RuntimeReceipt": proof}
            compiler.verify_ucontext_qualification(root, record)
            record["EntryStackAlignment"] = 8
            with self.assertRaises(ContractError):
                compiler.verify_ucontext_qualification(root, record)
            record["EntryStackAlignment"] = 16
            path.write_bytes(b"changed")
            with self.assertRaises(ContractError):
                compiler.verify_ucontext_qualification(root, record)

    def test_jump_qualification_checks_layout_and_bound_evidence(self):
        with tempfile.TemporaryDirectory(prefix="jmp-copy-control-") as directory:
            root = Path(directory)
            proof = root / "proof"
            proof.write_bytes(b"fixture")
            item = {"Path": "proof", "SHA256": digest(proof)}
            qualification = {"JmpBufBytes": 256, "SigjmpBufBytes": 272, "SaveMaskOffset": 256,
                             "SignalMaskOffset": 264, "ExistingConsumersRecompiled": False,
                             "Header": item, "Consumer": item, "RuntimeReceipt": item}
            pairing = {"SysrootManifest": item, "DllManifest": item}
            compiler.verify_jump_qualification(root, qualification, pairing)
            qualification["JmpBufBytes"] = 176
            with self.assertRaises(ContractError):
                compiler.verify_jump_qualification(root, qualification, pairing)
            qualification["JmpBufBytes"] = 256
            proof.write_bytes(b"changed")
            with self.assertRaises(ContractError):
                compiler.verify_jump_qualification(root, qualification, pairing)

    def test_immutable_legacy_input(self):
        _, status, files = compiler.published_input({
            "Immutable": True, "Prefix": "C:\\fixture", "Status": "c-qualified",
            "Files": [{"Path": "bin\\gcc.exe", "SHA256": "fixture"}]})
        self.assertEqual(status, "c-qualified")
        self.assertEqual(files, {"bin/gcc.exe": "fixture"})

    def test_case_duplicate_input_rejected(self):
        with self.assertRaises(ContractError):
            compiler.published_input({
                "Immutable": True, "Prefix": "C:\\fixture", "Status": "c-qualified",
                "Files": [{"Path": "bin\\gcc.exe", "SHA256": "fixture"},
                          {"Path": "bin\\GCC.exe", "SHA256": "fixture"}]})

    def test_versioned_producer_inventory(self):
        with tempfile.TemporaryDirectory(prefix="compiler-receipt-control-") as directory:
            root = Path(directory)
            proof = root / "proof.json"
            proof.write_text("{}")
            inventory = root / "inventory.json"
            inventory.write_text(json.dumps([{"relativePath": "bin\\gcc.exe", "sha256": "fixture"}]))
            handoff = {"schema": 1, "binaryCohort": {
                "windowsPrefix": str(root), "fileCount": 1, "inventory": str(inventory),
                "inventorySha256": digest(inventory)}, "targetedRegressions": {
                "passed": True, "result": str(proof), "resultSha256": digest(proof)}}
            self.assertEqual(compiler.published_input(handoff)[2], {"bin/gcc.exe": "fixture"})
            proof.write_text("changed")
            with self.assertRaises(ContractError):
                compiler.published_input(handoff)

    def test_crt_revision_inventory_and_proofs(self):
        with tempfile.TemporaryDirectory(prefix="crt-receipt-control-") as directory:
            root = Path(directory)
            proof = root / "proof.json"
            proof.write_text("{}")
            inventory = root / "inventory.json"
            inventory.write_text(json.dumps({"prefix": str(root), "fileCount": 1,
                                             "files": [{"relativePath": "bin/gcc.exe", "sha256": "fixture"}]}))
            handoff = {"schema": 1, "status": "crt-cexp-recursion-fix-validated",
                       "binary": {"successorPrefix": str(root), "fileCount": 1, "inventory": str(inventory),
                                  "inventorySha256": digest(inventory)},
                       "validation": {name: {"path": str(proof), "sha256": digest(proof)} for name in
                                      ("patchedCohort", "patchedDoubleProbe", "patchedFamilyProbe")}}
            self.assertEqual(compiler.published_input(handoff)[2], {"bin/gcc.exe": "fixture"})
            handoff["binary"]["fileCount"] = 2
            with self.assertRaises(ContractError):
                compiler.published_input(handoff)
            handoff["binary"]["fileCount"] = 1
            proof.write_text("changed")
            with self.assertRaises(ContractError):
                compiler.published_input(handoff)


class TkRecoveryControls(unittest.TestCase):
    command = "gcc -shared -O2 -o tk86.dll tkWindow.o -Wl,--out-implib,libtk86.dll.a -ltcl86"

    def test_redirects_outputs_without_changing_objects_or_flags(self):
        old, new = tk_relink.link_command([self.command], Path("new/gcc.exe"), Path("fresh"))
        self.assertEqual(new[2], "-O2")
        self.assertIn("tkWindow.o", new)
        self.assertEqual(new[-1], "-ltcl86")
        self.assertEqual(old[old.index("-o") + 1], "tk86.dll")
        self.assertEqual(Path(new[new.index("-o") + 1]), Path("fresh/bin/tk86.dll"))
        self.assertIn("-Wl,--out-implib,fresh/lib/libtk86.dll.a", new)

    def test_duplicate_and_missing_link_commands_are_rejected(self):
        for lines in ([], [self.command, self.command],
                      [self.command.replace(" -Wl,--out-implib,libtk86.dll.a", "")],
                      [self.command + " -Wl,--output-def,old.def"], [self.command + " \\"]):
            with self.subTest(lines=lines), self.assertRaises(ContractError):
                tk_relink.link_command(lines, Path("gcc.exe"), Path("fresh"))

    def test_overlay_rejects_distinct_and_case_collisions(self):
        base = {"usr/bin/wish.exe": {"sha256": "original", "size": 1}}
        for component in ({"bin/wish.exe": {"sha256": "other", "size": 1}},
                          {"bin/WISH.exe": {"sha256": "original", "size": 1}}):
            with self.subTest(component=component), self.assertRaises(ContractError):
                tk_overlay.overlay_plan(base, component)
        self.assertEqual(tk_overlay.overlay_plan(base, {"bin/wish.exe": base["usr/bin/wish.exe"]}), base)


if __name__ == "__main__":
    unittest.main()
