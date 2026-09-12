import importlib.util
from pathlib import Path
import unittest

from sources import ContractError

spec = importlib.util.spec_from_file_location("cmake_finish", Path(__file__).with_name("finish-msys-cmake.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CmakeFinishControls(unittest.TestCase):
    def test_complete_test_set_is_required(self):
        module.validate_test_set(["a", "b"], ["b", "a"])
        for actual in ([], ["a"], ["a", "a"], ["a", "b", "extra"]):
            with self.subTest(actual=actual), self.assertRaises(ContractError):
                module.validate_test_set(["a", "b"], actual)


if __name__ == "__main__":
    unittest.main()
