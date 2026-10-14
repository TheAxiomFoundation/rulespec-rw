"""Manifest-sync guard: attested RuleSpec files must keep their recorded bytes.

Each manifest under ``.axiom/encoding-manifests/`` lists, in
``applied_files``, the sha256 of every file it attests. The shared
validator's generated-RuleSpec guard checks only the files a pull request
changes, so a file edited while that guard was off keeps a manifest that no
longer matches it, and nothing reads that manifest again. These tests read
every manifest on every run and fail when an attested RuleSpec module or
companion test no longer has the bytes its manifest records. rulespec-us and
rulespec-dk carry the same check.

Claims that were already stale when this test was added are listed, by exact
bytes, in ``known_stale_attestations.py``. That list records the drift; it
does not attest the files.

This file is also the retired-manifest inventory that axiom-encode's
replacement path reconciles. ``KNOWN_RETIRED_SCHEMA_MANIFESTS`` must stay a
single top-level annotated frozenset assignment with one entry per line, and
no real manifest path may appear anywhere else in this file. The fixtures
below use the unused jurisdiction ``zz``.
"""

from __future__ import annotations

import hashlib
import json
import re
import warnings
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import pytest
from known_stale_attestations import (
    ADOPTED_COUNT,
    KNOWN_STALE_ATTESTATIONS,
    StaleAttestation,
)
from test_repository_layout import (
    CONTENT_DIRS,
    JURISDICTION_DIR_RE,
    ROOT,
    iter_rulespec_files,
    jurisdiction_dirs,
)

MANIFEST_DIR = PurePosixPath(".axiom/encoding-manifests")
MANUAL_ATTESTATION_SCHEMA = "axiom-encode/applied-rulespec/v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

#: Manifests whose primary module was retired without a replacement.
#: Empty: every manifest here attests at least one live file.
KNOWN_RETIRED_SCHEMA_MANIFESTS: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Claim:
    """One ``applied_files`` entry: a manifest's statement about one file."""

    manifest: str
    path: str
    sha256: str | None
    deleted: bool


@dataclass(frozen=True)
class SyncResult:
    failures: tuple[str, ...]
    known: tuple[StaleAttestation, ...]
    resolved: tuple[StaleAttestation, ...]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    keys = [key for key, _ in pairs]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise ValueError(f"duplicate keys {duplicates}")
    return dict(pairs)


def _load_manifest(path: Path) -> dict:
    payload = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
    )
    if not isinstance(payload, dict):
        raise ValueError("not a JSON object")
    return payload


def is_plain_relative_path(path: str) -> bool:
    pure = PurePosixPath(path)
    return (
        bool(path)
        and "\\" not in path
        and not pure.is_absolute()
        and all(part not in {"", ".", ".."} for part in path.split("/"))
    )


def is_synced_path(path: str) -> bool:
    """True for a RuleSpec module or companion test under a content root.

    Assembled program specs (``programs/`` at the root or under a
    jurisdiction) and root metadata a manifest may record as applied-time
    evidence are out of scope, as in rulespec-us: no tool re-attests an edited
    program spec, and reviewed metadata updates are not edits to rules.
    """
    parts = PurePosixPath(path).parts
    return (
        len(parts) >= 3
        and JURISDICTION_DIR_RE.match(parts[0]) is not None
        and parts[1] in CONTENT_DIRS
        and parts[-1].endswith(".yaml")
    )


def manifest_claims(root: Path) -> tuple[list[Claim], list[str]]:
    """Every claim in every manifest, and every structural problem found.

    Fails closed on shape: a manifest that is not a regular JSON object with a
    non-empty ``applied_files`` list of well-formed entries is a problem, not
    something to skip.
    """
    claims: list[Claim] = []
    problems: list[str] = []
    manifest_dir = root / MANIFEST_DIR
    if manifest_dir.is_symlink():
        return [], [f"{MANIFEST_DIR}: manifest directory is a symlink"]
    if not manifest_dir.is_dir():
        return [], []
    for manifest_path in sorted(manifest_dir.rglob("*")):
        rel = manifest_path.relative_to(root).as_posix()
        if manifest_path.is_symlink():
            problems.append(f"{rel}: manifest path is a symlink")
            continue
        if manifest_path.is_dir():
            continue
        if manifest_path.suffix != ".json":
            problems.append(f"{rel}: not a .json manifest")
            continue
        try:
            payload = _load_manifest(manifest_path)
        except (UnicodeDecodeError, ValueError) as exc:
            problems.append(f"{rel}: unreadable manifest ({exc})")
            continue
        applied = payload.get("applied_files")
        if not isinstance(applied, list) or not applied:
            problems.append(f"{rel}: applied_files is missing, empty or not a list")
            continue
        seen: set[str] = set()
        for index, entry in enumerate(applied):
            where = f"{rel}: applied_files[{index}]"
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                problems.append(f"{where} has no string path")
                continue
            path = entry["path"]
            if not is_plain_relative_path(path):
                problems.append(f"{where} path {path!r} is not a plain relative path")
                continue
            if path in seen:
                problems.append(f"{where} repeats {path}")
                continue
            seen.add(path)
            if entry.get("deleted") is True and set(entry) == {"path", "deleted"}:
                claims.append(Claim(rel, path, None, True))
            elif (
                set(entry) == {"path", "sha256"}
                and isinstance(entry["sha256"], str)
                and SHA256_RE.match(entry["sha256"])
            ):
                claims.append(Claim(rel, path, entry["sha256"], False))
            else:
                problems.append(
                    f"{where} must be {{path, sha256}} with a lowercase hex digest "
                    "or {path, deleted: true}"
                )
    return claims, problems


def check_sync(
    root: Path,
    claims: list[Claim],
    baseline: tuple[StaleAttestation, ...],
    retired: frozenset[str] = frozenset(),
) -> SyncResult:
    """Compare every synced claim with the file it names.

    A stale claim passes only when ``baseline`` lists exactly that manifest,
    file, recorded hash and current hash, and the manifest file is unchanged
    since it was listed. A listed manifest that was edited but is still a
    manual attestation fails (no sanctioned tool writes those any more); one
    the encoder replaced is reported as resolved.
    """
    by_claim = {
        (entry.manifest, entry.path, entry.attested_sha256): entry for entry in baseline
    }
    failures: list[str] = []
    known: list[StaleAttestation] = []
    listed: set[tuple[str, str, str | None]] = set()
    for claim in claims:
        if claim.manifest in retired or not is_synced_path(claim.path):
            continue
        target = root / claim.path
        if claim.deleted:
            if target.exists() or target.is_symlink():
                failures.append(
                    f"{claim.path}: {claim.manifest} records a deletion, but the file exists"
                )
            continue
        if target.is_symlink() or not target.is_file():
            failures.append(
                f"{claim.path}: attested by {claim.manifest}, but missing or not a regular file"
            )
            continue
        current = _sha256(target)
        if current == claim.sha256:
            continue
        key = (claim.manifest, claim.path, claim.sha256)
        entry = by_claim.get(key)
        if entry is None:
            failures.append(
                f"{claim.path}: sha256 {current} does not match {claim.sha256} "
                f"recorded in {claim.manifest}. Re-encode it through the "
                "supervised encoder; do not edit the manifest."
            )
            continue
        listed.add(key)
        manifest_sha256 = _sha256(root / claim.manifest)
        if manifest_sha256 != entry.manifest_sha256:
            failures.append(
                f"{claim.manifest}: listed as a stale manual attestation, but its "
                "bytes changed while it still records the stale claim."
            )
        elif current != entry.current_sha256:
            failures.append(
                f"{claim.path}: changed again after it was listed as stale "
                f"(listed {entry.current_sha256}, now {current})."
            )
        else:
            known.append(entry)
    resolved: list[StaleAttestation] = []
    for entry in baseline:
        if (entry.manifest, entry.path, entry.attested_sha256) in listed:
            continue
        manifest = root / entry.manifest
        if (
            manifest.is_file()
            and not manifest.is_symlink()
            and _sha256(manifest) != entry.manifest_sha256
        ):
            try:
                schema = _load_manifest(manifest).get("schema_version")
            except (UnicodeDecodeError, ValueError):
                schema = None
            if schema == MANUAL_ATTESTATION_SCHEMA:
                failures.append(
                    f"{entry.manifest}: a listed manual attestation was edited. "
                    "No sanctioned tool writes manual attestations; replace the "
                    "module through the supervised encoder."
                )
                continue
        # The encoder replaced or removed the manifest, or the file matches its
        # unchanged manifest again.
        resolved.append(entry)
    return SyncResult(tuple(failures), tuple(known), tuple(resolved))


# --------------------------------------------------------------------------
# The repository's own manifests.


def test_manifests_are_well_formed() -> None:
    _claims, problems = manifest_claims(ROOT)
    assert problems == [], "\n".join(problems)


def test_attested_files_match_their_manifests() -> None:
    claims, _problems = manifest_claims(ROOT)
    result = check_sync(
        ROOT, claims, KNOWN_STALE_ATTESTATIONS, KNOWN_RETIRED_SCHEMA_MANIFESTS
    )
    assert result.failures == (), "\n".join(result.failures)


def test_resolved_stale_entries_are_reported() -> None:
    claims, _problems = manifest_claims(ROOT)
    result = check_sync(
        ROOT, claims, KNOWN_STALE_ATTESTATIONS, KNOWN_RETIRED_SCHEMA_MANIFESTS
    )
    for entry in result.resolved:
        warnings.warn(
            f"{entry.path} is no longer a stale claim of {entry.manifest}; "
            "delete its entry from tests/known_stale_attestations.py",
            stacklevel=1,
        )


def test_known_stale_list_is_closed() -> None:
    keys = [(e.manifest, e.path, e.attested_sha256) for e in KNOWN_STALE_ATTESTATIONS]
    assert len(keys) == len(set(keys)), "duplicate entries"
    assert len(KNOWN_STALE_ATTESTATIONS) <= ADOPTED_COUNT, (
        "known_stale_attestations.py may only shrink; new drift is fixed through "
        "the supervised encoder, not listed"
    )
    for entry in KNOWN_STALE_ATTESTATIONS:
        assert entry.manifest.startswith(f"{MANIFEST_DIR}/"), entry
        assert is_synced_path(entry.path), entry
        for digest in (
            entry.manifest_sha256,
            entry.attested_sha256,
            entry.current_sha256,
        ):
            assert SHA256_RE.match(digest), entry
        assert entry.attested_sha256 != entry.current_sha256, entry
        assert entry.changed_by and all(COMMIT_RE.match(c) for c in entry.changed_by), (
            entry
        )
        assert entry.change, entry


def test_retired_inventory_entries_are_real() -> None:
    for rel in sorted(KNOWN_RETIRED_SCHEMA_MANIFESTS):
        assert (ROOT / rel).is_file(), f"inventory names a missing manifest: {rel}"


def test_no_unknown_orphaned_manifests() -> None:
    """A manifest whose attested modules all vanished must be inventoried."""
    claims, _problems = manifest_claims(ROOT)
    primaries: dict[str, list[str]] = {}
    for claim in claims:
        if is_synced_path(claim.path) and not claim.path.endswith(".test.yaml"):
            if not claim.deleted:
                primaries.setdefault(claim.manifest, []).append(claim.path)
    orphaned = sorted(
        manifest
        for manifest, paths in primaries.items()
        if not any((ROOT / path).is_file() for path in paths)
        and manifest not in KNOWN_RETIRED_SCHEMA_MANIFESTS
    )
    assert orphaned == [], (
        "manifests whose modules were retired without an inventory entry:\n"
        + "\n".join(orphaned)
    )


def test_no_jurisdiction_manifest_trees() -> None:
    """This test reads only the root manifest tree; no other layout may exist."""
    trees = [
        (directory / ".axiom" / "encoding-manifests").relative_to(ROOT).as_posix()
        for directory in jurisdiction_dirs()
        if (directory / ".axiom" / "encoding-manifests").exists()
    ]
    assert trees == [], f"manifest trees outside {MANIFEST_DIR}: {trees}"


def test_unmanifested_modules_are_reported_not_failed() -> None:
    claims, _problems = manifest_claims(ROOT)
    attested = {claim.path for claim in claims if not claim.deleted}
    unmanifested = [
        path.relative_to(ROOT).as_posix()
        for path in iter_rulespec_files()
        if path.relative_to(ROOT).as_posix() not in attested
    ]
    # A module with no manifest is a provenance gap, not drift; the guard
    # rejects any change to it that does not arrive with an encoder manifest.
    if unmanifested:
        warnings.warn(
            f"{len(unmanifested)} RuleSpec modules have no encoding manifest "
            f"(e.g. {unmanifested[0]})",
            stacklevel=1,
        )


# --------------------------------------------------------------------------
# The check itself, on fixture repositories. Paths use the unused
# jurisdiction ``zz`` so no real manifest path appears in this file.

MODULE = "zz/statutes/example/section-1.yaml"
COMPANION = "zz/statutes/example/section-1.test.yaml"
MANIFEST = f"{MANIFEST_DIR}/zz/statutes/example/section-1.json"
ORIGINAL = b"format: rulespec/v1\nrules:\n  - name: rate\n"
EDITED = b"format: rulespec/v1\nrules:\n  - name: rate  # edited\n"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_manifest(root: Path, files: dict[str, bytes], **fields: object) -> None:
    payload = {
        "applied_files": [
            {"path": path, "sha256": _digest(data)} for path, data in files.items()
        ],
        "schema_version": MANUAL_ATTESTATION_SCHEMA,
        "runner": "manual-attestation",
        **fields,
    }
    target = root / MANIFEST
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n")


def _repo(tmp_path: Path, module: bytes = ORIGINAL) -> Path:
    (tmp_path / MODULE).parent.mkdir(parents=True)
    (tmp_path / MODULE).write_bytes(module)
    (tmp_path / COMPANION).write_bytes(b"- name: case\n")
    _write_manifest(tmp_path, {MODULE: ORIGINAL, COMPANION: b"- name: case\n"})
    return tmp_path


def _sync(root: Path, baseline: tuple[StaleAttestation, ...] = ()) -> SyncResult:
    claims, problems = manifest_claims(root)
    assert problems == []
    return check_sync(root, claims, baseline)


def _listed(root: Path, current: bytes = EDITED) -> StaleAttestation:
    return StaleAttestation(
        manifest=MANIFEST,
        manifest_sha256=_digest((root / MANIFEST).read_bytes()),
        path=MODULE,
        attested_sha256=_digest(ORIGINAL),
        current_sha256=_digest(current),
        changed_by=("0" * 40,),
        change="fixture",
    )


def test_fixture_in_sync_passes(tmp_path: Path) -> None:
    assert _sync(_repo(tmp_path)) == SyncResult((), (), ())


def test_every_single_byte_change_is_detected(tmp_path: Path) -> None:
    """Exhaustive over one-byte edits: every flip, deletion and insertion fails."""
    root = _repo(tmp_path)
    variants = []
    for index in range(len(ORIGINAL)):
        flipped = bytearray(ORIGINAL)
        flipped[index] ^= 0x01
        variants.append(bytes(flipped))
        variants.append(ORIGINAL[:index] + ORIGINAL[index + 1 :])
        variants.append(ORIGINAL[:index] + b" " + ORIGINAL[index:])
    variants.append(ORIGINAL + b"\n")
    for variant in variants:
        (root / MODULE).write_bytes(variant)
        assert len(_sync(root).failures) == 1, variant
    (root / MODULE).write_bytes(ORIGINAL)
    assert _sync(root).failures == ()


def test_companion_test_drift_is_detected(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / COMPANION).write_bytes(b"- name: changed\n")
    (failure,) = _sync(root).failures
    assert failure.startswith(COMPANION)


def test_missing_attested_file_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / MODULE).unlink()
    assert len(_sync(root).failures) == 1


def test_symlinked_attested_file_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / MODULE).unlink()
    (tmp_path / "elsewhere.yaml").write_bytes(ORIGINAL)
    (root / MODULE).symlink_to(tmp_path / "elsewhere.yaml")
    assert len(_sync(root).failures) == 1


def test_deletion_entry_requires_absence(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    payload = json.loads((root / MANIFEST).read_text())
    payload["applied_files"].append(
        {"path": "zz/statutes/example/gone.yaml", "deleted": True}
    )
    (root / MANIFEST).write_text(json.dumps(payload))
    assert _sync(root).failures == ()
    (root / "zz/statutes/example/gone.yaml").write_bytes(b"back\n")
    assert len(_sync(root).failures) == 1


def test_listed_stale_claim_passes_only_with_its_exact_bytes(tmp_path: Path) -> None:
    root = _repo(tmp_path, module=EDITED)
    entry = _listed(root)
    result = _sync(root, (entry,))
    assert result.failures == () and result.known == (entry,) and result.resolved == ()
    # Editing the file again fails.
    (root / MODULE).write_bytes(EDITED + b"# again\n")
    assert len(_sync(root, (entry,)).failures) == 1
    # A listing for different bytes, another manifest or another attested hash
    # does not cover the claim.
    (root / MODULE).write_bytes(EDITED)
    for wrong in (
        entry._replace(current_sha256=_digest(b"other")),
        entry._replace(manifest=f"{MANIFEST_DIR}/zz/statutes/example/other.json"),
        entry._replace(attested_sha256=_digest(b"other")),
    ):
        assert len(_sync(root, (wrong,)).failures) == 1, wrong


def test_hand_edited_manual_attestation_fails(tmp_path: Path) -> None:
    """Rewriting a listed v1 manifest to bless the current bytes is caught."""
    root = _repo(tmp_path, module=EDITED)
    entry = _listed(root)
    _write_manifest(root, {MODULE: EDITED, COMPANION: b"- name: case\n"})
    (failure,) = _sync(root, (entry,)).failures
    assert "manual attestation was edited" in failure
    # So is any other edit to the listed manifest that keeps the stale claim.
    _write_manifest(root, {MODULE: ORIGINAL, COMPANION: b"- name: case\n"}, note="x")
    (failure,) = _sync(root, (entry,)).failures
    assert "bytes changed" in failure


def test_encoder_replacement_resolves_a_listed_claim(tmp_path: Path) -> None:
    root = _repo(tmp_path, module=EDITED)
    entry = _listed(root)
    _write_manifest(
        root,
        {MODULE: EDITED, COMPANION: b"- name: case\n"},
        schema_version="axiom-encode/applied-rulespec/v5",
        runner="codex",
    )
    result = _sync(root, (entry,))
    assert result.failures == () and result.resolved == (entry,)


def test_removed_manifest_resolves_a_listed_claim(tmp_path: Path) -> None:
    root = _repo(tmp_path, module=EDITED)
    entry = _listed(root)
    (root / MANIFEST).unlink()
    result = _sync(root, (entry,))
    assert result.failures == () and result.resolved == (entry,)


@pytest.mark.parametrize(
    "applied",
    [
        None,
        [],
        "zz/statutes/example/section-1.yaml",
        [{"sha256": "0" * 64}],
        [{"path": "/abs/section-1.yaml", "sha256": "0" * 64}],
        [{"path": "zz/statutes/../section-1.yaml", "sha256": "0" * 64}],
        [{"path": "zz//statutes/section-1.yaml", "sha256": "0" * 64}],
        [{"path": "zz\\statutes\\section-1.yaml", "sha256": "0" * 64}],
        [{"path": MODULE, "sha256": "ABC"}],
        [{"path": MODULE, "sha256": "0" * 64, "extra": 1}],
        [{"path": MODULE, "deleted": False}],
        [{"path": MODULE, "sha256": "0" * 64}, {"path": MODULE, "sha256": "1" * 64}],
    ],
)
def test_malformed_manifests_fail_closed(tmp_path: Path, applied: object) -> None:
    target = tmp_path / MANIFEST
    target.parent.mkdir(parents=True)
    payload = {} if applied is None else {"applied_files": applied}
    target.write_text(json.dumps(payload))
    _claims, problems = manifest_claims(tmp_path)
    assert problems


def test_duplicate_json_keys_fail_closed(tmp_path: Path) -> None:
    target = tmp_path / MANIFEST
    target.parent.mkdir(parents=True)
    entry = f'"path": "{MODULE}", "sha256": "{"0" * 64}", "sha256": "{"1" * 64}"'
    target.write_text('{"applied_files": [{' + entry + "}]}")
    _claims, problems = manifest_claims(tmp_path)
    assert len(problems) == 1 and "duplicate keys" in problems[0]


def test_symlinked_manifest_fails_closed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    real = tmp_path / "real.json"
    real.write_bytes((root / MANIFEST).read_bytes())
    (root / MANIFEST).unlink()
    (root / MANIFEST).symlink_to(real)
    _claims, problems = manifest_claims(root)
    assert len(problems) == 1 and "symlink" in problems[0]


@pytest.mark.parametrize(
    ("path", "synced"),
    [
        (MODULE, True),
        (COMPANION, True),
        ("zz/regulations/a/b.yaml", True),
        ("zz/policies/a/b.yaml", True),
        ("zz/legislation/a/b.yaml", True),
        ("programs/zz/income-tax/fy-2026.yaml", False),
        ("zz/programs/income-tax/fy-2026.yaml", False),
        (".axiom/toolchain.toml", False),
        ("known-validation-gaps.yaml", False),
        ("zz/statutes/a.json", False),
        ("zz/statutes", False),
    ],
)
def test_synced_scope(path: str, synced: bool) -> None:
    assert is_synced_path(path) is synced
