"""Tests for intra-system near-duplicate collapsing."""

from __future__ import annotations

import polars as pl

from pipeline.cleaners.duplicates import collapse_duplicates


def test_collapse_duplicates_merges_whitespace_padded_row() -> None:
    # Mirrors datagen.messiness.duplicates._perturb_duplicate_row's " {value} " padding.
    df = pl.DataFrame(
        {
            "CUST_ID": ["CUST-000001", "CUST-000001", "CUST-000002"],
            "CUST_NAME": ["Alice Smith", " Alice Smith ", "Bob Jones"],
            "CITY": ["Metropolis", "Metropolis", "Gotham"],
        }
    )

    collapsed, logs = collapse_duplicates(df, "CUST_ID")

    assert collapsed.height == 2
    row = collapsed.filter(pl.col("CUST_ID") == "CUST-000001").to_dicts()[0]
    assert row["CUST_NAME"] == "Alice Smith"
    assert len(logs) == 1
    assert logs[0].key_value == "CUST-000001"
    assert logs[0].row_count == 2
    assert logs[0].differing_columns == ["CUST_NAME"]


def test_collapse_duplicates_merges_upper_cased_row() -> None:
    # Mirrors datagen.messiness.duplicates._perturb_duplicate_row's value.upper() perturbation.
    df = pl.DataFrame(
        {
            "INV_NO": ["INV-000001", "INV-000001"],
            "STATUS_CD": ["paid", "PAID"],
        }
    )

    collapsed, logs = collapse_duplicates(df, "INV_NO")

    assert collapsed.height == 1
    assert collapsed.to_dicts()[0]["STATUS_CD"] == "paid"
    assert logs[0].differing_columns == ["STATUS_CD"]


def test_collapse_duplicates_leaves_singleton_rows_untouched() -> None:
    df = pl.DataFrame({"PMT_NO": ["PMT-000001", "PMT-000002"], "AMT": ["10.00", "20.00"]})

    collapsed, logs = collapse_duplicates(df, "PMT_NO")

    assert collapsed.height == 2
    assert logs == []


def test_collapse_duplicates_passes_through_rows_missing_key() -> None:
    df = pl.DataFrame(
        {
            "CUST_ID": ["CUST-000001", None],
            "CUST_NAME": ["Alice Smith", "Orphan Row"],
        }
    )

    collapsed, logs = collapse_duplicates(df, "CUST_ID")

    assert collapsed.height == 2
    assert logs == []
    assert None in collapsed["CUST_ID"].to_list()


def test_collapse_duplicates_groups_crm_dup_suffixed_keys_by_base_key() -> None:
    # Mirrors datagen.exporters.crm_json._dedupe_join_key's "-DUPn" re-keying,
    # applied so nested-JSON duplicates don't collide with their original row.
    df = pl.DataFrame(
        {
            "customerId": ["CUST-000001", "CUST-000001-DUP2", "CUST-000002"],
            "customerName": ["Alice Smith", "ALICE SMITH", "Bob Jones"],
        }
    )

    collapsed, logs = collapse_duplicates(df, "customerId")

    assert collapsed.height == 2
    assert "CUST-000001-DUP2" not in collapsed["customerId"].to_list()
    row = collapsed.filter(pl.col("customerId") == "CUST-000001").to_dicts()[0]
    assert row["customerName"] == "Alice Smith"
    assert len(logs) == 1
    assert logs[0].key_value == "CUST-000001"
    assert logs[0].differing_columns == ["customerName"]
