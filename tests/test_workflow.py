"""Unit checks for Bernini workflow patching. No GPU/R2 required."""
import json
import unittest

from r2_bridge import prepare_workflow, validate_rv2v_workflow, JOB_RE


def example_workflow():
    return {
        "5": {"class_type": "BerniniStudio", "inputs": {
            "slot_images": json.dumps(["original.jpg", None, None]),
            "task_type": "rv2v",
            "prompt": "Replace the man with the person from image0",
            "source_video": ["21", 0]
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
        validate_rv2v_workflow(wf)

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

    def test_wrong_mode_or_prompt_is_rejected_before_inference(self):
        wf = example_workflow()
        wf["5"]["inputs"]["task_type"] = "v2v"
        with self.assertRaises(ValueError):
            validate_rv2v_workflow(wf)
        wf["5"]["inputs"]["task_type"] = "rv2v"
        wf["5"]["inputs"]["prompt"] = "Make a nice video"
        with self.assertRaises(ValueError):
            validate_rv2v_workflow(wf)

    def test_only_image0_source_is_replaced(self):
        wf = example_workflow()
        wf["5"]["inputs"]["image0"] = ["24", 0]
        wf["24"] = {"class_type": "LoadImage", "inputs": {"image": "old_ref.jpg"}}
        wf["25"] = {"class_type": "LoadImage", "inputs": {"image": "unrelated.png"}}
        result = prepare_workflow(wf, "clip.mp4", "new_ref.jpg", "output")
        self.assertEqual(result["24"]["inputs"]["image"], "new_ref.jpg")
        self.assertEqual(result["25"]["inputs"]["image"], "unrelated.png")
        validate_rv2v_workflow(result)

    def test_job_id_validation(self):
        self.assertIsNotNone(JOB_RE.fullmatch("a" * 32))
        self.assertIsNone(JOB_RE.fullmatch("../secret"))


if __name__ == "__main__":
    unittest.main()
