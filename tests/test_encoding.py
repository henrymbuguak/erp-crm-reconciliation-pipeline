"""Tests for mojibake repair, grounded in datagen's actual corruption mechanics."""

from __future__ import annotations

import numpy as np
import polars as pl

from datagen.messiness.encoding import _corrupt_text
from pipeline.cleaners.encoding import clean_encoding_column, repair_mojibake


def test_repair_mojibake_is_the_exact_inverse_of_datagen_corruption() -> None:
    rng = np.random.default_rng(42)
    corrupted = _corrupt_text("Renee Garcia", rng)
    assert corrupted != "Renee Garcia"  # sanity: corruption actually happened

    repaired = repair_mojibake(corrupted)

    assert repaired is not None
    # Re-applying datagen's own forward corruption to our repair must
    # reproduce the exact corrupted string -- proof repair is a true inverse.
    assert repaired.encode("utf-8").decode("cp1252") == corrupted


def test_repair_mojibake_leaves_uncorrupted_ascii_text_unchanged() -> None:
    assert repair_mojibake("Bob Jones") == "Bob Jones"


def test_repair_mojibake_is_unrecoverable_when_replacement_char_present() -> None:
    assert repair_mojibake("Already \ufffd corrupted") is None


def test_clean_encoding_column_flags_unrecoverable_rows() -> None:
    rng = np.random.default_rng(42)
    corrupted = _corrupt_text("Renee Garcia", rng)
    df = pl.DataFrame(
        {
            "CUST_NAME": [corrupted, "Bob Jones", "Already \ufffd corrupted", None],
        }
    )

    cleaned = clean_encoding_column(df, "CUST_NAME")

    values = cleaned["CUST_NAME"].to_list()
    assert values[0] == repair_mojibake(corrupted)
    assert values[1] == "Bob Jones"
    # left as-is; flagged invalid instead
    assert values[2] == "Already \ufffd corrupted"
    assert values[3] is None
    assert cleaned["CUST_NAME_invalid"].to_list() == [False, False, True, False]
