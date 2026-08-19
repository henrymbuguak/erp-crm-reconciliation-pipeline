"""Persist the crosswalk table as JSON, with an idempotent upsert.

The crosswalk is keyed on `(entity_type, erp_key, crm_key)` (see
`CrosswalkEntry`) rather than on `canonical_id`, since `resolve.py` mints a
fresh UUID on every run. Re-running the pipeline on unchanged input must not
duplicate records or reassign existing canonical IDs, so `upsert_crosswalk`
uses a **reject-on-conflict** strategy: when an incoming entry's key already
exists on disk, the existing entry (and its `canonical_id`) is kept as-is
and the incoming one is discarded; only genuinely new keys are appended.

Known limitation (deliberate, not silently worked around): because the key
includes the exact `erp_key`/`crm_key` *shape*, a previously-orphaned record
whose missing side later gets resolved (e.g. a corrected export fixes a
one-sided invoice) has a different key on the next run -- `(entity_type,
"INV-1", None)` vs. `(entity_type, "INV-1", "IN-1")` are different keys --
and is written as a brand-new entry with a new `canonical_id`, rather than
resolving forward onto the stale orphan entry, which is left in place.
"""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.models import CrosswalkEntry, EntityType


def _key(entry: CrosswalkEntry) -> tuple[EntityType, str | None, str | None]:
    return (entry.entity_type, entry.erp_key, entry.crm_key)


def load_crosswalk(path: Path) -> list[CrosswalkEntry]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [CrosswalkEntry.model_validate(item) for item in raw]


def save_crosswalk(entries: list[CrosswalkEntry], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [entry.model_dump(mode="json") for entry in entries]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def upsert_crosswalk(new_entries: list[CrosswalkEntry], path: Path) -> list[CrosswalkEntry]:
    """Merge `new_entries` into the crosswalk at `path`, keyed as described above."""
    existing = load_crosswalk(path)
    known_keys = {_key(entry) for entry in existing}

    merged = list(existing)
    for entry in new_entries:
        key = _key(entry)
        if key not in known_keys:
            merged.append(entry)
            known_keys.add(key)

    save_crosswalk(merged, path)
    return merged
