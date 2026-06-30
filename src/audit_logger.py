"""Append-only audit log of claim-review decisions.

Every evaluation is recorded as one JSON object per line (JSONL). This gives a
simple, durable, human-readable trail of what was decided, by which rule version,
and why - supporting the report's emphasis on auditability. No database.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Iterable, List

from .schemas import EvalResult

DEFAULT_LOG_PATH = "audit_log.jsonl"


def log_results(results: Iterable[EvalResult], path: str = DEFAULT_LOG_PATH) -> int:
    """Append each result to the JSONL audit log. Returns count written."""
    written = 0
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for result in results:
            record = {
                "logged_at": datetime.now(timezone.utc).isoformat(),
                "timestamp": result.timestamp,
                "rule_id": result.rule_id,
                "rule_version": result.rule_version,
                "claim_id": result.claim_id,
                "outcome": result.outcome.value,
                "reasons": result.reasons,
            }
            fh.write(json.dumps(record) + "\n")
            written += 1
    return written


def log_event(event: dict, path: str = DEFAULT_LOG_PATH) -> None:
    """Append a single non-claim audit event (e.g. a rule change) as JSONL.

    Append-only: this never modifies or removes existing entries.
    """
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    record = {"logged_at": datetime.now(timezone.utc).isoformat(), **event}
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def read_log(path: str = DEFAULT_LOG_PATH) -> List[dict]:
    """Read all audit-log entries (oldest first). Empty list if no log yet."""
    if not os.path.exists(path):
        return []
    entries: List[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries
