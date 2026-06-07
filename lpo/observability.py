"""Per-run trace logging (Section 10).

Every run logs, under a trace_id: the question/context, the LP IR (model output
of record) plus the separate thinking trace, the restatement and human decision,
the SolverResult, the final explanation and critic flags, and token/latency per
stage. The provenance map (constraint -> source span) is the audit backbone.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger("lpo")

TRACE_DIR = os.environ.get("LPO_TRACE_DIR", "traces")


class Trace:
    def __init__(self, trace_id: str, question: str, context: Any):
        self.trace_id = trace_id
        self.data: dict[str, Any] = {
            "trace_id": trace_id,
            "question": question,
            "context": context,
            "attempts": [],
            "restatement": None,
            "human_confirmation": None,
            "solver_result": None,
            "explanation": None,
            "critic": None,
            "status": None,
        }

    def record_attempt(self, **fields: Any) -> None:
        self.data["attempts"].append(fields)

    def set(self, **fields: Any) -> None:
        self.data.update(fields)

    def flush(self) -> None:
        """Persist the trace as JSON. Best-effort; never breaks a request."""

        try:
            os.makedirs(TRACE_DIR, exist_ok=True)
            path = os.path.join(TRACE_DIR, f"{self.trace_id}.json")
            with open(path, "w") as fh:
                json.dump(self.data, fh, indent=2, default=str)
            logger.info("trace %s status=%s", self.trace_id, self.data.get("status"))
        except Exception:  # pragma: no cover
            logger.exception("failed to flush trace %s", self.trace_id)
