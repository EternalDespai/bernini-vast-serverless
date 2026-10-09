"""Exercise the shell launcher without a GPU or a live supervisor."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class RestartTests(unittest.TestCase):
    def run_restart(self, status, status_rc=0, restart_rc=0, override=""):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = root / "supervisorctl"
            fake.write_text('''#!/usr/bin/env bash
if [[ "$1" == -c ]]; then shift 2; fi
if [[ "$1" == status ]]; then
  printf '%s\\n' "$TEST_STATUS"
  exit "$TEST_STATUS_RC"
fi
printf '%s\\n' "$*" > "$TEST_CALL"
exit "$TEST_RESTART_RC"
''')
            fake.chmod(0o755)
            call = root / "call"
            env = dict(os.environ, PATH=directory + os.pathsep + os.environ['PATH'],
                       TEST_STATUS=status, TEST_STATUS_RC=str(status_rc),
                       TEST_RESTART_RC=str(restart_rc), TEST_CALL=str(call),
                       BERNINI_COMFY_SUPERVISOR_NAME=override)
            result = subprocess.run(['bash', str(Path(__file__).with_name('restart_comfyui.sh'))],
                                    env=env, capture_output=True, text=True)
            return result, call.read_text().strip() if call.exists() else None

    def test_unrelated_stopped_service_does_not_abort(self):
        result, call = self.run_restart('comfyui RUNNING pid 42\nportal STOPPED', 3)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(call, 'restart comfyui')

    def test_stopped_comfyui_can_be_restarted(self):
        result, call = self.run_restart('apps:comfyui STOPPED\ncomfyui-wrapper RUNNING', 3)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(call, 'restart apps:comfyui')

    def test_connection_error_does_not_restart_anything(self):
        result, call = self.run_restart('error connecting to comfyui socket', 4)
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(call)

    def test_ambiguous_services_require_override(self):
        result, call = self.run_restart('comfyui-a RUNNING\ncomfyui-b STOPPED', 3)
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(call)

    def test_explicit_override(self):
        result, call = self.run_restart('', 4, override='apps:comfyui')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(call, 'restart apps:comfyui')

    def test_restart_error_propagates(self):
        result, _ = self.run_restart('comfyui RUNNING', restart_rc=7)
        self.assertEqual(result.returncode, 7)

    def test_refuse_restart_all(self):
        result, call = self.run_restart('', override='all')
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(call)


if __name__ == '__main__':
    unittest.main()
