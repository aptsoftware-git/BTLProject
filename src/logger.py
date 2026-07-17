"""
logger.py
=========
Stage-based logging. Every stage class calls `self.logger.stage("...")` once
at the start of its work and `self.logger.info(...)` / `.warning(...)` for
detail lines, printed to console and (when configured) to logs/pipeline.log.

`PipelineLogger` subclasses `logging.Logger` directly so it satisfies the
`logger: logging.Logger` type hints used throughout the existing stage files
while adding the one extra method (`.stage()`) they call.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path


class PipelineLogger(logging.Logger):
    """A logging.Logger with an added .stage() banner method."""

    def stage(self, name: str) -> None:
        self.info("=" * 60)
        self.info(name)
        self.info("=" * 60)


def get_logger(name: str = "pipeline", log_file: Path | None = None) -> PipelineLogger:
    logging.setLoggerClass(PipelineLogger)
    logger = logging.getLogger(name)
    logging.setLoggerClass(logging.Logger)  # don't leak the custom class globally

    if not isinstance(logger, PipelineLogger):
        # logging.getLogger caches by name; if something already created a
        # plain Logger under this name, rebuild it as a PipelineLogger.
        logger.__class__ = PipelineLogger

    if not logger.handlers:
        logger.setLevel(logging.INFO)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(console_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        already_has_file_handler = any(
            isinstance(h, logging.FileHandler) and Path(h.baseFilename) == log_file
            for h in logger.handlers
        )
        if not already_has_file_handler:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
            logger.addHandler(file_handler)

    return logger  # type: ignore[return-value]