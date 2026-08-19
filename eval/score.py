"""Score a pipeline run's crosswalk against `ground_truth.json`.

This is the ONLY module allowed to read `ground_truth.json` -- per
CLAUDE.md's hard constraint, no module under `src/pipeline/` may import,
read, or reference it. This script runs the pipeline itself (via
`pipeline.orchestrate.run_pipeline`) and scores the resulting crosswalk
after the fact; the pipeline never consults the answer key at runtime.

`ground_truth.json` only covers invoices and payments -- customers have no
`exists_in_erp`/`exists_in_crm` split in the generator, so there's nothing
to score customer resolution against.

Usage::

    uv run python eval/score.py path/to/data_dir
    uv run python eval/score.py path/to/data_dir --threshold 0.8

The `--threshold` flag sweeps `resolve_customers`' confidence threshold for
offline calibration (see `pipeline.resolve.CUSTOMER_MATCH_THRESHOLD`'s
docstring) -- it does not read `ground_truth.json` any differently, it just
re-runs the pipeline with a different threshold before scoring.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pipeline.models import CrosswalkEntry, EntityType
from pipeline.orchestrate import run_pipeline
from pipeline.report import PrecisionRecall

# Ground-truth entries are tagged with their entity type before being
# combined, so an invoice's business key can never collide with a payment's.
_GroundTruthPair = tuple[EntityType, str, str]


def load_ground_truth(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return result


def _ground_truth_pairs(
    entity_type: EntityType, entries: list[dict[str, Any]]
) -> set[_GroundTruthPair]:
    return {
        (entity_type, entry["erp_key"], entry["crm_key"])
        for entry in entries
        if entry["expected_match"]
    }


def _predicted_pairs(
    crosswalk: list[CrosswalkEntry], entity_type: EntityType
) -> set[_GroundTruthPair]:
    return {
        (entity_type, entry.erp_key, entry.crm_key)
        for entry in crosswalk
        if entry.entity_type == entity_type
        and entry.erp_key is not None
        and entry.crm_key is not None
    }


def _precision_recall(
    predicted: set[_GroundTruthPair], expected: set[_GroundTruthPair]
) -> PrecisionRecall:
    true_positives = predicted & expected
    precision = len(true_positives) / len(predicted) if predicted else 0.0
    recall = len(true_positives) / len(expected) if expected else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return PrecisionRecall(precision=precision, recall=recall, f1=f1)


def score_invoices(
    crosswalk: list[CrosswalkEntry], ground_truth: dict[str, Any]
) -> PrecisionRecall:
    expected = _ground_truth_pairs(EntityType.INVOICE, ground_truth["invoices"])
    predicted = _predicted_pairs(crosswalk, EntityType.INVOICE)
    return _precision_recall(predicted, expected)


def score_payments(
    crosswalk: list[CrosswalkEntry], ground_truth: dict[str, Any]
) -> PrecisionRecall:
    expected = _ground_truth_pairs(EntityType.PAYMENT, ground_truth["payments"])
    predicted = _predicted_pairs(crosswalk, EntityType.PAYMENT)
    return _precision_recall(predicted, expected)


def score_crosswalk(
    crosswalk: list[CrosswalkEntry], ground_truth: dict[str, Any]
) -> PrecisionRecall:
    """Combined precision/recall across invoices and payments (all `ground_truth.json` covers)."""
    expected = _ground_truth_pairs(
        EntityType.INVOICE, ground_truth["invoices"]
    ) | _ground_truth_pairs(EntityType.PAYMENT, ground_truth["payments"])
    predicted = _predicted_pairs(crosswalk, EntityType.INVOICE) | _predicted_pairs(
        crosswalk, EntityType.PAYMENT
    )
    return _precision_recall(predicted, expected)


def _format(label: str, result: PrecisionRecall) -> str:
    return f"{label:<10} precision={result.precision:.1%}  recall={result.recall:.1%}  f1={result.f1:.1%}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "data_dir", type=Path, help="Directory containing ground_truth.json + erp/crm exports"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Override the customer fuzzy-match confidence threshold for this run",
    )
    args = parser.parse_args()

    ground_truth = load_ground_truth(args.data_dir / "ground_truth.json")
    if args.threshold is None:
        result = run_pipeline(args.data_dir)
    else:
        result = run_pipeline(args.data_dir, customer_match_threshold=args.threshold)

    print(_format("invoices", score_invoices(result.crosswalk, ground_truth)))
    print(_format("payments", score_payments(result.crosswalk, ground_truth)))
    print(_format("combined", score_crosswalk(result.crosswalk, ground_truth)))


if __name__ == "__main__":
    main()
