"""Parse messy date strings to ISO-8601, or flag them as unparseable.

`datagen`'s date corruption (see `src/datagen/messiness/dates.py`) rewrites
a clean ISO date into one of a fixed set of alternate formats, a Unix
timestamp, or a known invalid placeholder (``"0000-00-00"``, ``"TBD"``,
etc.). Trying every one of those formats -- not just a summarized subset --
before giving up is what makes this "cleaning" rather than a validation gate;
see CLAUDE.md's "Cleaning vs. quarantine" rule.

Assumes generic missing-value markers (see `pipeline.cleaners.missing`) have
already been normalized to null: a null input here means "legitimately
absent", not "invalid" -- only a non-null value that fails every format is
flagged as invalid.
"""

from __future__ import annotations

from datetime import date, datetime

import polars as pl

# Mirrors the alternate formats datagen.messiness.dates._format_variants can
# produce (ISO is tried first via date.fromisoformat).
_ALTERNATE_FORMATS = ("%m/%d/%Y", "%d-%m-%Y", "%d %b %Y", "%Y/%m/%d")


def parse_date(value: str) -> date | None:
    """Parse a single date string, trying every format the generator can produce.

    Returns ``None`` for an unparseable string, including known invalid
    placeholders like ``"0000-00-00"`` or ``"TBD"`` (neither matches any
    known format, so no special-casing is needed for them).
    """
    value = value.strip()
    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        pass

    for fmt in _ALTERNATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    if value.isdigit():
        try:
            # datagen builds this via datetime(y, m, d).timestamp(), which
            # interprets the naive datetime as local time -- decode the same
            # way (naive/local) so the round trip lands on the same calendar
            # day regardless of which local timezone either side runs in.
            return datetime.fromtimestamp(int(value)).date()
        except (OSError, OverflowError, ValueError):
            return None

    return None


def clean_date_column(df: pl.DataFrame, column: str) -> pl.DataFrame:
    """Parse ``column`` to ISO-8601 strings in place; add a `{column}_invalid` flag column.

    A row is flagged invalid when its raw value was non-null but failed to
    parse under any known format -- that's the signal a later validation
    stage uses to decide whether to quarantine (see CLAUDE.md's
    "unparseable_date" reason code).
    """
    if column not in df.columns:
        return df

    parsed_values: list[str | None] = []
    invalid_flags: list[bool] = []
    for raw in df[column].to_list():
        if raw is None:
            parsed_values.append(None)
            invalid_flags.append(False)
            continue
        parsed = parse_date(raw)
        parsed_values.append(parsed.isoformat() if parsed is not None else None)
        invalid_flags.append(parsed is None)

    return df.with_columns(
        pl.Series(column, parsed_values),
        pl.Series(f"{column}_invalid", invalid_flags),
    )
