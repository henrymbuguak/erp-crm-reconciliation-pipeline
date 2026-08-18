"""Tests for cosmetic messiness injection functions."""

from __future__ import annotations

import numpy as np
import pandas as pd

from datagen.messiness.dates import corrupt_dates
from datagen.messiness.duplicates import add_duplicates
from datagen.messiness.encoding import corrupt_encoding
from datagen.messiness.mismatches import apply_amount_drift
from datagen.messiness.missing import MISSING_MARKERS, inject_missing


def _dates_df(n: int = 200) -> pd.DataFrame:
    from datetime import date, timedelta

    return pd.DataFrame({"DT": [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]})


def test_corrupt_dates_zero_ratio_is_noop() -> None:
    df = _dates_df()
    result = corrupt_dates(df, ["DT"], 0.0, np.random.default_rng(1))
    assert result["DT"].tolist() == df["DT"].tolist()


def test_corrupt_dates_changes_approximately_ratio_fraction() -> None:
    df = _dates_df(500)
    rng = np.random.default_rng(1)
    result = corrupt_dates(df, ["DT"], 0.3, rng)
    changed = sum(1 for a, b in zip(df["DT"], result["DT"], strict=True) if a != b)
    assert 0.2 * len(df) < changed < 0.4 * len(df)


def test_corrupt_dates_is_deterministic() -> None:
    df = _dates_df()
    first = corrupt_dates(df, ["DT"], 0.3, np.random.default_rng(5))
    second = corrupt_dates(df, ["DT"], 0.3, np.random.default_rng(5))
    assert first["DT"].tolist() == second["DT"].tolist()


def test_corrupt_dates_ignores_missing_column() -> None:
    df = _dates_df(10)
    result = corrupt_dates(df, ["NOT_A_COLUMN"], 1.0, np.random.default_rng(1))
    assert result["DT"].tolist() == df["DT"].tolist()


def test_corrupt_encoding_zero_ratio_is_noop() -> None:
    df = pd.DataFrame({"NAME": ["Jose Garcia"] * 50})
    result = corrupt_encoding(df, ["NAME"], 0.0, np.random.default_rng(1))
    assert (result["NAME"] == df["NAME"]).all()


def test_corrupt_encoding_produces_visible_corruption() -> None:
    df = pd.DataFrame({"NAME": ["Jose Garcia"] * 200})
    result = corrupt_encoding(df, ["NAME"], 1.0, np.random.default_rng(1))
    assert (result["NAME"] != df["NAME"]).any()


def test_inject_missing_zero_ratio_is_noop() -> None:
    df = pd.DataFrame({"PHONE": ["555-1234"] * 50})
    result = inject_missing(df, ["PHONE"], 0.0, np.random.default_rng(1))
    assert (result["PHONE"] == df["PHONE"]).all()


def test_inject_missing_uses_known_markers() -> None:
    df = pd.DataFrame({"PHONE": ["555-1234"] * 300})
    result = inject_missing(df, ["PHONE"], 1.0, np.random.default_rng(1))
    # Note: pandas silently coerces an assigned `None` into float NaN even in
    # an object-dtype column, so both are accepted as valid "missing" markers.
    assert all(pd.isna(v) or v in MISSING_MARKERS for v in result["PHONE"])


def test_add_duplicates_zero_ratio_returns_same_length() -> None:
    df = pd.DataFrame({"ID": range(50), "NAME": [f"n{i}" for i in range(50)]})
    result = add_duplicates(df, 0.0, np.random.default_rng(1))
    assert len(result) == len(df)


def test_add_duplicates_adds_expected_row_count() -> None:
    df = pd.DataFrame({"ID": range(100), "NAME": [f"n{i}" for i in range(100)]})
    result = add_duplicates(df, 0.2, np.random.default_rng(1))
    assert len(result) == 120


def test_add_duplicates_excludes_key_columns_from_perturbation() -> None:
    df = pd.DataFrame(
        {"ID": [f"K{i:03d}" for i in range(200)], "NAME": [f"n{i}" for i in range(200)]}
    )
    result = add_duplicates(df, 0.5, np.random.default_rng(1), exclude_columns=("ID",))
    # Every ID in the output must still refer to a real original key.
    assert set(result["ID"]).issubset(set(df["ID"]))


def test_apply_amount_drift_adds_and_drops_column() -> None:
    df = pd.DataFrame({"AMT": [100.0, 200.0], "_DRIFT": [1.5, -2.0]})
    result = apply_amount_drift(df, "AMT", "_DRIFT")
    assert result["AMT"].tolist() == [101.5, 198.0]
    assert "_DRIFT" not in result.columns


def test_apply_amount_drift_missing_column_is_noop() -> None:
    df = pd.DataFrame({"AMT": [100.0]})
    result = apply_amount_drift(df, "AMT", "_DRIFT")
    assert result["AMT"].tolist() == [100.0]
