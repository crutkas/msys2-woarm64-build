import unittest

from openssl_test_patches import adapt_test, replace_once
from sources import ContractError


class OpenSslTestPatchControls(unittest.TestCase):
    def test_ca_override_preserves_packaged_default(self):
        patched = adapt_test("apps/CA.pl", 'my $CATOP = "/usr/ssl";\n')
        self.assertIn('$ENV{"OPENSSL_CA_DIR"} // "/usr/ssl"', patched)

    def test_context_change_or_duplicate_is_not_silently_accepted(self):
        for text in ("unrelated", "context context"):
            with self.assertRaises(ContractError):
                replace_once(text, "context", "changed")

    def test_unknown_test_adaptation_is_rejected(self):
        with self.assertRaises(ContractError):
            adapt_test("test/unknown.t", "anything")


if __name__ == "__main__":
    unittest.main()
