"""Synthetic data generators.

Each generator builds a list of canonical (:mod:`datagen.identities`)
entities using seeded Faker/mimesis providers plus a seeded
:class:`numpy.random.Generator` for structural decisions (counts, dates,
amounts, and which records should structurally diverge between ERP and CRM).
"""
