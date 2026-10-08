import hashlib
from pathlib import Path
import tempfile
import unittest

from provenance import collect, revision


class ProvenanceTests(unittest.TestCase):
    def test_hashes_include_config_but_never_unrelated_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            models = Path(temporary)
            folder = models / "faster-tiny"
            folder.mkdir()
            (folder / "model.bin").write_bytes(b"synthetic weights")
            (folder / "config.json").write_text("{}")
            (folder / ".env").write_text("synthetic ignored content")
            result = collect(models)["faster_models"][0]
            self.assertEqual({item["artifact"] for item in result["artifacts"]}, {"model.bin", "config.json"})
            weight = next(item for item in result["artifacts"] if item["artifact"] == "model.bin")
            self.assertEqual(weight["sha256"], hashlib.sha256(b"synthetic weights").hexdigest())
            self.assertIsNone(result["revision"])

    def test_nonrevision_content_is_never_exported(self):
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / "metadata"
            file.write_text("synthetic-not-a-revision")
            with self.assertRaises(ValueError):
                revision(file)


if __name__ == "__main__":
    unittest.main()
