"""Inject mixed-encoding / mojibake corruption into text columns.

Simulates the classic real-world bug where UTF-8 encoded text is
misinterpreted as a single-byte codepage (e.g. CP-1252/Latin-1), which is a
frequent source of "dirty" data when files are exchanged between systems
that don't agree on encoding.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Map plain ASCII letters to visually similar accented characters so that
# even purely-ASCII synthetic names/addresses produce visible mojibake once
# re-encoded, rather than silently no-op'ing.
_ACCENT_LOOKALIKES = {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú", "n": "ñ", "c": "ç"}


def _corrupt_text(text: str, rng: np.random.Generator) -> str:
    chars = list(text)
    candidate_positions = [idx for idx, ch in enumerate(chars) if ch.lower() in _ACCENT_LOOKALIKES]
    if not candidate_positions:
        return text

    rng.shuffle(candidate_positions)
    num_targets = max(1, len(candidate_positions) // 4)
    for pos in candidate_positions[:num_targets]:
        lower = chars[pos].lower()
        replacement = _ACCENT_LOOKALIKES[lower]
        chars[pos] = replacement.upper() if chars[pos].isupper() else replacement

    accented = "".join(chars)
    try:
        return accented.encode("utf-8").decode("cp1252", errors="replace")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return accented


def corrupt_encoding(
    df: pd.DataFrame, columns: list[str], ratio: float, rng: np.random.Generator
) -> pd.DataFrame:
    """Corrupt a random subset of cells in ``columns`` with mojibake-style encoding artifacts."""
    if ratio <= 0.0:
        return df
    df = df.copy()
    for column in columns:
        if column not in df.columns:
            continue
        mask = rng.random(len(df)) < ratio
        for i in df.index[mask]:
            value = df.at[i, column]
            if not isinstance(value, str) or not value:
                continue
            df.at[i, column] = _corrupt_text(value, rng)
    return df
