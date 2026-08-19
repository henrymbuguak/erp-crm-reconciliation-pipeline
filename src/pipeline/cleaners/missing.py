"""Normalize missing-value markers to null.

`datagen`'s missing-value injection (see `src/datagen/messiness/missing.py`)
replaces cells with one of a fixed set of markers: a true null, an empty
string, or a sentinel like ``"N/A"``. Recognizing all of them here means
downstream per-field required/optional handling only ever has to deal with
"present" vs. "null" -- not a grab bag of sentinel spellings.
"""

from __future__ import annotations

import polars as pl

# Mirrors datagen.messiness.missing.MISSING_MARKERS, minus the native `None`
# (which is already a Utf8 null after ingestion and needs no normalization).
MISSING_MARKERS: frozenset[str] = frozenset({"", "N/A", "NULL", "--", "unknown"})


def normalize_missing_value(value: str | None) -> str | None:
    """Map a known missing-value marker to ``None``; pass any other value through."""
    if value is None or value in MISSING_MARKERS:
        return None
    return value


def clean_missing_markers(df: pl.DataFrame, columns: list[str]) -> pl.DataFrame:
    """Normalize missing-value markers to null across ``columns``."""
    exprs = [
        pl.col(column).map_elements(normalize_missing_value, return_dtype=pl.Utf8).alias(column)
        for column in columns
        if column in df.columns
    ]
    if not exprs:
        return df
    return df.with_columns(exprs)
