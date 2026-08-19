"""Apply structural cross-system mismatches at export time.

Whether a payment amount should legitimately drift between ERP and CRM is
decided during generation (see `datagen.generators.payments`); this
module is where that decision is actually materialized into the ERP export's
amount column, since the CRM export always shows the canonical/true amount.
"""

from __future__ import annotations

import pandas as pd


def apply_amount_drift(df: pd.DataFrame, amount_column: str, drift_column: str) -> pd.DataFrame:
    """Add ``drift_column`` into ``amount_column`` and drop the now-internal drift column."""
    if drift_column not in df.columns:
        return df
    df = df.copy()
    df[amount_column] = df[amount_column] + df[drift_column]
    return df.drop(columns=[drift_column])
