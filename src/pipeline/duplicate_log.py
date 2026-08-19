"""Persist intra-system duplicate-merge logs to `duplicate_log.json`.

Every near-duplicate cluster `pipeline.cleaners.duplicates.collapse_duplicates`
collapses into one canonical row is recorded here, so a run leaves behind a
durable, inspectable record of which rows were merged and on what basis (see
CLAUDE.md's "Intra-system near-duplicates" rule) -- not just the deduplicated
data itself.
"""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.models import DuplicateMergeLog


def write_duplicate_log(entries: list[DuplicateMergeLog], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [entry.model_dump(mode="json") for entry in entries]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
