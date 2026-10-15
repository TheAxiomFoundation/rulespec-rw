"""Encoding-manifest state recorded on 2026-10-14.

KNOWN_STALE_ATTESTATIONS lists manifest claims that were already stale. Each
entry is one claim in one manifest under .axiom/encoding-manifests/: the
file it attests, the sha256 the manifest records for that file, the sha256
the file had on 2026-10-14, the sha256 of the manifest file itself, and the
commits that changed the file after it was attested.

This repository had no encoding manifests on 2026-10-14, so nothing is
listed. The list stays empty: any manifest added later must match its files.

KNOWN_UNMANIFESTED_MODULES lists the RuleSpec modules that had no encoding
manifest on 2026-10-14. Any other module without one fails.

Both lists are closed. Every entry must carry a digest in
test_encoding_manifests.py's ADOPTED_LIST_SHA256, so the lists cannot gain
an entry that was not recorded on 2026-10-14; a removed entry could be put
back later, and only review catches that. The test fails if a listed file
changes again, if a listed manifest is edited, removed or retired other than
by an encoder replacement, or if a module loses its manifest. It warns when
an entry resolves, for example once the supervised encoder replaces a
module's manifest; delete the entry then. New drift is fixed through the
encoder, not listed.
"""

from __future__ import annotations

from typing import NamedTuple


class StaleAttestation(NamedTuple):
    manifest: str
    manifest_sha256: str
    path: str
    attested_sha256: str
    current_sha256: str
    changed_by: tuple[str, ...]
    change: str


KNOWN_STALE_ATTESTATIONS: tuple[StaleAttestation, ...] = ()

KNOWN_UNMANIFESTED_MODULES: tuple[str, ...] = (
    "rw/policies/loda-vup/direct-support-amounts.yaml",
    "rw/regulations/mo-2026-002-26-10-tc/cbhi-member-premiums.yaml",
    "rw/regulations/pmo-2020-105-03/cbhi-employee-contribution.yaml",
    "rw/regulations/po-2024-086-01/pension-contribution-rate.yaml",
    "rw/statutes/composed/pilot-worker-disposable-income-pipeline.yaml",
    "rw/statutes/law-2001-24/rama-contributions.yaml",
    "rw/statutes/law-2005-23/mmi-contributions.yaml",
    "rw/statutes/law-2015-03/community-based-health-insurance.yaml",
    "rw/statutes/law-2016-003/maternity-leave-contributions.yaml",
    "rw/statutes/law-2022-027/employment-income-tax.yaml",
    "rw/statutes/law-2022-027/lump-sum-regime.yaml",
    "rw/statutes/law-2023-048/rental-income-tax.yaml",
    "rw/statutes/law-2023-049/value-added-tax.yaml",
    "rw/statutes/law-2025-011/excise-duty.yaml",
)
