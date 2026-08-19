"""Persist quarantined records to `quarantine_log.json`.

Every row that fails cleaning/validation, or resolves to the `ambiguous`
outcome, must land here -- never be silently dropped (see CLAUDE.md's "Zero
silent failures" rule). `original_data` may retain full PII since this file
is the designated place for it; PII masking only applies to console/summary
output (see `pipeline.cli`), not this file.
"""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.models import QuarantineEntry


def write_quarantine_log(entries: list[QuarantineEntry], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [entry.model_dump(mode="json") for entry in entries]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
