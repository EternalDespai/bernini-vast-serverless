import asyncio
import os
import unittest
from unittest.mock import patch

from ui_v6.vast_submit import submit_job


class VastIntegrationTests(unittest.TestCase):
    def test_real_sdk_worker_and_benchmark_contract(self):
        from worker import make_config
        from vastai.serverless.server.worker import EndpointHandlerFactory
        with patch.dict(os.environ, {'BERNINI_BENCHMARK_JOB_ID': 'a' * 32}):
            factory = EndpointHandlerFactory(make_config())
            handler = factory.get_all_handlers()['/generate/sync']
            self.assertFalse(handler.do_warmup_benchmark)
            self.assertEqual(handler.make_benchmark_payload().generate_payload_json(),
                             {'job_id': 'a' * 32})
            payload = handler.payload_cls().from_json_msg({'job_id': 'b' * 32})
            self.assertEqual(payload.generate_payload_json(), {'job_id': 'b' * 32})

    def test_sdk_supports_long_worker_timeout(self):
        import inspect
        from vastai import Serverless
        self.assertIn('worker_timeout', inspect.signature(Serverless.queue_endpoint_request).parameters)

    def fake(self, response):
        calls = {}
        class Client:
            def __init__(self, token):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def get_endpoint(self, name):
                calls['name'] = name
                return 'endpoint'
            async def queue_endpoint_request(self, **kwargs):
                calls.update(kwargs)
                return response
        return Client, calls

    def test_long_video_request_no_automatic_replay(self):
        body = {'ok': True, 'job_id': 'a' * 32}
        client, calls = self.fake({'ok': True, 'response': body})
        self.assertEqual(asyncio.run(submit_job('ylxfcvlr', 'fake', 'a' * 32, client_factory=client)), body)
        self.assertEqual(calls['worker_timeout'], 14400)
        self.assertEqual(calls['timeout'], 14400)
        self.assertFalse(calls['retry'])

    def test_http_and_nested_errors_are_not_success(self):
        for response in ({'ok': False, 'status': 500},
                         {'ok': True, 'response': {'ok': False}},
                         {'ok': True, 'response': {'ok': True, 'job_id': 'b' * 32}}):
            with self.subTest(response=response):
                client, _ = self.fake(response)
                with self.assertRaises(RuntimeError):
                    asyncio.run(submit_job('ylxfcvlr', 'fake', 'a' * 32, client_factory=client))

    def test_invalid_timeout_fails_before_connection(self):
        for value in ('nan', 0, 90000):
            with self.assertRaises(ValueError):
                asyncio.run(submit_job('ylxfcvlr', 'fake', 'a' * 32, timeout=value))
