"""Faker-based synthetic customer generation."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
from faker import Faker

from datagen.identities import CanonicalCustomer
from datagen.rng import seeded_uuid4


def generate_customers(count: int, seed: int) -> list[CanonicalCustomer]:
    """Generate ``count`` unique, deterministic customers for the given seed."""
    faker = Faker()
    faker.seed_instance(seed)
    rng = np.random.default_rng(seed)

    today = date.today()
    seen_emails: set[str] = set()
    customers: list[CanonicalCustomer] = []

    for index in range(1, count + 1):
        first_name = faker.first_name()
        last_name = faker.last_name()
        domain = faker.free_email_domain()
        email = f"{first_name}.{last_name}@{domain}".lower()
        suffix = 1
        while email in seen_emails:
            suffix += 1
            email = f"{first_name}.{last_name}{suffix}@{domain}".lower()
        seen_emails.add(email)

        created_days_ago = int(rng.integers(30, 365 * 3))
        customers.append(
            CanonicalCustomer(
                customer_id=seeded_uuid4(rng),
                sequence_number=index,
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=faker.phone_number(),
                street=faker.street_address(),
                city=faker.city(),
                region=faker.state(),
                postal_code=faker.postcode(),
                country=faker.country(),
                created_at=today - timedelta(days=created_days_ago),
            )
        )

    return customers
