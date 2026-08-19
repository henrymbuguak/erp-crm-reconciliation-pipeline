"""Cosmetic "messiness" injection, applied per export target.

Each function takes a `pandas.DataFrame` plus a seeded RNG and
returns a *new* DataFrame with a configurable fraction of cells corrupted.
Because ERP and CRM exports each call these functions with independently
spawned RNGs (see `datagen.rng`), the two systems' copies of the same
underlying data diverge realistically instead of being corrupted identically.
"""
