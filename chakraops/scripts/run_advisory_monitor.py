# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R65 advisory monitor entrypoint — separate from API / legacy scheduler."""

from __future__ import annotations

import logging
import os
import signal
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("chakraops.monitor")


def main() -> int:
    # Hard safety: never enable trade execution from worker.
    os.environ.setdefault("trade_execution", "false")
    os.environ.setdefault("manual_only", "true")
    os.environ["CHAKRAOPS_SCHEDULER_ENABLED"] = "false"
    os.environ["CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED"] = "false"

    from app.core.monitor.advisory_worker_r54 import get_monitor_worker

    worker = get_monitor_worker()
    stop = False

    def _stop(*_args):
        nonlocal stop
        stop = True
        worker.stop()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    logger.info("Starting R65 advisory monitor (manual_only, no broker writes)")
    worker.start()
    # Immediate first cycle
    try:
        worker.run_once()
    except Exception as exc:
        logger.warning("initial monitor cycle failed: %s", type(exc).__name__)

    while not stop and worker.running:
        time.sleep(1.0)
    logger.info("Advisory monitor stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
