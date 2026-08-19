"""Tests for missing-value marker normalization."""

from __future__ import annotations

import polars as pl

from datagen.messiness.missing import MISSING_MARKERS as DATAGEN_MISSING_MARKERS
from pipeline.cleaners.missing import (
    MISSING_MARKERS,
    clean_missing_markers,
    normalize_missing_value,
)


def test_missing_markers_match_datagen_marker_set() -> None:
    # datagen's marker set includes native `None`, which is already a Utf8
    # null after ingestion and needs no explicit normalization here.
    assert {m for m in DATAGEN_MISSING_MARKERS if m is not None} == set(MISSING_MARKERS)


def test_normalize_missing_value_maps_known_markers_to_none() -> None:
    for marker in ("", "N/A", "NULL", "--", "unknown"):
        assert normalize_missing_value(marker) is None
    assert normalize_missing_value(None) is None


def test_normalize_missing_value_passes_through_real_values() -> None:
    assert normalize_missing_value("Alice Smith") == "Alice Smith"
    # trailing space -> not an exact marker match
    assert normalize_missing_value("N/A ") == "N/A "


def test_clean_missing_markers_normalizes_across_columns() -> None:
    df = pl.DataFrame(
        {
            "EMAIL_ADDR": ["alice@example.com", "N/A", "--"],
            "PHONE_NUM": ["555-0100", "unknown", "555-0102"],
            "OTHER": ["x", "y", "z"],
        }
    )

    cleaned = clean_missing_markers(df, ["EMAIL_ADDR", "PHONE_NUM"])

    assert cleaned["EMAIL_ADDR"].to_list() == ["alice@example.com", None, None]
    assert cleaned["PHONE_NUM"].to_list() == ["555-0100", None, "555-0102"]
    assert cleaned["OTHER"].to_list() == ["x", "y", "z"]
