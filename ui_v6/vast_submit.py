"""Vast 1.8.3 submission contract shared by the v6 UI and repository UI."""
import math
import re


class EndpointUnavailableError(RuntimeError):
    pass


async def submit_job(name, token, job_id, timeout=14400, client_factory=None):
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise ValueError("Invalid job_id")
    timeout = float(timeout)
    if not math.isfinite(timeout) or not 60 <= timeout <= 86400:
        raise ValueError("BERNINI_REQUEST_TIMEOUT_SECONDS must be 60..86400")
    if client_factory is None:
        from vastai import Serverless
        client_factory = Serverless
    async with client_factory(token) as client:
        endpoint = await client.get_endpoint(name=name)
        config = getattr(getattr(endpoint, 'data', None), 'config', None)
        if getattr(config, 'endpoint_state', None) in ('stopped', 'suspended'):
            raise EndpointUnavailableError('Endpoint Vast остановлен. Включи его после настройки workgroup.')
        # Endpoint.request does not expose worker_timeout in Vast 1.8.3.
        # Set both allocation and HTTP execution timeouts on the public client.
        # Do not automatically replay a potentially still-running video job.
        result = await client.queue_endpoint_request(
            endpoint=endpoint, worker_route="/generate/sync",
            worker_payload={"job_id": job_id}, timeout=timeout,
            worker_timeout=timeout, retry=False,
        )
    if not isinstance(result, dict) or result.get("ok") is not True:
        status = result.get("status", "unknown") if isinstance(result, dict) else "unknown"
        raise RuntimeError(f"Vast request failed (HTTP {status})")
    body = result.get("response")
    if not isinstance(body, dict) or body.get("ok") is not True or body.get("job_id") != job_id:
        raise RuntimeError("Vast returned an invalid Bernini response")
    return body
