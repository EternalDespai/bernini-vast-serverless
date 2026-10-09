"""Offline regression tests for the Bernini R2 workflow patch."""
import json
import unittest

from r2_bridge import prepare_workflow


class WorkflowTests(unittest.TestCase):
    def test_all_reference_nodes_updated(self):
        workflow = {
            "5": {"class_type": "BerniniStudio",
                  "inputs": {"slot_images": json.dumps(["old.jpg", None])}},
            "21": {"class_type": "VHS_LoadVideo",
                   "inputs": {"video": "old.mp4"}},
            "22": {"class_type": "VHS_VideoCombine",
                   "inputs": {"filename_prefix": "old", "save_output": False}},
            "24": {"class_type": "LoadImage", "inputs": {"image": "old.jpg"}},
            "25": {"class_type": "LoadImage", "inputs": {"image": "other.jpg"}},
        }
        result = prepare_workflow(workflow, "new.mp4", "new.jpg", "Bernini_test")
        self.assertEqual(result["21"]["inputs"]["video"], "new.mp4")
        self.assertEqual(json.loads(result["5"]["inputs"]["slot_images"])[0], "new.jpg")
        self.assertEqual(result["24"]["inputs"]["image"], "new.jpg")
        self.assertEqual(result["25"]["inputs"]["image"], "new.jpg")
        self.assertTrue(result["22"]["inputs"]["save_output"])
        self.assertEqual(result["22"]["inputs"]["filename_prefix"], "Bernini_test")


if __name__ == "__main__":
    unittest.main()
