"""Manifest-sync guard: attested RuleSpec files must keep their recorded bytes.

Each manifest under ``.axiom/encoding-manifests/`` lists, in
``applied_files``, the sha256 of every file it attests. The shared
validator's generated-RuleSpec guard checks only the files a pull request
changes, so a file edited while that guard was off keeps a manifest that no
longer matches it, and nothing reads that manifest again. These tests read
every manifest on every run and fail when an attested RuleSpec module or
companion test no longer has the bytes its manifest records. They are a
stricter variant of rulespec-dk's check: every module and companion test is
synced, and assembled ``programs/`` specs are left out, as in rulespec-us.

Two lists in ``known_stale_attestations.py`` record the state found when this
test was added: manifest claims that were already stale, by exact bytes, and
modules that had no manifest. Listing a claim records the drift; it does not
attest the file. Both lists may only shrink: every entry must carry a digest
in ``ADOPTED_LIST_SHA256`` below, so adding or rewriting an entry means
editing this guard.

This file is also the retired-manifest inventory that axiom-encode's
replacement path reconciles. ``KNOWN_RETIRED_SCHEMA_MANIFESTS`` must stay a
single top-level annotated frozenset assignment with one entry per line, and
no real manifest path, module path or rule identity may appear anywhere else
in this file. The fixtures below use the unused jurisdiction ``zz``.
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
    KNOWN_STALE_ATTESTATIONS,
    KNOWN_UNMANIFESTED_MODULES,
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
ENCODER_SCHEMA = "axiom-encode/applied-rulespec/v5"
ENCODER_SIGNATURE_ALGORITHM = "ed25519-domain-v1"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
#: Files the operating system drops into directories; never manifests.
IGNORED_NAMES = frozenset({".DS_Store"})

#: Manifests whose primary module was retired without a replacement.
#: Empty: every manifest here attests at least one live file.
KNOWN_RETIRED_SCHEMA_MANIFESTS: frozenset[str] = frozenset()

#: One digest per entry the two lists in known_stale_attestations.py held when
#: they were adopted on 2026-10-14, across rulespec-gh, -ug, -zm, -et and -rw
#: (see ``stale_entry_sha256`` and ``unmanifested_entry_sha256``). An entry
#: whose digest is missing here was added or rewritten later.
ADOPTED_LIST_SHA256: frozenset[str] = frozenset(
    {
        "02b580c08afbe29c87a1e87962dc37474f74ce0a82be73b3a3f12515a6c14b01",
        "03916bb6be2624ec6563a91d05913d31ca7f93f2f8aa3b2f86ba9e91ffb5254b",
        "0b966e7c015fe135ae1fb57ec9c5eac14fd316a916aad013a9564ae038144bec",
        "0bcf08d8964ab9877d9cdcea4a11e65b3bf6633ecdf6f5f46fc65b6ca0a369bc",
        "198d9698a2f272b5e56980266d2a85a526ac5fe1b2d52b800ab249a88770e6d8",
        "1c703a49d80c05714df91b060ecdd98f911e24b1742ab0c54a1ccb3ad6c44cdc",
        "1ea7e5457cacba70e109a2024c4d516485944aff26217b172601e2b4756c4040",
        "294e9d02a6d224d3287ce9994a4eaa3c48799d64ba0805cf1f3e0bdcc1bc3fe8",
        "30a28462ba529097057b66084a318435db0b29164b893645689d4e6c880a601c",
        "34920b62abde04deabcc7c1b4369b2b44e846eea6cbf6fac48bc7e110a5d370e",
        "3ad35daf2da20307153c535e5c7f292c90eca7f646072ed4323eb3df625a76a4",
        "3e5f778d39964e60f65f88e1c1c6c759f6830476017adcd9c90d80daa96722a5",
        "4078cfc4f42119e8d591dd770a3c93ff460c7b2066f2e1c8624c3698f420f163",
        "438470ed069376abd4b3d10bd205b9365f3cd959a74639aa41e4b10050dd5fa6",
        "444d69c79a94cef5ca28753e90b4bf40c7dbbf5125ace156d8a2f15d5370536a",
        "53abcf38df2ea5579ac5db4bd53e0c1ce4891132c4556791ea3dfc3e7c78fd32",
        "595b5588fe2acfb952acc5210dba5de58389dcb1af2779916e07e08b0a747504",
        "65e4bd5d896dad6709b8d230dc79c4929ee5d09d26d98d9a8c30a982fd702587",
        "6a3739759543d681ef151ca326e83b37cc06f280eeeb0d518377f6f43d0170b0",
        "6b16ebe0474a5e1cbbf095b45dc7c1704c2eb19c8427e77b9a70e3bdbc261604",
        "7073fa85fa490dffdd12449881ff580086e440d9cb081d4ef31f719e4bdaed0f",
        "731a07f20894fd34475c64c4d8b2155b3cebbded59c924c15c8f0808ca443942",
        "74d784f121a371241a2d8b9b190e7e2b62ed34f84d074abd4b3445d431a290e6",
        "757819bd9ba2d397077aba0d307ab06acedfa2f048dfd5a26770ca5a38dbea13",
        "7da1887f46302287f1459673188b0582a77ed018426c4565bec684edeaadd605",
        "8524103d8efd1d77b7399fc07228d4f071c4f7be71da9076d8912abbc44e833c",
        "88afc05ff7ec5fce15eccb05dee92ab99cd47096c43a89ed0f88ff28cd18307b",
        "88e4cb8583529359c26ac7ffb5ee7e74f27bdc2fb681c36bf4dd903507e3af0c",
        "8df6760a49cbec6d1720783c08e90b1c145c6ac7b5cd01295ab83d44bef42f70",
        "90cca9913322cbf4575bee6b7d516860a6955e4cd46d96bbf0883faa125c97ce",
        "91b46ff916af505b60c7fb94cd6bb7717813033177607bbee1ed7b38de4b8981",
        "93abcc20f87354865de80f50159eb80f6c7d1e390a3e80217fb566d6fbfcc5f7",
        "95c73387f7db5c62eb40daaddc22ff172cab5cd5cd4eca93d0aa55a195d8f3e9",
        "a90e0472f545b0097c143e2802cbb18832732e05ac5b3e0bba4aba52e1ab7421",
        "ab28ae251e4d567d6fb9bba6fd64a2ccc18a2aa5f95831e57720e22ad0d5e25a",
        "aba4f954e259ed75331d8e0a31f95c485070f690ec9740022c66e4f1b2b1b545",
        "b231845574e1e1fd2a5c239af6997b1061a6486b56d19305111085621da58cf9",
        "b42e65baf16ddc544a7a433d926734ecb1188c70911d0fef56199070c97a4029",
        "be6f724ac15ab06f7960cd3642e81b8380f5852e5538df1812a475dcbf033c5e",
        "cb4dc9a5545e096bbf95dcdc36cf542191fbe97a88f2f2f0b1653a96e1ba703c",
        "d2aa450d9f6d05df33f9ccad6a1ee3af5ffd91414549694752149d5917d3a9e4",
        "d5db98fdfd7d3876f0dac65298de0b8029139c3b5aea6ffc367608d75b663f0c",
        "d8100b606e0d8c75543f903b1c7c53cda67626880303835efd077c55961816a3",
        "da9b1736e30cc3a428d31b97697d4d849d26e23cb4f3ac231702b117f3fc47a9",
        "dddbb4d3c2c1dae5b86a80406d97dcf509d0a5253387da056e27c0d3d8726bd2",
        "e7135f56ed05f416731ada6c71c4dc00ad7314a193d3475a3069aa286be63991",
        "ea2577322c3a9a4a9caff5ad00b7dea4d3d96ff9fddbacd6234bbadc3920fb91",
        "ed756875dd2a6ce607155dabfcbebcc72ea2d7d82e5d3724ff87e6e021afff04",
        "edf466153da5105ee2827c4d96fcab9097d17876f807a64c07da3fd2067de878",
        "f56cfaf4616cbb0253501a8450938f3910de18b6b0d4e11c47d8775f57a73eb6",
        "f618ca837f26222c25f4588ba778e3a2cc69068f335f5e3178d7b65cd742722e",
        "f66f6097a82657ada87d8d55e9e27b127b512a1931c9acc1c8fd067528858200",
    }
)


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


def stale_entry_sha256(entry: StaleAttestation) -> str:
    fields = (
        "stale",
        entry.manifest,
        entry.manifest_sha256,
        entry.path,
        entry.attested_sha256,
        entry.current_sha256,
        *entry.changed_by,
    )
    return hashlib.sha256("\n".join(fields).encode()).hexdigest()


def unmanifested_entry_sha256(path: str) -> str:
    return hashlib.sha256(f"unmanifested\n{path}".encode()).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _has_symlink(root: Path, relative: str) -> bool:
    """True if the path or any directory between it and ``root`` is a symlink."""
    cursor = root
    for part in PurePosixPath(relative).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            return True
    return False


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
    return (
        bool(path)
        and "\\" not in path
        and not PurePosixPath(path).is_absolute()
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
    if _has_symlink(root, MANIFEST_DIR.as_posix()):
        return [], [f"{MANIFEST_DIR}: manifest directory is or sits behind a symlink"]
    manifest_dir = root / MANIFEST_DIR
    if not manifest_dir.is_dir():
        return [], []
    for manifest_path in sorted(manifest_dir.rglob("*")):
        rel = manifest_path.relative_to(root).as_posix()
        if manifest_path.name in IGNORED_NAMES and not manifest_path.is_symlink():
            continue
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
                and SHA256_RE.fullmatch(entry["sha256"])
            ):
                claims.append(Claim(rel, path, entry["sha256"], False))
            else:
                problems.append(
                    f"{where} must be {{path, sha256}} with a lowercase hex digest "
                    "or {path, deleted: true}"
                )
    return claims, problems


def _encoder_replacement_issue(manifest: Path, path: str) -> str | None:
    """Why a changed listed manifest is not an encoder replacement, if it isn't.

    This checks shape only: schema v5, an ed25519 signature record, and a claim
    for the listed file. Whether the signature verifies is the shared
    generated-RuleSpec guard's job.
    """
    try:
        payload = _load_manifest(manifest)
    except (UnicodeDecodeError, ValueError) as exc:
        return f"unreadable ({exc})"
    signature = payload.get("signature")
    if payload.get("schema_version") != ENCODER_SCHEMA:
        return f"schema is not {ENCODER_SCHEMA}"
    if (
        not isinstance(signature, dict)
        or signature.get("algorithm") != ENCODER_SIGNATURE_ALGORITHM
    ):
        return f"it carries no {ENCODER_SIGNATURE_ALGORITHM} signature"
    applied = payload.get("applied_files")
    if not isinstance(applied, list) or not any(
        isinstance(item, dict) and item.get("path") == path for item in applied
    ):
        return f"it has no claim for {path}"
    return None


def check_sync(
    root: Path,
    claims: list[Claim],
    baseline: tuple[StaleAttestation, ...],
    retired: frozenset[str] = frozenset(),
) -> SyncResult:
    """Compare every synced claim with the file it names.

    A stale claim passes only when ``baseline`` lists exactly that manifest,
    file, recorded hash and current hash, and the manifest file is unchanged
    since it was listed. A listed entry resolves, with a warning, only on
    positive evidence: the file matches its unchanged manifest again, the
    manifest and the file are both gone, or the manifest was replaced by an
    encoder manifest (schema v5, ed25519 signature record, a claim for the
    file). Anything else that touches a listed manifest fails.
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
        if _has_symlink(root, claim.path):
            failures.append(
                f"{claim.path}: attested by {claim.manifest}, but it is or sits "
                "behind a symlink"
            )
            continue
        if claim.deleted:
            if target.exists():
                failures.append(
                    f"{claim.path}: {claim.manifest} records a deletion, but the "
                    "file exists"
                )
            continue
        if not target.is_file():
            failures.append(
                f"{claim.path}: attested by {claim.manifest}, but missing or not a "
                "regular file"
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
        if _sha256(root / claim.manifest) != entry.manifest_sha256:
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
        if not manifest.exists() and not manifest.is_symlink():
            if (root / entry.path).exists() or (root / entry.path).is_symlink():
                failures.append(
                    f"{entry.manifest}: a listed manual attestation was removed "
                    f"while {entry.path} remains. Replace the module through the "
                    "supervised encoder."
                )
                continue
        elif manifest.is_symlink() or not manifest.is_file():
            failures.append(f"{entry.manifest}: listed manifest is not a regular file")
            continue
        elif _sha256(manifest) != entry.manifest_sha256:
            issue = _encoder_replacement_issue(manifest, entry.path)
            if issue is not None:
                failures.append(
                    f"{entry.manifest}: a listed manual attestation was edited, and "
                    f"the result is not an encoder manifest ({issue}). No "
                    "sanctioned tool writes manual attestations; replace the "
                    "module through the supervised encoder."
                )
                continue
        resolved.append(entry)
    return SyncResult(tuple(failures), tuple(known), tuple(resolved))


def check_unmanifested(
    root: Path,
    claims: list[Claim],
    modules: list[str],
    known: tuple[str, ...],
) -> tuple[list[str], list[str]]:
    """New unmanifested modules (failures), and listed ones now resolved."""
    attested = {claim.path for claim in claims if not claim.deleted}
    unmanifested = {path for path in modules if path not in attested}
    failures = [
        f"{path} has no encoding manifest, and it is not in "
        "KNOWN_UNMANIFESTED_MODULES. A manifest was removed or a module arrived "
        "without one; restore it through the supervised encoder."
        for path in sorted(unmanifested - set(known))
    ]
    resolved = [path for path in known if path not in unmanifested]
    return failures, resolved


def check_adopted(
    baseline: tuple[StaleAttestation, ...],
    unmanifested: tuple[str, ...],
    adopted: frozenset[str],
) -> list[str]:
    problems = []
    for entry in baseline:
        if stale_entry_sha256(entry) not in adopted:
            problems.append(f"stale entry for {entry.path} was added or rewritten")
    for path in unmanifested:
        if unmanifested_entry_sha256(path) not in adopted:
            problems.append(f"unmanifested entry {path} was added")
    return problems


def _repo_modules(root: Path) -> list[str]:
    return [path.relative_to(root).as_posix() for path in iter_rulespec_files()]


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


def test_no_module_loses_its_manifest() -> None:
    claims, _problems = manifest_claims(ROOT)
    failures, resolved = check_unmanifested(
        ROOT, claims, _repo_modules(ROOT), KNOWN_UNMANIFESTED_MODULES
    )
    assert failures == [], "\n".join(failures)
    for path in resolved:
        warnings.warn(
            f"{path} now has a manifest or is gone; delete it from "
            "KNOWN_UNMANIFESTED_MODULES in tests/known_stale_attestations.py",
            stacklevel=1,
        )


def test_known_lists_only_shrink() -> None:
    keys = [(e.manifest, e.path, e.attested_sha256) for e in KNOWN_STALE_ATTESTATIONS]
    assert len(keys) == len(set(keys)), "duplicate stale entries"
    assert len(KNOWN_UNMANIFESTED_MODULES) == len(set(KNOWN_UNMANIFESTED_MODULES))
    for entry in KNOWN_STALE_ATTESTATIONS:
        assert entry.manifest.startswith(f"{MANIFEST_DIR}/"), entry
        assert is_synced_path(entry.path), entry
        for digest in (
            entry.manifest_sha256,
            entry.attested_sha256,
            entry.current_sha256,
        ):
            assert SHA256_RE.fullmatch(digest), entry
        assert entry.attested_sha256 != entry.current_sha256, entry
        assert entry.changed_by, entry
        assert all(COMMIT_RE.fullmatch(c) for c in entry.changed_by), entry
        assert entry.change, entry
    problems = check_adopted(
        KNOWN_STALE_ATTESTATIONS, KNOWN_UNMANIFESTED_MODULES, ADOPTED_LIST_SHA256
    )
    assert problems == [], (
        "known_stale_attestations.py may only shrink; new drift and new "
        "unmanifested modules are fixed through the supervised encoder:\n"
        + "\n".join(problems)
    )


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


def test_unsynced_claims_naming_missing_files_are_reported() -> None:
    """Program-spec and metadata claims are not synced; report dangling ones."""
    claims, _problems = manifest_claims(ROOT)
    dangling = sorted(
        f"{claim.path} ({claim.manifest})"
        for claim in claims
        if not claim.deleted
        and not is_synced_path(claim.path)
        and not (ROOT / claim.path).exists()
    )
    if dangling:
        warnings.warn(
            f"{len(dangling)} unsynced manifest claims name files that do not "
            f"exist (e.g. {dangling[0]})",
            stacklevel=1,
        )


def test_no_jurisdiction_manifest_trees() -> None:
    """This test reads only the root manifest tree; no other layout may exist."""
    trees = [
        (directory / ".axiom" / "encoding-manifests").relative_to(ROOT).as_posix()
        for directory in jurisdiction_dirs()
        if (directory / ".axiom" / "encoding-manifests").exists()
    ]
    assert trees == [], f"manifest trees outside {MANIFEST_DIR}: {trees}"


# --------------------------------------------------------------------------
# The check itself, on fixture repositories. Paths use the unused
# jurisdiction ``zz`` so no real manifest path appears in this file.

MODULE = "zz/statutes/example/section-1.yaml"
COMPANION = "zz/statutes/example/section-1.test.yaml"
MANIFEST = f"{MANIFEST_DIR}/zz/statutes/example/section-1.json"
ORIGINAL = b"format: rulespec/v1\nrules:\n  - name: rate\n"
EDITED = b"format: rulespec/v1\nrules:\n  - name: rate  # edited\n"
CASES = b"- name: case\n"
SIGNED = {"algorithm": ENCODER_SIGNATURE_ALGORITHM, "key_id": "k", "value": "v"}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_manifest(root: Path, files: dict[str, bytes | None], **fields) -> None:
    payload = {
        "applied_files": [
            {"path": path, "deleted": True}
            if data is None
            else {"path": path, "sha256": _digest(data)}
            for path, data in files.items()
        ],
        "schema_version": MANUAL_ATTESTATION_SCHEMA,
        "runner": "manual-attestation",
    }
    payload.update(fields)
    payload = {key: value for key, value in payload.items() if value is not None}
    target = root / MANIFEST
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n")


def _encoder_manifest(root: Path, files: dict[str, bytes | None]) -> None:
    _write_manifest(
        root, files, schema_version=ENCODER_SCHEMA, runner="codex", signature=SIGNED
    )


def _repo(tmp_path: Path, module: bytes = ORIGINAL) -> Path:
    (tmp_path / MODULE).parent.mkdir(parents=True)
    (tmp_path / MODULE).write_bytes(module)
    (tmp_path / COMPANION).write_bytes(CASES)
    _write_manifest(tmp_path, {MODULE: ORIGINAL, COMPANION: CASES})
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


def test_symlinked_parent_directory_fails(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    real = tmp_path / "real-statutes"
    (real / "example").mkdir(parents=True)
    (real / "example" / "section-1.yaml").write_bytes(ORIGINAL)
    (real / "example" / "section-1.test.yaml").write_bytes(CASES)
    (root / "zz").mkdir()
    (root / "zz" / "statutes").symlink_to(real)
    _write_manifest(root, {MODULE: ORIGINAL, COMPANION: CASES})
    assert len(_sync(root).failures) == 2


def test_symlinked_manifest_tree_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / ".axiom").mkdir(parents=True)
    real = tmp_path / "real-manifests"
    real.mkdir()
    (root / MANIFEST_DIR).symlink_to(real)
    _claims, problems = manifest_claims(root)
    assert len(problems) == 1 and "symlink" in problems[0]


def test_deletion_entry_requires_absence(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    gone = "zz/statutes/example/gone.yaml"
    _write_manifest(root, {MODULE: ORIGINAL, COMPANION: CASES, gone: None})
    assert _sync(root).failures == ()
    (root / gone).write_bytes(b"back\n")
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
        result = _sync(root, (wrong,))
        assert result.failures and result.known == (), wrong


@pytest.mark.parametrize(
    "fields",
    [
        {},  # still a manual attestation
        {"schema_version": None},  # schema removed
        {"schema_version": ENCODER_SCHEMA},  # relabelled, unsigned
        {"schema_version": ENCODER_SCHEMA, "signature": {"algorithm": "hmac-sha256"}},
    ],
)
def test_hand_blessing_a_listed_manifest_fails(tmp_path: Path, fields: dict) -> None:
    """Rewriting a listed manifest to attest the current bytes is caught."""
    root = _repo(tmp_path, module=EDITED)
    entry = _listed(root)
    _write_manifest(root, {MODULE: EDITED, COMPANION: CASES}, **fields)
    (failure,) = _sync(root, (entry,)).failures
    assert "was edited" in failure


def test_any_other_edit_to_a_listed_manifest_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path, module=EDITED)
    entry = _listed(root)
    _write_manifest(root, {MODULE: ORIGINAL, COMPANION: CASES}, note="x")
    (failure,) = _sync(root, (entry,)).failures
    assert "bytes changed" in failure


def test_removing_a_listed_manifest_while_the_module_remains_fails(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path, module=EDITED)
    entry = _listed(root)
    (root / MANIFEST).unlink()
    (failure,) = _sync(root, (entry,)).failures
    assert "was removed" in failure


def test_encoder_replacement_resolves_a_listed_claim(tmp_path: Path) -> None:
    root = _repo(tmp_path, module=EDITED)
    entry = _listed(root)
    _encoder_manifest(root, {MODULE: EDITED, COMPANION: CASES})
    result = _sync(root, (entry,))
    assert result.failures == () and result.resolved == (entry,)


def test_encoder_retirement_resolves_a_listed_claim(tmp_path: Path) -> None:
    root = _repo(tmp_path, module=EDITED)
    entry = _listed(root)
    (root / MODULE).unlink()
    (root / COMPANION).unlink()
    _encoder_manifest(root, {MODULE: None, COMPANION: None})
    result = _sync(root, (entry,))
    assert result.failures == () and result.resolved == (entry,)


def test_path_migration_resolves_a_listed_claim(tmp_path: Path) -> None:
    root = _repo(tmp_path, module=EDITED)
    entry = _listed(root)
    (root / MANIFEST).unlink()
    (root / MODULE).unlink()
    (root / COMPANION).unlink()
    result = _sync(root, (entry,))
    assert result.failures == () and result.resolved == (entry,)


def test_restored_bytes_resolve_a_listed_claim(tmp_path: Path) -> None:
    root = _repo(tmp_path, module=EDITED)
    entry = _listed(root)
    (root / MODULE).write_bytes(ORIGINAL)
    result = _sync(root, (entry,))
    assert result.failures == () and result.resolved == (entry,)


def test_removing_an_in_sync_manifest_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / MANIFEST).unlink()
    claims, _problems = manifest_claims(root)
    failures, resolved = check_unmanifested(root, claims, [MODULE], ())
    assert len(failures) == 1 and resolved == []
    # Listed at adoption, it passes; once manifested again it resolves.
    assert check_unmanifested(root, claims, [MODULE], (MODULE,)) == ([], [])
    _encoder_manifest(root, {MODULE: ORIGINAL, COMPANION: CASES})
    claims, _problems = manifest_claims(root)
    assert check_unmanifested(root, claims, [MODULE], (MODULE,)) == ([], [MODULE])


def test_lists_cannot_grow_or_be_rewritten(tmp_path: Path) -> None:
    root = _repo(tmp_path, module=EDITED)
    entry = _listed(root)
    adopted = frozenset(
        {stale_entry_sha256(entry), unmanifested_entry_sha256("zz/policies/a.yaml")}
    )
    assert check_adopted((entry,), ("zz/policies/a.yaml",), adopted) == []
    assert check_adopted((), (), adopted) == []
    rewritten = (
        entry._replace(current_sha256=_digest(b"other")),
        entry._replace(changed_by=("1" * 40,)),
        entry._replace(path="zz/statutes/example/other.yaml"),
    )
    for wrong in rewritten:
        assert len(check_adopted((wrong,), (), adopted)) == 1, wrong
    assert len(check_adopted((), ("zz/policies/b.yaml",), adopted)) == 1


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
        [{"path": MODULE, "sha256": "0" * 64 + "\n"}],
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


def test_stray_files_fail_closed_except_os_metadata(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / MANIFEST).parent.joinpath(".DS_Store").write_bytes(b"\0")
    assert manifest_claims(root)[1] == []
    (root / MANIFEST).parent.joinpath("notes.txt").write_text("x")
    assert len(manifest_claims(root)[1]) == 1


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
