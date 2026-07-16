from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
JURISDICTION_DIR_RE = re.compile(r"^[a-z]{2}(-[a-z0-9-]+)*$")
CONTENT_DIRS = ("statutes", "regulations", "policies", "legislation")
IGNORED_DIRS = {".git", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__"}
ALLOWED_ROOT_DIRS = {".axiom", ".github", "bulk", "data", "docs", "tests", "rw"}
ALLOWED_ROOT_FILES = {
    ".gitignore",
    "CLAUDE.md",
    "README.md",
    "known-missing-money-atoms.yaml",
    "known-validation-gaps.yaml",
    "oracle-coverage-pending.yaml",
    "variables.toml",
}


def jurisdiction_dirs() -> list[Path]:
    return sorted(
        child
        for child in ROOT.iterdir()
        if child.is_dir()
        and JURISDICTION_DIR_RE.match(child.name)
        and any((child / marker).is_dir() for marker in CONTENT_DIRS)
    )


def rulespec_content_roots() -> list[Path]:
    return [
        jurisdiction / marker
        for jurisdiction in jurisdiction_dirs()
        for marker in CONTENT_DIRS
        if (jurisdiction / marker).is_dir()
    ]


def iter_rulespec_files() -> list[Path]:
    files: list[Path] = []
    for root in rulespec_content_roots():
        files.extend(
            path
            for path in root.rglob("*.yaml")
            if not path.name.endswith(".test.yaml")
        )
    return sorted(files)


def test_only_rwanda_namespace_present() -> None:
    """Rwanda is unitary: the only jurisdiction directory is rw/."""
    names = {d.name for d in jurisdiction_dirs()}
    assert names <= {"rw"}, f"unexpected jurisdiction dirs: {names - {'rw'}}"


def test_rw_content_buckets_exist() -> None:
    for marker in ("statutes", "regulations", "policies"):
        assert (ROOT / "rw" / marker).is_dir(), f"missing rw/{marker}"


def test_root_directories_are_allowed() -> None:
    # The org validate-rulespec workflow checks out sibling toolchain repos
    # (axiom-encode, axiom-rules-engine, ...) into a `_axiom/` directory and
    # skips any `_`- or `.`-prefixed directory during shard discovery. Mirror
    # that: ignore underscore/dot-prefixed dirs so CI's transient checkouts do
    # not trip the layout gate.
    found = {
        child.name
        for child in ROOT.iterdir()
        if child.is_dir()
        and child.name not in IGNORED_DIRS
        and not child.name.startswith(("_", "."))
    }
    unexpected = found - ALLOWED_ROOT_DIRS
    assert not unexpected, f"unexpected root directories: {unexpected}"


def test_root_files_are_allowed() -> None:
    # In a git worktree checkout `.git` is a gitdir-pointer file rather than
    # a directory, so exclude it here just as IGNORED_DIRS excludes the
    # `.git` directory in normal clones.
    found = {
        child.name for child in ROOT.iterdir() if child.is_file() and child.name != ".git"
    }
    unexpected = found - ALLOWED_ROOT_FILES
    assert not unexpected, f"unexpected root files: {unexpected}"


def test_every_rulespec_has_companion_test() -> None:
    """Any encoded rule module must ship a companion .test.yaml alongside it."""
    for path in iter_rulespec_files():
        companion = path.with_name(path.name[: -len(".yaml")] + ".test.yaml")
        assert companion.exists(), f"{path} is missing companion {companion.name}"


def test_money_atom_ratchet_is_nonnegative_int() -> None:
    payload = yaml.safe_load((ROOT / "known-missing-money-atoms.yaml").read_text())
    allowed = payload["total_allowed"]
    assert isinstance(allowed, int) and allowed >= 0


def test_oracle_index_is_rw_scoped() -> None:
    payload = json.loads((ROOT / "data/oracles/oracle-index.json").read_text())
    assert payload["jurisdiction"] == "rw"


def test_source_map_is_rw_scoped() -> None:
    payload = json.loads(
        (ROOT / "data/coverage/tax-benefit-source-map.json").read_text()
    )
    assert payload["jurisdiction"] == "rw"


def test_toolchain_pins_are_full_shas() -> None:
    import tomllib

    payload = tomllib.loads((ROOT / ".axiom/toolchain.toml").read_text())
    toolchain = payload["toolchain"]
    assert set(toolchain) == {
        "axiom_corpus_release",
        "axiom_corpus_release_content_sha256",
        "validation_waiver_set_sha256",
    }
    assert re.fullmatch(
        r"[a-z]{2}-rulespec-\d{4}-\d{2}-\d{2}", toolchain["axiom_corpus_release"]
    ), "release must be an immutable dated name"
    sha256_re = re.compile(r"^[0-9a-f]{64}$")
    assert sha256_re.match(toolchain["axiom_corpus_release_content_sha256"])
    assert sha256_re.match(toolchain["validation_waiver_set_sha256"])
