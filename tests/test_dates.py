"""Tests for date parsing/cleaning, grounded in datagen's actual corruption formats."""

from __future__ import annotations

from datetime import date

import polars as pl

from datagen.messiness.dates import _INVALID_PLACEHOLDERS, _format_variants
from pipeline.cleaners.dates import clean_date_column, parse_date


def test_parse_date_handles_every_real_format_datagen_produces() -> None:
    original = date(2024, 3, 7)
    variants = _format_variants(original)
    real_variants = variants[: len(variants) - len(_INVALID_PLACEHOLDERS)]

    for variant in real_variants:
        assert parse_date(variant) == original, f"failed to parse {variant!r}"


def test_parse_date_handles_iso_format() -> None:
    assert parse_date("2024-03-07") == date(2024, 3, 7)


def test_parse_date_returns_none_for_known_invalid_placeholders() -> None:
    for placeholder in _INVALID_PLACEHOLDERS:
        assert parse_date(placeholder) is None


def test_clean_date_column_flags_unparseable_non_null_values() -> None:
    df = pl.DataFrame(
        {
            "ISSUE_DT": ["2024-03-07", "03/07/2024", "0000-00-00", None],
        }
    )

    cleaned = clean_date_column(df, "ISSUE_DT")

    assert cleaned["ISSUE_DT"].to_list() == ["2024-03-07", "2024-03-07", None, None]
    assert cleaned["ISSUE_DT_invalid"].to_list() == [False, False, True, False]
