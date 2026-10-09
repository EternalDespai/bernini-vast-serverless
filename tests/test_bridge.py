"""Offline integration tests: fake R2 and fake ComfyUI, no credentials or GPU."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import r2_bridge
from test_workflow import example_workflow


class FakeS3:
    def __init__(self, workflow):
        self.objects = {
            "source.mp4": b"fake video",
            "reference.jpg": b"fake image",
            "workflow_api.json": json.dumps(workflow).encode(),
        }
        self.uploads = {}

    def head_object(self, Bucket, Key):
        return {"ContentLength": len(self.objects[Key.rsplit("/", 1)[1]])}

    def download_file(self, bucket, key, filename):
        Path(filename).write_bytes(self.objects[key.rsplit("/", 1)[1]])

    def upload_file(self, filename, bucket, key, ExtraArgs):
        assert ExtraArgs["ContentType"] == "video/mp4"
        self.uploads[key] = Path(filename).read_bytes()


class FakeResponse:
    def __init__(self, body):
        self.body = body
        self.ok = True

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def post(self, url, json, timeout):
        assert url.endswith("/prompt")
        wf = json["prompt"]
        assert wf["21"]["inputs"]["video"].endswith("_source.mp4")
        assert wf["5"]["inputs"]["slot_images"].startswith('["bernini_')
        return FakeResponse({"prompt_id": "mock-prompt"})

    def get(self, url, timeout):
        assert url.endswith("/history/mock-prompt")
        return FakeResponse({"mock-prompt": {
            "status": {"status_str": "success"},
            "outputs": {"22": {"gifs": [
                {"filename": "Bernini_test.mp4", "subfolder": "", "type": "output"}
            ]}}
        }})


class BridgeTests(unittest.TestCase):
    def test_end_to_end_mock(self):
        job_id = "a" * 32
        fake_s3 = FakeS3(example_workflow())
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            inputs, outputs = base / "input", base / "output"
            inputs.mkdir()
            outputs.mkdir()
            (outputs / "Bernini_test.mp4").write_bytes(b"rendered-video")
            env = {
                "R2_BUCKET": "bernini-rv2v",
                "COMFY_INPUT_DIR": str(inputs),
                "COMFY_OUTPUT_DIR": str(outputs),
                "COMFY_API_URL": "http://127.0.0.1:18188",
            }
            with patch.dict("os.environ", env), \
                 patch.object(r2_bridge, "s3_client", return_value=fake_s3), \
                 patch.object(r2_bridge.requests, "Session", FakeSession):
                with patch.dict("os.environ", {"BERNINI_FULL_VIDEO": "0"}):
                    r2_bridge.run(job_id, timeout=5)
            self.assertEqual(
                fake_s3.uploads[f"jobs/{job_id}/result.mp4"], b"rendered-video"
            )
            self.assertEqual(list(inputs.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
