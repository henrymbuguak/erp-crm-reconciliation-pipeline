"""Tests for `pipeline.crosswalk`."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from pipeline.crosswalk import load_crosswalk, save_crosswalk, upsert_crosswalk
from pipeline.models import CrosswalkEntry, EntityType


def _entry(entity_type: EntityType, erp_key: str | None, crm_key: str | None) -> CrosswalkEntry:
    return CrosswalkEntry(
        entity_type=entity_type, canonical_id=uuid4(), erp_key=erp_key, crm_key=crm_key
    )


def test_load_crosswalk_returns_empty_list_when_file_missing(tmp_path: Path) -> None:
    assert load_crosswalk(tmp_path / "crosswalk.json") == []


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "crosswalk.json"
    entries = [_entry(EntityType.CUSTOMER, "C000001", "CUST-000001")]

    save_crosswalk(entries, path)
    loaded = load_crosswalk(path)

    assert loaded == entries


def test_upsert_crosswalk_appends_new_entries(tmp_path: Path) -> None:
    path = tmp_path / "crosswalk.json"
    first = _entry(EntityType.CUSTOMER, "C000001", "CUST-000001")
    save_crosswalk([first], path)

    second = _entry(EntityType.CUSTOMER, "C000002", None)
    merged = upsert_crosswalk([second], path)

    assert {e.erp_key for e in merged} == {"C000001", "C000002"}
    assert load_crosswalk(path) == merged


def test_upsert_crosswalk_preserves_canonical_id_when_key_already_exists(tmp_path: Path) -> None:
    """Idempotency: re-running on the same input must not mint a new UUID for an existing key."""
    path = tmp_path / "crosswalk.json"
    original = _entry(EntityType.CUSTOMER, "C000001", "CUST-000001")
    save_crosswalk([original], path)

    # Simulate a re-run: same (entity_type, erp_key, crm_key) key, but resolve.py
    # would mint a brand-new UUID for it.
    rerun_entry = _entry(EntityType.CUSTOMER, "C000001", "CUST-000001")
    assert rerun_entry.canonical_id != original.canonical_id

    merged = upsert_crosswalk([rerun_entry], path)

    assert len(merged) == 1
    assert merged[0].canonical_id == original.canonical_id


def test_upsert_crosswalk_treats_newly_resolved_orphan_as_a_new_entry(tmp_path: Path) -> None:
    """Known limitation: a corrected export's now-resolved orphan mints a second UUID."""
    path = tmp_path / "crosswalk.json"
    orphan = _entry(EntityType.INVOICE, "INV-0001", None)
    save_crosswalk([orphan], path)

    now_resolved = _entry(EntityType.INVOICE, "INV-0001", "IN-0001")
    merged = upsert_crosswalk([now_resolved], path)

    assert len(merged) == 2
    assert {(e.erp_key, e.crm_key) for e in merged} == {("INV-0001", None), ("INV-0001", "IN-0001")}
