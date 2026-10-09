"""Offline readiness regression tests: never require a GPU or network."""
import json
import tempfile
import unittest
from pathlib import Path

from preflight import check


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "input").mkdir()
        (self.root / "output").mkdir()
        self.records = []
        for i in range(6):
            relative = f"vae/test_{i}.safetensors"
            target = self.root / "models" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"model")
            self.records.append({"target": relative, "min_bytes": 5})
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(json.dumps({"models": self.records}))

    def ready(self):
        return check(self.manifest, self.root, "http://127.0.0.1:1", check_api=False, min_free_gb=0)

    def test_six_models_pass(self):
        self.assertTrue(self.ready())

    def test_missing_model_fails(self):
        (self.root / "models" / self.records[0]["target"]).unlink()
        self.assertFalse(self.ready())

    def test_broken_symlink_fails(self):
        target = self.root / "models" / self.records[1]["target"]
        target.unlink()
        target.symlink_to(self.root / "nonexistent_blob")
        self.assertFalse(self.ready())

    def test_too_small_model_fails(self):
        target = self.root / "models" / self.records[2]["target"]
        target.write_bytes(b"x")
        self.assertFalse(self.ready())


if __name__ == "__main__":
    unittest.main()
