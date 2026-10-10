import asyncio
import io
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from ui_v6 import app
from ui_v6.vast_submit import submit_job, EndpointUnavailableError

class PollingTests(unittest.TestCase):
    def setUp(self):
        app.TASKS.clear()
        app.STATUS_CACHE.clear()
        app.SUBMISSIONS.clear()
        app.TASKS['a'*32] = {'state': 'waiting_for_gpu'}

    def test_waiting_status_cached_across_requests(self):
        with patch.object(app, 'fetch_status', return_value={'state':'queued','stage':'waiting_for_gpu'}) as fetch:
            first = app.read_status('a'*32)
            for _ in range(5):
                self.assertEqual(app.read_status('a'*32), first)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(first['poll_after_ms'], 60000)

    def test_local_pre_submission_error_never_reads_r2(self):
        app.TASKS['a'*32] = {'state':'failed','not_submitted':True}
        with patch.object(app,'fetch_status') as fetch:
            self.assertEqual(app.read_status('a'*32)['state'], 'failed')
            fetch.assert_not_called()

    def test_disconnect_does_not_attempt_second_response(self):
        handler = object.__new__(app.Handler)
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock(side_effect=ConnectionAbortedError(10053, 'closed'))
        handler.wfile = io.BytesIO()
        handler.respond(200, b'hello')
        self.assertTrue(handler.close_connection)
        handler.send_response.assert_called_once_with(200)

    def test_stopped_endpoint_not_queued(self):
        queued = Mock()
        class Client:
            def __init__(self, token): pass
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
            async def get_endpoint(self,name):
                return SimpleNamespace(data=SimpleNamespace(config=SimpleNamespace(endpoint_state='stopped')))
            queue_endpoint_request = queued
        with self.assertRaises(EndpointUnavailableError):
            asyncio.run(submit_job('ylxfcvlr','fake','a'*32,client_factory=Client))
        queued.assert_not_called()

    def test_duplicate_post_uploads_and_submits_once(self):
        job = 'b'*32
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'jobs' / job
            folder.mkdir(parents=True)
            (folder / 'workflow_api.json').write_text('{}')
            (root / 'benchmark_configured.txt').write_text('c'*32)
            handler = object.__new__(app.Handler)
            handler.path = '/upload-r2'
            body = ('job_id='+job).encode()
            handler.headers = {'Content-Length':str(len(body))}
            handler.respond = Mock()
            with patch.object(app,'ROOT',root), patch.object(app,'JOBS',root/'jobs'), patch.object(app,'extra_settings'), patch.object(app,'upload_to_r2') as upload, patch.object(app,'ensure_benchmark_from_upload',return_value=('c'*32,False)), patch.object(app.threading,'Thread') as thread:
                for _ in range(2):
                    handler.rfile = io.BytesIO(body)
                    handler.do_POST()
                upload.assert_called_once()
                thread.assert_called_once()
                self.assertEqual([c.args[0] for c in handler.respond.call_args_list],[303,303])
