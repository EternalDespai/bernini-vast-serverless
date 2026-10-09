"""Unit checks for Bernini workflow patching. No GPU/R2 required."""
import json
import unittest

from r2_bridge import prepare_workflow, JOB_RE


def example_workflow():
    return {
        "5": {"class_type": "BerniniStudio", "inputs": {
            "slot_images": json.dumps(["original.jpg", None, None])
        }},
        "21": {"class_type": "VHS_LoadVideo", "inputs": {
            "video": "original.mp4"
        }},
        "22": {"class_type": "VHS_VideoCombine", "inputs": {
            "filename_prefix": "old", "save_output": False
        }},
        "77": {"class_type": "OtherNode", "inputs": {"kept": True}}
    }


class WorkflowTests(unittest.TestCase):
    def test_patches_expected_inputs(self):
        wf = prepare_workflow(example_workflow(), "new.mp4", "new.jpg", "job123")
        self.assertEqual(wf["21"]["inputs"]["video"], "new.mp4")
        self.assertEqual(json.loads(wf["5"]["inputs"]["slot_images"])[0], "new.jpg")
        self.assertEqual(wf["22"]["inputs"]["filename_prefix"], "job123")
        self.assertTrue(wf["22"]["inputs"]["save_output"])
        self.assertTrue(wf["77"]["inputs"]["kept"])

    def test_rejects_wrong_nodes(self):
        wf = example_workflow()
        wf["5"]["class_type"] = "NotBernini"
        with self.assertRaises(ValueError):
            prepare_workflow(wf, "x.mp4", "x.jpg", "prefix")

    def test_rejects_invalid_slot_images(self):
        wf = example_workflow()
        wf["5"]["inputs"]["slot_images"] = "not-json"
        with self.assertRaises(json.JSONDecodeError):
            prepare_workflow(wf, "x.mp4", "x.jpg", "prefix")

    def test_job_id_validation(self):
        self.assertIsNotNone(JOB_RE.fullmatch("a" * 32))
        self.assertIsNone(JOB_RE.fullmatch("../secret"))


if __name__ == "__main__":
    unittest.main()
