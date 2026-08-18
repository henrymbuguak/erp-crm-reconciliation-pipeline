"""Exporters that project canonical entities into system-specific formats.

Each exporter filters out records that shouldn't exist in its system
(per :attr:`~datagen.identities.CanonicalInvoice.exists_in_erp` /
``exists_in_crm``), renders system-specific field names/formats, and layers
on cosmetic messiness independently of the other system's export.
"""
