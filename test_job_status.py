"""Offline R2 status tests: no credentials, GPU, network or billing."""
import json
import unittest

from job_status import JobStatus


class FakeS3:
    def __init__(self):
        self.writes = []

    def put_object(self, **kwargs):
        self.writes.append(kwargs)


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.s3 = FakeS3()
        self.job = JobStatus(self.s3, "test-bucket", "a" * 32)

    def last(self):
        return json.loads(self.s3.writes[-1]["Body"])

    def test_stages_and_completion(self):
        self.job.publish(state="running", stage="downloading", force=True)
        self.assertEqual(self.last()["percent"], None)
        self.job.publish(state="running", stage="sampling", step_percent=47, force=True)
        self.assertEqual(self.last()["step_percent"], 47)
        self.assertEqual(self.last()["percent_kind"], "sampling_step")
        self.job.publish(state="running", stage="uploading", force=True)
        self.assertIsNone(self.last()["percent"])
        self.job.publish(state="complete", stage="complete", force=True)
        self.assertEqual(self.last()["percent"], 100)
        self.assertEqual(self.last()["state"], "complete")

    def test_failure_clears_percentage(self):
        self.job.publish(state="running", stage="sampling", step_percent=77, force=True)
        self.job.publish(state="failed", stage="failed", force=True)
        self.assertIsNone(self.last()["percent"])

    def test_bounds_percentage(self):
        self.job.publish(stage="sampling", step_percent=110, force=True)
        self.assertEqual(self.last()["percent"], 100)


if __name__ == "__main__":
    unittest.main()
