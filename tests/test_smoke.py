import unittest
import json
from pathlib import Path

class SmokeTestDocs(unittest.TestCase):
    def test_completed_manifest_has_all_sources(self):
        doc=json.loads(Path("model_manifest.example.json").read_text())
        self.assertEqual(len(doc["models"]),6)
        for m in doc["models"]:
            self.assertTrue(m["repo_id"])
            self.assertTrue(m["revision"])
            self.assertTrue(m["filename"])
    def test_smoke_script_never_exposes_server(self):
        sh=Path("gpu_smoke_test.sh").read_text()
        self.assertIn('127.0.0.1:18188',sh)
        self.assertIn('r2_bridge.py',sh)
