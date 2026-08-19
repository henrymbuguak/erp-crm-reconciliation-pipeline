"""Repair UTF-8-misread-as-CP-1252 mojibake, or flag it as unrecoverable.

`datagen`'s encoding corruption (see `src/datagen/messiness/encoding.py`)
inserts accented characters into otherwise-ASCII text, then encodes it as
UTF-8 and decodes those bytes as CP-1252. Reversing that round trip
(encode as CP-1252, decode as UTF-8) repairs it exactly; running the same
round trip on text that was never corrupted either no-ops (pure ASCII) or
raises (genuinely non-CP-1252-encodable text), so it's a safe repair
attempt to always make.
"""

from __future__ import annotations

import polars as pl

_REPLACEMENT_CHAR = "\ufffd"


def repair_mojibake(text: str) -> str | None:
    """Attempt to reverse CP-1252/UTF-8 mojibake in ``text``.

    Returns the repaired text, the original text unchanged if it wasn't
    mojibake to begin with, or ``None`` if it's unrecoverable (the text
    already contains the Unicode replacement character, or repairing it
    would produce one).
    """
    if _REPLACEMENT_CHAR in text:
        return None
    try:
        repaired = text.encode("cp1252").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text
    return None if _REPLACEMENT_CHAR in repaired else repaired


def clean_encoding_column(df: pl.DataFrame, column: str) -> pl.DataFrame:
    """Repair mojibake in ``column`` in place; add a `{column}_invalid` flag column.

    A row is flagged invalid when its raw value was non-null but the
    mojibake repair was unrecoverable -- the signal a later validation
    stage uses to decide whether to quarantine (see CLAUDE.md's
    "unrecoverable_encoding" reason code).
    """
    if column not in df.columns:
        return df

    repaired_values: list[str | None] = []
    invalid_flags: list[bool] = []
    for raw in df[column].to_list():
        if raw is None:
            repaired_values.append(None)
            invalid_flags.append(False)
            continue
        repaired = repair_mojibake(raw)
        repaired_values.append(raw if repaired is None else repaired)
        invalid_flags.append(repaired is None)

    return df.with_columns(
        pl.Series(column, repaired_values),
        pl.Series(f"{column}_invalid", invalid_flags),
    )
