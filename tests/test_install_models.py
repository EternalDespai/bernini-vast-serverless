"""Offline regression tests for manifest-driven model installation."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from install_models import install, validate_model, verify_sha256


class ModelInstallTests(unittest.TestCase):
    def record(self, sha=None):
        r = {
            "target": "vae/sample.safetensors",
            "repo_id": "test/repo",
            "revision": "abc123",
            "filename": "sample.safetensors",
            "min_bytes": 1000000,
        }
        if sha is not None:
            r["sha256"] = sha
        return r

    def test_invalid_manifest_sha_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid sha256"):
            validate_model(self.record("not-a-hash"))

    def test_sha_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model"
            path.write_bytes(b"abc")
            self.assertTrue(verify_sha256(path, hashlib.sha256(b"abc").hexdigest()))
            self.assertFalse(verify_sha256(path, "0" * 64))

    def test_install_hardlinks_cached_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "cached.safetensors"
            source.write_bytes(b"x" * 1000001)
            models = root / "models"
            models.mkdir()
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"models": [self.record(), {
                **self.record(), "target": "loras/second.safetensors"
            }]}))
            with patch("install_models.hf_hub_download", return_value=str(source)):
                install(manifest, models)
            dest = models / "vae/sample.safetensors"
            self.assertTrue(dest.is_file())
            self.assertEqual(source.stat().st_ino, dest.stat().st_ino)

    def test_existing_hash_mismatch_fails_without_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models = root / "models"
            (models / "vae").mkdir(parents=True)
            (models / "vae/sample.safetensors").write_bytes(b"x" * 1000001)
            record = self.record("0" * 64)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"models": [record, {
                **self.record(), "target": "loras/second.safetensors"
            }]}))
            with patch("install_models.hf_hub_download") as download:
                with self.assertRaisesRegex(RuntimeError, "SHA256 mismatch"):
                    install(manifest, models)
                download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
