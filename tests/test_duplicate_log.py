"""Tests for `pipeline.duplicate_log`."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.duplicate_log import write_duplicate_log
from pipeline.models import DuplicateMergeLog


def _log() -> DuplicateMergeLog:
    return DuplicateMergeLog(
        key_column="CUST_ID",
        key_value="C000001",
        row_count=2,
        differing_columns=["CITY"],
    )


def test_write_duplicate_log_creates_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "duplicate_log.json"

    write_duplicate_log([_log()], path)

    assert path.exists()


def test_write_duplicate_log_retains_merge_details(tmp_path: Path) -> None:
    path = tmp_path / "duplicate_log.json"

    write_duplicate_log([_log()], path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert len(payload) == 1
    assert payload[0]["key_value"] == "C000001"
    assert payload[0]["row_count"] == 2
    assert payload[0]["differing_columns"] == ["CITY"]


def test_write_duplicate_log_handles_empty_list(tmp_path: Path) -> None:
    path = tmp_path / "duplicate_log.json"

    write_duplicate_log([], path)

    assert json.loads(path.read_text(encoding="utf-8")) == []
