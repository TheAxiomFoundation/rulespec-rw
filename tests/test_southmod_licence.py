"""Tripwire for SOUTHMOD (RWAMOD) model internals in committed text.

This repository is public, and the SOUTHMOD_A4.0 Adhesion Agreement bars
giving the model to third parties. CLAUDE.md therefore lets us record only
RWAMOD output variable names used as comparison bindings, outputs observed
on synthetic households, and comparison statistics.

The scan below catches the syntactic forms that model content takes when it
slips into prose: income-list names and compositions, policy and function
names, switch and constant syntax, and output variable names that are not
comparison bindings. It cannot recognise a parameter value, a condition or
a model input-variable name written in plain words; review still owns those.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Every UTF-8 file under these roots is scanned, whatever its suffix, so a
# committed bundle file (EUROMOD parameters are XML) is caught too. The
# program specs live under rw/programs/, so `rw` covers them. `.github/`
# holds workflow shell code and `tests/` holds these patterns, so neither is
# scanned; nor are CI's transient `_axiom/` toolchain checkouts.
SCAN_DIRS = (".axiom", "data", "docs", "rw")

# RWAMOD output variables that axiom-oracles' rw suites compare against
# (`comparisons/rw-*.yaml`). Keep in step with the `wired` block of
# data/oracles/oracle-index.json; test_bindings_match_oracle_index checks it.
COMPARISON_BINDINGS = frozenset(
    {
        "tex01_s",
        "tex12_s",
        "tex13_s",
        "tin_s",
        "tpr_s",
        "tsceehl01_s",
        "tsceehl02_s",
        "tsceehl03_s",
        "tsceehl_s",
        "tsceeml_s",
        "tsceepi_s",
        "tscerhl01_s",
        "tscerhl_s",
        "tscerml_s",
        "tscerpi_s",
        "ttn_s",
        "tva_s",
    }
)
# The disposable-income income list is compared by name; its composition is
# model content.
COMPARED_INCOME_LIST = "ils_dispy"
NOT_POLICY_NAMES = frozenset({"rulespec_rw"})

# SOUTHMOD policy names end in the country code. Any SOUTHMOD country's
# suffix is caught, so a record pasted from another country's repo fails too.
SOUTHMOD_COUNTRY_CODES = ("gh", "ug", "zm", "rw", "et", "tz", "mz")

PATTERNS = {
    "income_list": re.compile(r"\bils?_[a-z][a-z0-9_]*"),
    "policy_name": re.compile(
        r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)*_(?:"
        + "|".join(SOUTHMOD_COUNTRY_CODES)
        + r")\b"
    ),
    "function_name": re.compile(
        r"\b(?:ArithOp|BenCalc|ChangeParam|ChangeSwitch|DefConst|DefIL"
        r"|DefOutput|DefTU|DefVar|DropUnit|Elig|IlVarOp|KeepUnit|SchedCalc"
        r"|SetDefault|UnitLoop|UpdateTU)\b"
    ),
    "switch": re.compile(r"\bsw\s*=\s*(?:on|off|n/a)\b", re.IGNORECASE),
    # Model constants are mixed or lower case; all-caps names are shell
    # variables ($HOME, $GITHUB_WORKSPACE).
    "constant": re.compile(r"\$(?![A-Z][A-Z0-9_]*\b)[A-Za-z][A-Za-z0-9_]*"),
    "period_suffix": re.compile(r"\b\d+(?:\.\d+)?#[ymwqd]\b"),
    "output_variable": re.compile(r"\b[a-z]{2,8}\d{0,2}_s\b"),
}

# Instances already on main inside encoded RuleSpec, which only the
# supervised encoder may change (rulespec-rw#18 tracks the encoding debt).
# The scan found none on 2026-10-04. Add an entry only for a hit in a module
# or companion test, with the exact count and the issue item that lists it;
# delete it when the re-encode lands. The test fails on any change, so the
# list only shrinks on purpose.
PENDING_ENCODER_REPAIR: dict[tuple[str, str], int] = {}


def find_internals(text: str) -> list[tuple[int, str]]:
    """Return (line number, category) for each model-internal token in text."""
    hits: list[tuple[int, str]] = []
    for category, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            token = match.group(0)
            if (
                category == "income_list"
                and token == COMPARED_INCOME_LIST
                and not re.match(r"\s*=", text[match.end() :])
            ):
                continue
            if category == "policy_name" and token in NOT_POLICY_NAMES:
                continue
            if category == "output_variable" and token in COMPARISON_BINDINGS:
                continue
            hits.append((text.count("\n", 0, match.start()) + 1, category))
    return sorted(hits)


def iter_scanned_files() -> list[Path]:
    files = [
        path
        for directory in SCAN_DIRS
        if (ROOT / directory).is_dir()
        for path in (ROOT / directory).rglob("*")
        if path.is_file()
    ]
    files.extend(path for path in ROOT.iterdir() if path.is_file())
    return sorted(files)


def scan_repository() -> dict[tuple[str, str], list[int]]:
    found: dict[tuple[str, str], list[int]] = defaultdict(list)
    for path in iter_scanned_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line, category in find_internals(text):
            found[(path.relative_to(ROOT).as_posix(), category)].append(line)
    return dict(found)


def test_no_new_model_internals() -> None:
    found = scan_repository()
    counts = {key: len(lines) for key, lines in found.items()}
    # Report path, line and category only: CI logs are public too.
    new = [
        f"{path}:{','.join(map(str, sorted(set(found[(path, category)]))))} ({category})"
        for (path, category), count in sorted(counts.items())
        if count > PENDING_ENCODER_REPAIR.get((path, category), 0)
    ]
    assert not new, (
        "SOUTHMOD model content in committed text; describe RWAMOD only by "
        "comparison-binding outputs, observed outputs and comparison "
        "statistics (CLAUDE.md):\n" + "\n".join(new)
    )
    stale = [
        f"{path} ({category}): expected {expected}, found {counts.get((path, category), 0)}"
        for (path, category), expected in sorted(PENDING_ENCODER_REPAIR.items())
        if counts.get((path, category), 0) != expected
    ]
    assert not stale, (
        "PENDING_ENCODER_REPAIR is out of date; lower or delete these entries:\n"
        + "\n".join(stale)
    )


def test_bindings_match_oracle_index() -> None:
    payload = json.loads((ROOT / "data/oracles/oracle-index.json").read_text())
    wired = [
        oracle["wired"]
        for oracle in payload.get("oracles", [])
        if oracle.get("id") == "rwamod" and "wired" in oracle
    ]
    assert wired, "data/oracles/oracle-index.json lost its RWAMOD wired block"
    names = {name for suite in wired[0]["suites"] for name in suite["rwamod_variables"]}
    assert names == COMPARISON_BINDINGS | {COMPARED_INCOME_LIST}


# The detector checks below use made-up tokens of the same shape, plus one
# generic EUROMOD function name and the platform's switch syntax, so this
# file names no RWAMOD content.
def categories(text: str) -> Counter[str]:
    return Counter(category for _, category in find_internals(text))


def test_detector_flags_each_form() -> None:
    assert categories("the example list ils_zzexample") == {"income_list": 1}
    assert categories("il_zzbase3 feeds the base") == {"income_list": 1}
    assert categories("ils_dispy = ils_zza + ils_zzb") == {"income_list": 3}
    assert categories("policy zzz_rw runs") == {"policy_name": 1}
    assert categories("a SchedCalc step") == {"function_name": 1}
    assert categories("it is sw=off here") == {"switch": 1}
    assert categories("uses $zzconstant") == {"constant": 1}
    assert categories("uses $ZzMixedRate and $ZZ_part") == {"constant": 2}
    assert categories("above 77#q") == {"period_suffix": 1}
    assert categories("output zzz01_s differs") == {"output_variable": 1}


def test_detector_flags_other_southmod_country_policy_names() -> None:
    for code in SOUTHMOD_COUNTRY_CODES:
        assert categories(f"policy zzz_{code} runs") == {"policy_name": 1}, code
    assert categories("policy zzz_xx runs") == {}


def test_detector_allows_bindings_and_ordinary_text() -> None:
    clean = (
        "RWAMOD's tin_s at 30,000 is 0, as the statutory schedule gives. "
        "Compared output: ils_dispy. Pinned rulespec_rw 001fa4b; see "
        "rulespec-rw#18. income_tax_s, ${{ secrets.TOKEN }}, $HOME and "
        "$GITHUB_WORKSPACE are not model names."
    )
    assert categories(clean) == {}


def test_detector_reports_line_numbers() -> None:
    assert find_internals("first\nsecond ils_zzexample\n") == [(2, "income_list")]
