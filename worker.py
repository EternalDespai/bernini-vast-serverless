"""Vast.ai PyWorker SDK adapter for the local Bernini bridge.

IMPORTANT: not deployable without provisioning Bernini models and a real
benchmark job already present in the R2 bucket. Fails closed instead of
running an unrelated default SD1.5 benchmark.
"""
import os
from vastai import Worker, WorkerConfig, HandlerConfig, BenchmarkConfig, LogActionConfig


def benchmark_payload():
    job_id = os.environ.get("BERNINI_BENCHMARK_JOB_ID", "")
    from r2_bridge import JOB_RE
    if not JOB_RE.fullmatch(job_id):
        raise RuntimeError(
            "BERNINI_BENCHMARK_JOB_ID must be a 32-character R2 test-job ID"
        )
    return {"job_id": job_id}


def make_config():
    if not os.environ.get("BERNINI_BENCHMARK_JOB_ID"):
        raise RuntimeError(
            "Refusing to start: set BERNINI_BENCHMARK_JOB_ID after provisioning"
        )
    return WorkerConfig(
        model_server_url="http://127.0.0.1",
        model_server_port=int(os.getenv("BERNINI_BRIDGE_PORT", "18300")),
        model_log_file=os.getenv("BERNINI_BRIDGE_LOG", "/tmp/bernini-bridge.log"),
        model_healthcheck_url="/health",
        handlers=[
            HandlerConfig(
                route="/generate/sync",
                allow_parallel_requests=False,
                max_queue_time=10.0,
                benchmark_config=BenchmarkConfig(generator=benchmark_payload),
            )
        ],
        log_action_config=LogActionConfig(
            on_load=["BERNINI_BRIDGE_READY"],
            on_error=["BERNINI_BRIDGE_FATAL"],
            on_info=[],
        ),
    )


if __name__ == "__main__":
    Worker(make_config()).run()
