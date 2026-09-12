import importlib.util
from pathlib import Path
import tempfile
import unittest

from sources import ContractError


spec = importlib.util.spec_from_file_location("native_cmake", Path(__file__).with_name("build-native-cmake.py"))
recipe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recipe)


class NativeCmakeControls(unittest.TestCase):
    def parse(self, xml):
        temp = tempfile.TemporaryDirectory(prefix="native-ctest-control-")
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "tests.xml"
        path.write_text(xml)
        return recipe.ctest_results(path)

    def test_junit_pass(self):
        self.assertEqual(self.parse('<testsuite><testcase name="real-test"/></testsuite>'), ["real-test"])

    def test_junit_empty_rejected(self):
        with self.assertRaises(ContractError):
            self.parse("<testsuite/>")

    def test_junit_failure_rejected(self):
        with self.assertRaises(ContractError):
            self.parse('<testsuite><testcase name="test"><failure/></testcase></testsuite>')

    def test_junit_notrun_rejected(self):
        with self.assertRaises(ContractError):
            self.parse('<testsuite><testcase name="test"><skipped/></testcase></testsuite>')

    def test_expat_nonempty_pass(self):
        self.assertEqual(recipe.expat_test_results("Expat version: 2.8.4\n100%: Checks: 4884, Failed: 0\n")["checks"],
                         [4884])

    def test_expat_no_checks_rejected(self):
        with self.assertRaises(ContractError):
            recipe.expat_test_results("100%: Checks: 0, Failed: 0")

    def test_expat_later_failure_not_masked(self):
        with self.assertRaises(ContractError):
            recipe.expat_test_results("100%: Checks: 99, Failed: 0\n99%: Checks: 100, Failed: 1")

    def test_expat_banner_is_not_execution(self):
        with self.assertRaises(ContractError):
            recipe.expat_test_results("Expat version: 2.8.4")


if __name__ == "__main__":
    unittest.main()
