"""Inject missing/null-like values into otherwise-populated columns."""

from __future__ import annotations

import numpy as np
import pandas as pd

# A realistic mix of how "missing" shows up across real-world exports:
# a true null, an empty string, and common sentinel/placeholder text.
MISSING_MARKERS: tuple[str | None, ...] = (None, "", "N/A", "NULL", "--", "unknown")


def inject_missing(
    df: pd.DataFrame, columns: list[str], ratio: float, rng: np.random.Generator
) -> pd.DataFrame:
    """Replace a random subset of cells in ``columns`` with a missing-value marker."""
    if ratio <= 0.0:
        return df
    df = df.copy()
    for column in columns:
        if column not in df.columns:
            continue
        mask = rng.random(len(df)) < ratio
        for i in df.index[mask]:
            marker = MISSING_MARKERS[int(rng.integers(len(MISSING_MARKERS)))]
            df.at[i, column] = marker
    return df
