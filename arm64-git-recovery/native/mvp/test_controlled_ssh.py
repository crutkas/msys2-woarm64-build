from pathlib import Path
import shlex
import tempfile
import unittest

from artifact import ArtifactError
from controlled_ssh import known_hosts_option


class SshOptionControls(unittest.TestCase):
    def test_config_value_quotes_survive_shell_argument_roundtrip(self):
        with tempfile.TemporaryDirectory() as temporary:
            for folder in ("plain", "path with spaces"):
                path = Path(temporary) / folder / "known_hosts"
                for name in ("UserKnownHostsFile", "GlobalKnownHostsFile"):
                    with self.subTest(folder=folder, name=name):
                        value = known_hosts_option(name, path)
                        command = ["ssh", "-o", value]
                        self.assertEqual(shlex.split(shlex.join(command)), command)
                        self.assertEqual(shlex.split(value), [name + "=" + path.resolve().as_posix()])
                        self.assertIn('="', value)

    def test_config_control_characters_are_rejected(self):
        for value in ('bad"path', "bad\npath", "bad\rpath", "bad\0path"):
            with self.subTest(value=value), self.assertRaises((ArtifactError, ValueError)):
                known_hosts_option("UserKnownHostsFile", value)


if __name__ == "__main__":
    unittest.main()
