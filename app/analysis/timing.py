"""Analysis timings and model usage; report contents and credentials stay out of logs."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)
_trace: ContextVar[tuple[str, float] | None] = ContextVar(
    "analysis_trace", default=None
)


def record(event: str, **fields: Any) -> None:
    trace = _trace.get()
    logger.info(
        "PERF %s",
        json.dumps(
            {
                "event": event,
                "trace_id": trace[0] if trace else None,
                "offset_ms": (
                    round((perf_counter() - trace[1]) * 1000, 3) if trace else None
                ),
                **fields,
            },
            ensure_ascii=False,
        ),
    )


@contextmanager
def timed(stage: str, **fields: Any) -> Iterator[None]:
    started = perf_counter()
    record("start", stage=stage, **fields)
    status = "ok"
    error_type = None
    try:
        yield
    except BaseException as error:
        status = "error"
        error_type = type(error).__name__
        raise
    finally:
        record(
            "finish",
            stage=stage,
            status=status,
            error_type=error_type,
            duration_ms=round((perf_counter() - started) * 1000, 3),
            **fields,
        )


@contextmanager
def analysis_trace(inns: list[str]) -> Iterator[str]:
    trace_id = uuid4().hex
    token = _trace.set((trace_id, perf_counter()))
    try:
        with timed("request", inns=inns):
            yield trace_id
    finally:
        _trace.reset(token)


def record_llm_result(result: Any, **fields: Any) -> None:
    usage = result.usage
    response = result.response
    details = response.provider_details or {}
    record(
        "llm_usage",
        **fields,
        model=response.model_name,
        provider=response.provider_name,
        inference_provider=details.get("downstream_provider"),
        cost_usd=details.get("cost"),
        generation_id=response.provider_response_id,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cached_input_tokens=usage.cache_read_tokens,
        reasoning_tokens=usage.details.get("reasoning_tokens"),
        model_requests=usage.requests,
        finish_reason=response.finish_reason,
    )
