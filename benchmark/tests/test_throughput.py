"""Throughput benchmark: concurrent request handling."""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx  # type: ignore[import-not-found]
import pytest  # type: ignore[import-not-found]

CONCURRENCY_LEVELS = [1, 5, 10, 25]
REQUESTS_PER_LEVEL = 100


async def _send_requests(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    concurrency: int,
    total: int,
    json_body: dict[str, Any] | None = None,
) -> float:
    """Send *total* requests at *concurrency* and return elapsed seconds."""
    sem = asyncio.Semaphore(concurrency)

    async def _one() -> None:
        async with sem:
            if method == "GET":
                await client.get(url)
            else:
                await client.post(url, json=json_body or {})

    start = time.perf_counter()
    await asyncio.gather(*[_one() for _ in range(total)])
    return time.perf_counter() - start


@pytest.mark.asyncio
@pytest.mark.parametrize("concurrency", CONCURRENCY_LEVELS)
async def test_rest_throughput(
    rest_app: Any,
    concurrency: int,
    sample_customer_id: str,
) -> None:
    """Measure REST QPS at various concurrency levels."""
    base_url = "http://testserver"
    transport = httpx.ASGITransport(app=rest_app.app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
        elapsed = await _send_requests(
            client,
            "GET",
            f"/api/v1/customers/{sample_customer_id}/health",
            concurrency=concurrency,
            total=REQUESTS_PER_LEVEL,
        )
    qps = REQUESTS_PER_LEVEL / elapsed
    assert qps > 0  # noqa: S101


@pytest.mark.asyncio
@pytest.mark.parametrize("concurrency", CONCURRENCY_LEVELS)
async def test_cognimesh_throughput(
    mesh_app: Any,
    concurrency: int,
    sample_customer_id: str,
) -> None:
    """Measure CogniMesh QPS at various concurrency levels."""
    base_url = "http://testserver"
    transport = httpx.ASGITransport(app=mesh_app.app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
        elapsed = await _send_requests(
            client,
            "POST",
            "/query",
            concurrency=concurrency,
            total=REQUESTS_PER_LEVEL,
            json_body={
                "uc_id": "UC-01",
                "params": {"customer_id": sample_customer_id},
            },
        )
    qps = REQUESTS_PER_LEVEL / elapsed
    assert qps > 0  # noqa: S101
