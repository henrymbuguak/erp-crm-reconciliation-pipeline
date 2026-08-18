"""Inject near-duplicate rows into an export.

Real-world duplicate rows are rarely byte-identical (extra whitespace,
case differences, re-keyed entries) so a random subset of columns on each
duplicate row is lightly perturbed rather than copied verbatim.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _perturb_duplicate_row(
    row: pd.Series, rng: np.random.Generator, exclude_columns: frozenset[str]
) -> pd.Series:
    string_columns = [
        c for c in row.index if c not in exclude_columns and isinstance(row[c], str) and row[c]
    ]
    if not string_columns or rng.random() >= 0.5:
        return row
    column = string_columns[int(rng.integers(len(string_columns)))]
    value = row[column]
    row = row.copy()
    row[column] = f" {value} " if rng.random() < 0.5 else value.upper()
    return row


def add_duplicates(
    df: pd.DataFrame,
    ratio: float,
    rng: np.random.Generator,
    exclude_columns: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Append near-duplicates of a random subset of rows, then shuffle row order.

    ``exclude_columns`` should list ID/foreign-key columns that must not be
    perturbed: corrupting a join key would silently orphan the duplicated
    record (e.g. detaching an invoice from its customer) instead of
    producing a realistic, detectable duplicate.
    """
    if ratio <= 0.0 or df.empty:
        return df.reset_index(drop=True)

    num_duplicates = round(len(df) * ratio)
    if num_duplicates == 0:
        return df.reset_index(drop=True)

    excluded = frozenset(exclude_columns)
    duplicate_positions = rng.choice(len(df), size=num_duplicates, replace=False)
    duplicates = df.iloc[duplicate_positions].apply(
        lambda row: _perturb_duplicate_row(row, rng, excluded), axis=1
    )

    combined = pd.concat([df, duplicates], ignore_index=True)
    shuffled_order = rng.permutation(len(combined))
    return combined.iloc[shuffled_order].reset_index(drop=True)
