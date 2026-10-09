"""Offline checks for safe Vast deployment command construction."""
import unittest
from deploy_serverless import commands

class DeploymentTests(unittest.TestCase):
    def test_scale_to_zero_one_worker(self):
        endpoint, group = commands("bernini-rv2v", "template_12345")
        joined = " ".join(endpoint)
        for flag, value in (
            ("--min_load", "0"), ("--min_workers", "0"),
            ("--cold_workers", "0"), ("--max_workers", "1"),
            ("--inactivity_timeout", "600"),
        ):
            self.assertIn(flag + " " + value, joined)
        self.assertIn("--template_hash template_12345", " ".join(group))
    def test_reject_shell_injection(self):
        with self.assertRaises(ValueError):
            commands("bad;echo hacked", "template_12345")
        with self.assertRaises(ValueError):
            commands("bernini-rv2v", "$(whoami)")
if __name__ == "__main__":
    unittest.main()
