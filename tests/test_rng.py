"""Tests for seeded RNG utilities."""

from __future__ import annotations

from uuid import UUID

import numpy as np

from datagen.rng import seeded_uuid4, spawn_rngs


def test_spawn_rngs_is_deterministic() -> None:
    first = spawn_rngs(42, ["a", "b"])
    second = spawn_rngs(42, ["a", "b"])
    assert first["a"].random() == second["a"].random()
    assert first["b"].random() == second["b"].random()


def test_spawn_rngs_are_independent_streams() -> None:
    rngs = spawn_rngs(42, ["a", "b"])
    assert rngs["a"].random() != rngs["b"].random()


def test_seeded_uuid4_is_deterministic_and_valid() -> None:
    rng1 = np.random.default_rng(123)
    rng2 = np.random.default_rng(123)
    uuid1 = seeded_uuid4(rng1)
    uuid2 = seeded_uuid4(rng2)

    assert uuid1 == uuid2
    assert isinstance(uuid1, UUID)
    assert uuid1.version == 4


def test_seeded_uuid4_produces_unique_values() -> None:
    rng = np.random.default_rng(1)
    values = {seeded_uuid4(rng) for _ in range(1000)}
    assert len(values) == 1000
