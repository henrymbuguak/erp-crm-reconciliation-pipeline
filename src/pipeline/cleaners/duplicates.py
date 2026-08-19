"""Collapse intra-system near-duplicate rows, before validation or resolution.

`datagen`'s duplicate injection (see `src/datagen/messiness/duplicates.py`)
never perturbs a duplicated row's ID/foreign-key columns -- only a random
other string column, by whitespace-padding it or upper-casing it. The CRM
JSON exporter is the one exception: since it nests rows into a tree keyed
by that same business key, it re-keys each duplicate with a `-DUPn` suffix
first so it doesn't collide (see `datagen.exporters.crm_json._dedupe_join_key`).
Stripping that suffix before grouping means both the flat ERP CSVs and the
nested CRM JSON collapse the same way. This is a separate, earlier problem
than cross-system entity resolution in `pipeline.resolve`: collapsing here
first means resolution never has to match against duplicated noise.
"""

from __future__ import annotations

import re
from typing import Any

import polars as pl

from pipeline.models import DuplicateMergeLog

_DUP_SUFFIX = re.compile(r"^(.*)-DUP\d+$")


def _base_key(key: str) -> str:
    """Strip datagen's CRM `-DUPn` re-keying suffix, if present."""
    match = _DUP_SUFFIX.match(key)
    return match.group(1) if match else key


def _pick_canonical_value(values: list[Any]) -> Any:
    """Pick the unperturbed value among a group's copies of one column.

    Perturbation is only ever whitespace-padding (`" x "`) or upper-casing
    (`"X"`), so the canonical value is whichever candidate is not padded and,
    failing that, is not the upper-cased one.
    """
    unique = list(dict.fromkeys(values))
    if len(unique) == 1:
        return unique[0]

    string_candidates = [v for v in unique if isinstance(v, str)]
    if len(string_candidates) != len(unique):
        return unique[0]

    stripped = [v for v in string_candidates if v == v.strip()]
    candidates = stripped or string_candidates
    non_upper = [v for v in candidates if v != v.upper()]
    return (non_upper or candidates)[0]


def _merge_group(
    rows: list[dict[str, Any]], key_column: str, base_key: str
) -> tuple[dict[str, Any], list[str]]:
    canonical: dict[str, Any] = {}
    differing_columns: list[str] = []
    for column in rows[0]:
        if column == key_column:
            # Always the true business key, never the CRM `-DUPn` re-keying artifact.
            canonical[column] = base_key
            continue
        values = [row[column] for row in rows]
        if len(set(values)) > 1:
            differing_columns.append(column)
        canonical[column] = _pick_canonical_value(values)
    return canonical, differing_columns


def collapse_duplicates(
    df: pl.DataFrame, key_column: str
) -> tuple[pl.DataFrame, list[DuplicateMergeLog]]:
    """Collapse rows sharing the same ``key_column`` value into one canonical row.

    Rows with a null/missing key are left untouched -- they can't be grouped
    by business key and are handled later as missing-required-field failures.
    """
    if df.is_empty() or key_column not in df.columns:
        return df, []

    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    ungrouped: list[dict[str, Any]] = []

    for row in df.to_dicts():
        raw_key = row.get(key_column)
        if raw_key is None:
            ungrouped.append(row)
            continue
        key = _base_key(raw_key)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)

    merge_logs: list[DuplicateMergeLog] = []
    merged_rows: list[dict[str, Any]] = []
    for key in order:
        group = groups[key]
        if len(group) == 1:
            merged_rows.append(group[0])
            continue
        canonical, differing_columns = _merge_group(group, key_column, key)
        merged_rows.append(canonical)
        merge_logs.append(
            DuplicateMergeLog(
                key_column=key_column,
                key_value=key,
                row_count=len(group),
                differing_columns=differing_columns,
            )
        )

    collapsed = pl.DataFrame(merged_rows + ungrouped, schema=df.schema)
    return collapsed, merge_logs
