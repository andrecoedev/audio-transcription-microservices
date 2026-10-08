from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from prepare_private import main


class PrivateMediaTests(unittest.TestCase):
    def check_sanitized_timeout(self, stage):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "synthetic-private-name.mp4"
            source.touch()
            output = Path(temporary) / "output.wav"
            failure = subprocess.TimeoutExpired(["synthetic-command", str(source)], 30)
            effects = [failure] if stage == "probe" else [SimpleNamespace(returncode=0, stdout="600"), failure]
            with patch("sys.argv", ["prepare_private", temporary, "--output", str(output)]), \
                 patch("prepare_private.subprocess.run", side_effect=effects):
                with self.assertRaises(SystemExit) as error:
                    main()
            self.assertNotIn(source.name, str(error.exception))
            self.assertNotIn(temporary, str(error.exception))
            self.assertIsNone(error.exception.__cause__)
            self.assertTrue(error.exception.__suppress_context__)

    def test_probe_timeout_never_discloses_private_path(self):
        self.check_sanitized_timeout("probe")

    def test_extract_timeout_never_discloses_private_path(self):
        self.check_sanitized_timeout("extract")


if __name__ == "__main__":
    unittest.main()
