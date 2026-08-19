"""Ingestion, cleaning, entity resolution, and reconciliation pipeline.

Consumes the ERP CSV and CRM JSON exports produced by `datagen` (see
`src/datagen/**`, which is read-only reference material for this package)
and reconciles them into a canonical, deduplicated dataset plus a
reconciliation report. See `CLAUDE.md` at the repo root for the governing
design rules.
"""

from __future__ import annotations
