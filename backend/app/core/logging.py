"""Backend logging configuration."""
from __future__ import annotations

import logging
from typing import Literal


def configure_logging(level: str) -> None:
    """Configure application logging once at startup."""
    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.setLevel(level.upper())
        return

    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )


def log_model_event(
    *,
    event: Literal["query", "embedding"],
    model: str,
    latency_ms: int,
    fallback: str,
    intent: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    dimensions: int | None = None,
) -> None:
    """Log model telemetry without request or response content."""
    fields = [f"event={event}", f"model={model}"]
    if intent is not None:
        fields.append(f"intent={intent}")
    if dimensions is not None:
        fields.append(f"dimensions={dimensions}")
    fields.append(f"latency_ms={latency_ms}")
    if input_tokens is not None:
        fields.append(f"input_tokens={input_tokens}")
    if output_tokens is not None:
        fields.append(f"output_tokens={output_tokens}")
    fields.append(f"fallback={fallback}")
    logging.getLogger("backend.models").info(" ".join(fields))
