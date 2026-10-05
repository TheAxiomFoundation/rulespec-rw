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
    "LICENSE",
    "LICENSE-CODE",
    "NOTICE",
    "README.md",
    "known-missing-money-atoms.yaml",
    "known-validation-gaps.yaml",
    "oracle-coverage-pending.yaml",
    "variables.toml",
}
ORACLE_INDEX = ROOT / "data/oracles/oracle-index.json"
SOURCE_MAP = ROOT / "data/coverage/tax-benefit-source-map.json"
SYSTEM_RE = re.compile(r"\b[A-Z]{2}_\d{4}\b")
AXIOM_OUTPUT_RE = re.compile(r"^rw:(?P<path>[a-z0-9/._-]+)#(?P<name>[a-z0-9_]+)$")
# Other SOUTHMOD models (Annex 1.3 of the Adhesion Agreement): the sibling
# rulespec lanes gh, ug, zm and et, plus Tanzania and Mozambique. Neither data
# file may name another country's model, model id, country or system prefix:
# a record pasted from a sibling repo must fail here.
OTHER_SOUTHMOD_COUNTRIES = {
    "gh": ("GHAMOD", "Ghana"),
    "ug": ("UGAMOD", "Uganda"),
    "zm": ("MicroZAMOD", "Zambia"),
    "et": ("ETMOD", "Ethiopia"),
    "tz": ("TAZMOD", "Tanzania"),
    "mz": ("MOZMOD", "Mozambique"),
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
        child.name
        for child in ROOT.iterdir()
        if child.is_file() and child.name != ".git"
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


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def rwamod_oracle() -> dict:
    oracles = load_json(ORACLE_INDEX)["oracles"]
    assert len(oracles) == 1, "expected exactly one oracle (RWAMOD)"
    return oracles[0]


def wired_suites() -> list[dict]:
    return rwamod_oracle()["wired"]["suites"]


def iter_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)


def encoded_modules() -> list[str]:
    """Non-test RuleSpec YAML under rw/, excluding the program specs."""
    return sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "rw").rglob("*.yaml")
        if not path.name.endswith(".test.yaml")
        and "programs" not in path.relative_to(ROOT / "rw").parts
    )


def test_oracle_index_identifies_rwamod() -> None:
    payload = load_json(ORACLE_INDEX)
    assert payload["jurisdiction"] == "rw"
    oracle = rwamod_oracle()
    assert (oracle["id"], oracle["name"]) == ("rwamod", "RWAMOD")
    assert oracle["url"].startswith("https://www.wider.unu.edu/about/")
    assert "rwamod" in oracle["url"]
    assert oracle["authority"] == "wired_per_case_parity"
    assert oracle["availability_check"]["status"] == "wired_per_case_parity"


def test_oracle_index_systems_and_suites_are_rwandan() -> None:
    oracle = rwamod_oracle()
    wired = oracle["wired"]
    system_texts = [wired["system"], oracle["systems"]]
    system_texts += [suite["system"] for suite in wired["suites"] if "system" in suite]
    systems = {match for text in system_texts for match in SYSTEM_RE.findall(text)}
    assert systems, "no <CC>_YYYY system recorded"
    assert all(system.startswith("RW_") for system in systems), systems
    assert wired["dataset_configuration"].startswith("rw_")
    for suite in wired["suites"]:
        assert suite["suite"].startswith("rw-"), suite["suite"]


def test_oracle_index_statistics_are_consistent() -> None:
    wired = rwamod_oracle()["wired"]
    suites = wired["suites"]
    for suite in suites:
        name = suite["suite"]
        assert suite["matched"] + suite["dispositioned"] == suite["comparisons"], name
        assert len(suite["axiom_outputs"]) == len(suite["rwamod_variables"]), name
    assert wired["totals"] == {
        "suites": len(suites),
        "cases": sum(suite["cases"] for suite in suites),
        "comparisons": sum(suite["comparisons"] for suite in suites),
        "matched": sum(suite["matched"] for suite in suites),
        "dispositioned": sum(suite["dispositioned"] for suite in suites),
    }


def test_oracle_index_axiom_outputs_resolve_to_rules() -> None:
    for suite in wired_suites():
        for output in suite["axiom_outputs"]:
            match = AXIOM_OUTPUT_RE.match(output)
            assert match, f"{suite['suite']}: malformed output {output}"
            module = ROOT / "rw" / f"{match['path']}.yaml"
            assert module.is_file(), f"{suite['suite']}: {output} has no module"
            rules = yaml.safe_load(module.read_text()).get("rules", [])
            names = {rule["name"] for rule in rules}
            assert match["name"] in names, f"{suite['suite']}: {output} is not a rule"


def test_oracle_index_records_no_local_paths() -> None:
    # local_path names where the licensed bundle sits; nothing else may.
    oracle = dict(rwamod_oracle())
    oracle.pop("local_path")
    for text in iter_strings(oracle):
        assert "~/" not in text and "/Users/" not in text, text[:80]


def test_source_map_tracks_resolve() -> None:
    payload = load_json(SOURCE_MAP)
    assert payload["jurisdiction"] == "rw"
    suite_names = {suite["suite"] for suite in wired_suites()}
    ids = [track["id"] for track in payload["tracks"]]
    assert len(ids) == len(set(ids)), "duplicate track ids"
    for track in payload["tracks"]:
        modules = track.get("rulespec_modules", [])
        assert (track["status"] == "encoded") == bool(modules), track["id"]
        for module in modules:
            assert (ROOT / module).is_file(), f"{track['id']}: {module} missing"
        for suite in track.get("oracle_suites", []):
            assert suite in suite_names, f"{track['id']}: unknown suite {suite}"


def test_source_map_covers_every_encoded_module() -> None:
    tracks = load_json(SOURCE_MAP)["tracks"]
    mapped = {
        module for track in tracks for module in track.get("rulespec_modules", [])
    }
    missing = sorted(set(encoded_modules()) - mapped)
    assert not missing, f"encoded modules with no source-map track: {missing}"


def test_source_map_links_each_compared_module_to_its_suite() -> None:
    tracks = load_json(SOURCE_MAP)["tracks"]
    for suite in wired_suites():
        for output in suite["axiom_outputs"]:
            module = f"rw/{AXIOM_OUTPUT_RE.match(output)['path']}.yaml"
            assert any(
                module in track.get("rulespec_modules", [])
                and suite["suite"] in track.get("oracle_suites", [])
                for track in tracks
            ), f"no track links {module} to {suite['suite']}"


def test_source_map_restates_no_amounts() -> None:
    # Amounts live in the modules; the map cites law and points at them.
    text = SOURCE_MAP.read_text()
    assert "%" not in text
    assert not re.search(r"\b(?:FRW|RWF|Frw)\b", text)
    assert not re.search(r"\d,\d{3}", text)


def test_data_files_name_no_other_southmod_country() -> None:
    for path in (ORACLE_INDEX, SOURCE_MAP):
        text = path.read_text()
        for code, names in OTHER_SOUTHMOD_COUNTRIES.items():
            for name in names:
                assert not re.search(rf"\b{name}\b", text, re.IGNORECASE), (
                    f"{path.name} names {name}"
                )
            assert not re.search(rf"\b{code.upper()}_\d{{4}}\b", text), (
                f"{path.name} names a {code.upper()}_YYYY system"
            )


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
