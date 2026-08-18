"""Inject inconsistent or invalid date formatting into date columns."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

_INVALID_PLACEHOLDERS = ("0000-00-00", "N/A", "", "TBD")


def _format_variants(value: date) -> list[str]:
    return [
        value.strftime("%m/%d/%Y"),
        value.strftime("%d-%m-%Y"),
        value.strftime("%d %b %Y"),
        value.strftime("%Y/%m/%d"),
        str(int(datetime(value.year, value.month, value.day).timestamp())),
        *_INVALID_PLACEHOLDERS,
    ]


def _corrupt_date_value(value: Any, rng: np.random.Generator) -> date | datetime | str:
    parsed: date
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return value
    else:
        return str(value)

    variants = _format_variants(parsed)
    return variants[int(rng.integers(len(variants)))]


def corrupt_dates(
    df: pd.DataFrame, columns: list[str], ratio: float, rng: np.random.Generator
) -> pd.DataFrame:
    """Rewrite a random subset of cells in ``columns`` to an inconsistent or invalid date format."""
    if ratio <= 0.0:
        return df
    df = df.copy()
    for column in columns:
        if column not in df.columns:
            continue
        mask = rng.random(len(df)) < ratio
        for i in df.index[mask]:
            original = df.at[i, column]
            if pd.isna(original):
                continue
            df.at[i, column] = _corrupt_date_value(original, rng)
    return df
