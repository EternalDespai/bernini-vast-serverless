"""Tests HTTP contract without GPU or actual R2 credentials."""
import threading
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import bridge_api


class BridgeAPITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(bridge_api.app)

    def test_health(self):
        class HealthyResponse:
            def raise_for_status(self):
                pass
            def json(self):
                return {"BerniniStudio": {}}
        with patch.object(bridge_api.requests, "get", return_value=HealthyResponse()):
            r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)

    def test_health_rejects_missing_comfyui(self):
        with patch.object(bridge_api.requests, "get", side_effect=bridge_api.requests.ConnectionError("offline")):
            r = self.client.get("/health")
        self.assertEqual(r.status_code, 503)

    def test_invalid_job_id(self):
        r = self.client.post("/generate/sync", json={"job_id": "../secrets"})
        self.assertEqual(r.status_code, 422)

    def test_submit_valid_job(self):
        with patch.object(bridge_api, "run") as run:
            job_id = "a" * 32
            r = self.client.post("/generate/sync", json={"job_id": job_id})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["result_key"], f"jobs/{job_id}/result.mp4")
            run.assert_called_once_with(job_id, 7200)

    def test_failure_has_no_internal_details(self):
        with patch.object(bridge_api, "run", side_effect=RuntimeError("R2_SECRET_ACCESS_KEY=secret")):
            r = self.client.post("/generate/sync", json={"job_id": "a" * 32})
            self.assertEqual(r.status_code, 500)
            self.assertNotIn("secret", r.text)

    def test_concurrent_request_rejected(self):
        entered = threading.Event()
        release = threading.Event()
        def slow_run(*args):
            entered.set()
            release.wait(timeout=5)
        result = {}
        def first():
            result["response"] = self.client.post("/generate/sync", json={"job_id": "a" * 32})
        with patch.object(bridge_api, "run", side_effect=slow_run):
            thread = threading.Thread(target=first)
            thread.start()
            self.assertTrue(entered.wait(5))
            try:
                r = self.client.post("/generate/sync", json={"job_id": "b" * 32})
                self.assertEqual(r.status_code, 429)
            finally:
                release.set()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
