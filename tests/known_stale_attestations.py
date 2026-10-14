"""Encoding-manifest claims that were already stale on 2026-10-14.

Each entry is one claim in one manifest under .axiom/encoding-manifests/:
the file it attests, the sha256 the manifest records for that file, the
sha256 the file had on 2026-10-14, the sha256 of the manifest file itself,
and the commits that changed the file after it was attested.

This repository had no encoding manifests on 2026-10-14, so nothing is
listed. The list stays empty: any manifest added later must match its files.

The list is closed and may only shrink. test_encoding_manifests.py fails if
a listed file changes again or a listed manifest is edited while it stays a
manual attestation. It reports an entry as resolved once the supervised
encoder replaces the module's manifest; delete the entry then. Do not add
entries: new drift fails CI and is fixed through the encoder.
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


#: Number of entries when the list was adopted. The list may only shrink.
ADOPTED_COUNT = 0

KNOWN_STALE_ATTESTATIONS: tuple[StaleAttestation, ...] = ()
