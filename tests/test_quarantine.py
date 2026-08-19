"""Tests for `pipeline.quarantine`."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.models import EntityType, QuarantineEntry, ReasonCode, SourceSystem
from pipeline.quarantine import write_quarantine_log


def _entry() -> QuarantineEntry:
    return QuarantineEntry(
        entity_type=EntityType.CUSTOMER,
        source_system=SourceSystem.ERP,
        reason_code=ReasonCode.MISSING_REQUIRED_FIELD,
        stage="validate",
        original_data={"CUST_ID": "C000001", "EMAIL": "person@example.com"},
    )


def test_write_quarantine_log_creates_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "quarantine_log.json"

    write_quarantine_log([_entry()], path)

    assert path.exists()


def test_write_quarantine_log_retains_original_data(tmp_path: Path) -> None:
    path = tmp_path / "quarantine_log.json"

    write_quarantine_log([_entry()], path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert len(payload) == 1
    assert payload[0]["reason_code"] == "missing_required_field"
    assert payload[0]["original_data"]["EMAIL"] == "person@example.com"


def test_write_quarantine_log_handles_empty_list(tmp_path: Path) -> None:
    path = tmp_path / "quarantine_log.json"

    write_quarantine_log([], path)

    assert json.loads(path.read_text(encoding="utf-8")) == []
