import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from install_models import install, validate_model


class ModelInstallTests(unittest.TestCase):
    def test_rejects_incomplete_models(self):
        with self.assertRaises(ValueError):
            validate_model({"target": "vae/wan_2.1_vae.safetensors", "repo_id": ""})

    def test_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            validate_model({"target": "../bad.safetensors"})

    def test_example_manifest_validates_dry_run_without_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("install_models.hf_hub_download") as downloader:
                install("model_manifest.example.json", tmp, dry_run=True)
                downloader.assert_not_called()

    def test_local_dry_run_no_download(self):
        records = [{"target": f"loras/model_{i}.safetensors",
                    "repo_id": "publisher/repo", "revision": "abc123",
                    "filename": f"model_{i}.safetensors", "min_bytes": 1000000}
                   for i in range(2)]
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "models.json"
            manifest.write_text(json.dumps({"models": records}), encoding="utf-8")
            with patch("install_models.hf_hub_download") as downloader:
                install(manifest, tmp, dry_run=True)
                downloader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
