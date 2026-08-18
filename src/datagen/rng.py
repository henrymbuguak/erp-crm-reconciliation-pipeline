"""Seeded random-number-generator utilities.

To keep dataset generation fully reproducible while still letting each
component (customers, invoices, payments, per-system messiness, ...) draw
independent random streams, we derive child generators from a single master
seed via :class:`numpy.random.SeedSequence`. This avoids the common pitfall
of reusing one global RNG (which makes output order-sensitive) while still
guaranteeing that a given master seed always reproduces the same dataset.
"""

from __future__ import annotations

from uuid import UUID

import numpy as np


def spawn_rngs(master_seed: int, names: list[str]) -> dict[str, np.random.Generator]:
    """Create one independent, reproducible RNG per name from a master seed."""
    seed_sequence = np.random.SeedSequence(master_seed)
    children = seed_sequence.spawn(len(names))
    return {name: np.random.default_rng(child) for name, child in zip(names, children, strict=True)}


def seeded_uuid4(rng: np.random.Generator) -> UUID:
    """Draw a random-looking UUID (version 4 bit layout) from a seeded RNG.

    Using ``uuid.uuid4()`` directly would draw from OS randomness and break
    reproducibility; this instead derives the 128 bits from the caller's
    seeded generator so that a given master seed always yields identical
    entity IDs.
    """
    raw = bytearray(rng.bytes(16))
    raw[6] = (raw[6] & 0x0F) | 0x40  # version 4
    raw[8] = (raw[8] & 0x3F) | 0x80  # variant 10xx
    return UUID(bytes=bytes(raw))
