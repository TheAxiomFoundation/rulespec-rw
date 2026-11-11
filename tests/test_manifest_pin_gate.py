"""Refuse encoding manifests while CI runs an encoder that skips them.

In CI, axiom-encode's `guard-generated` reads the manifests under
`.axiom/encoding-manifests/`. At each axiom-encode commit listed below, all
older than #1853 (fa0da5e8), its diff mode returns before it lists or
verifies a single manifest when a change touches no protected RuleSpec YAML.
A pull request that adds or edits only manifests therefore passes that guard
with no signature, file-hash or producer check.

While `.github/workflows/repository-checks.yml` pins an encoder in
ENCODERS_THAT_SKIP_MANIFEST_ONLY_CHANGES, `manifests_the_guard_skips` gives
every JSON path under the manifest root a failure line, whatever the file
holds. At any other pin it adds nothing, so a re-pin to fa0da5e8 or later
lifts the gate through the configuration files alone. rulespec-be#135 holds
the same gate.
"""

from __future__ import annotations

import functools
import json
import os
import re
import subprocess
import tomllib
from pathlib import Path, PurePosixPath

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_ROOT = Path(".axiom/encoding-manifests")
WORKFLOW = Path(".github/workflows/repository-checks.yml")
WORKFLOW_TOOLCHAIN = Path(".axiom/workflow-toolchain.toml")
# rulespec-us's layout: a workflow-toolchain job reads the encoder pin from
# .axiom/workflow-toolchain.toml and passes it to the validate job.
TOOLCHAIN_ENCODER_REF = re.compile(
    r"\$\{\{\s*needs\.workflow-toolchain\.outputs\.axiom_encode_ref\s*\}\}"
)
COMMIT_RE = re.compile(r"[0-9a-f]{40}")

# At each of these axiom-encode commits, guard_generated_change_issues in
# src/axiom_encode/cli.py returns [] on the lines noted, before it lists any
# manifest, when a change touches no protected RuleSpec YAML.
ENCODERS_THAT_SKIP_MANIFEST_ONLY_CHANGES = frozenset(
    {
        "185b2457c16df11bf328fd6257a5b7fbe3fe7534",  # cli.py:16205-16206
        "b9d376684cfb5e86202daa3451b8fc716703ed19",  # cli.py:16830-16831
    }
)
# axiom-encode#1853 narrowed that early return: from this commit on, the guard
# verifies changed manifests even when no RuleSpec YAML changes.
FIRST_ENCODER_THAT_CHECKS_MANIFEST_ONLY_CHANGES = (
    "fa0da5e834214052cc8d9d381e25ff409dd1062f"
)
# The rulespec-rw commit that first pinned each skipping encoder. A test
# reads repository-checks.yml at each one and at its parent.
SKIPPING_ENCODER_PIN_HISTORY = {
    "185b2457c16df11bf328fd6257a5b7fbe3fe7534": "2539b05daf6e52ee6eb25916de8b780b713754e7",
    "b9d376684cfb5e86202daa3451b8fc716703ed19": "62eef4b94d2525611be4f575a91808ef27d7234d",
}
# The rulespec-rw main commit this gate starts from. A test reads
# repository-checks.yml at every commit in this commit's history, merged
# branches included, and checks that the encoders listed above are exactly the
# ones it pinned, so the list leaves out no earlier pin.
PIN_HISTORY_RECORDED_THROUGH = "f15605dc4b856d6b5318da1b188c6f8f1cd655ee"


def pinned_encoder_ref(root: Path = ROOT) -> str:
    """Return the axiom-encode commit that CI runs the generated guard from."""
    workflow = yaml.safe_load((root / WORKFLOW).read_text())
    encoder_ref = workflow["jobs"]["validate"]["with"]["axiom-encode-ref"]
    if isinstance(encoder_ref, str) and TOOLCHAIN_ENCODER_REF.fullmatch(
        encoder_ref.strip()
    ):
        toolchain = tomllib.loads((root / WORKFLOW_TOOLCHAIN).read_text())
        encoder_ref = toolchain["workflow_toolchain"]["axiom_encode_ref"]
    return encoder_ref


def manifests_the_guard_skips(root: Path = ROOT) -> list[str]:
    """List every manifest under root while the pinned guard skips them.

    The guard counts any `.json` path under the manifest root as a manifest,
    so this lists each one, in path order, whatever it holds. At a pin outside
    ENCODERS_THAT_SKIP_MANIFEST_ONLY_CHANGES it returns nothing and leaves the
    manifests to the guard.
    """
    encoder_ref = pinned_encoder_ref(root)
    if encoder_ref not in ENCODERS_THAT_SKIP_MANIFEST_ONLY_CHANGES:
        return []
    manifest_root = root / MANIFEST_ROOT
    manifests = sorted(
        (
            manifest.relative_to(manifest_root)
            for manifest in manifest_root.rglob("*.json")
        ),
        key=lambda manifest: manifest.parts,
    )
    return [
        f"{manifest.as_posix()}: the pinned encoder {encoder_ref[:8]} does not "
        "verify a change that adds only manifests"
        for manifest in manifests
    ]


def test_no_manifest_lands_while_the_pinned_guard_skips_manifest_only_changes() -> None:
    assert manifests_the_guard_skips() == []


def test_the_workflow_pins_a_full_commit_id() -> None:
    # The gate must read the pin CI runs; a layout it cannot read fails here.
    assert COMMIT_RE.fullmatch(pinned_encoder_ref())


def test_the_listed_encoders_are_full_commit_ids() -> None:
    # CI accepts only full lowercase commit ids as pins, so a short id here
    # would never match one.
    for encoder_ref in (
        *ENCODERS_THAT_SKIP_MANIFEST_ONLY_CHANGES,
        FIRST_ENCODER_THAT_CHECKS_MANIFEST_ONLY_CHANGES,
    ):
        assert COMMIT_RE.fullmatch(encoder_ref), encoder_ref
    assert (
        FIRST_ENCODER_THAT_CHECKS_MANIFEST_ONLY_CHANGES
        not in ENCODERS_THAT_SKIP_MANIFEST_ONLY_CHANGES
    )


def test_each_skipping_encoder_has_a_recorded_pin() -> None:
    assert set(SKIPPING_ENCODER_PIN_HISTORY) == ENCODERS_THAT_SKIP_MANIFEST_ONLY_CHANGES
    for repository_commit in SKIPPING_ENCODER_PIN_HISTORY.values():
        assert COMMIT_RE.fullmatch(repository_commit), repository_commit
    assert COMMIT_RE.fullmatch(PIN_HISTORY_RECORDED_THROUGH)


# git's list must name each of these, or git() refuses to run: each one
# changes which repository, work tree, index, objects or history a git
# command uses.
GIT_VARIABLES_THE_LIST_MUST_NAME = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_SHALLOW_FILE",
        "GIT_WORK_TREE",
    }
)


@functools.cache
def repository_local_git_variables() -> frozenset[str]:
    """Return the GIT_* variables git lists as local to a repository.

    git exports some of these to a hook so the hook's commands find its
    repository; a pre-commit hook gets GIT_INDEX_FILE, for one. Left in place,
    they aim git at the hook's repository in whatever directory a command runs.
    githooks(5) clears `git rev-parse --local-env-vars` before running git in
    another repository, and this list is that one.
    """
    listed = subprocess.run(
        ["git", "rev-parse", "--local-env-vars"],
        env={
            key: value for key, value in os.environ.items() if not key.startswith("GIT_")
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert listed.returncode == 0, listed.stderr
    variables = frozenset(listed.stdout.split())
    # A short or empty list would leave a hook's variables in place.
    missing = GIT_VARIABLES_THE_LIST_MUST_NAME - variables
    assert not missing, f"git rev-parse --local-env-vars omits {sorted(missing)}"
    return variables


def git_environment() -> dict[str, str]:
    """Return this process's environment without repository-local git variables."""
    local = repository_local_git_variables()
    return {key: value for key, value in os.environ.items() if key not in local}


def git(*args: str, root: Path = ROOT) -> subprocess.CompletedProcess[str]:
    # A replace ref (`git replace`) would show one commit's contents in place
    # of another's, so reads take every commit as written.
    return subprocess.run(
        ["git", "--no-replace-objects", *args],
        cwd=root,
        env=git_environment(),
        capture_output=True,
        text=True,
        check=False,
    )


def require_git_history() -> None:
    shallow = git("rev-parse", "--is-shallow-repository")
    if shallow.returncode != 0:
        pytest.skip("The pin history needs a git checkout")
    if shallow.stdout.strip() != "false":
        pytest.skip("Historical pin commits are unavailable in a shallow checkout")


def in_head_history(commit: str) -> bool:
    return git("merge-base", "--is-ancestor", commit, "HEAD").returncode == 0


def encoder_pinned_at(commit: str, root: Path = ROOT) -> str | None:
    """Return the encoder repository-checks.yml pinned at commit, if any."""
    shown = git("show", f"{commit}:{WORKFLOW.as_posix()}", root=root)
    if shown.returncode != 0:
        return None
    workflow = yaml.safe_load(shown.stdout) or {}
    validate = (workflow.get("jobs") or {}).get("validate") or {}
    return (validate.get("with") or {}).get("axiom-encode-ref")


def encoders_pinned_through(commit: str, root: Path = ROOT) -> set[str]:
    """Return every encoder repository-checks.yml pinned in commit's history.

    This reads the workflow at every commit reachable from commit. A walk
    limited to the workflow's path would simplify history: git drops a merged
    branch whose merge leaves the workflow as the first parent had it, and with
    it any pin that branch made and then undid. A pin passed through
    .axiom/workflow-toolchain.toml would show here as the workflow's
    expression, which no listed encoder equals.
    """
    listed = git("rev-list", commit, root=root)
    assert listed.returncode == 0, listed.stderr
    return {encoder_pinned_at(each, root) for each in listed.stdout.split()} - {None}


def test_the_recorded_pins_match_repository_history() -> None:
    require_git_history()
    # Control: the ancestry check refuses a commit this history lacks.
    assert not in_head_history("0" * 40)
    for encoder_ref, repository_commit in SKIPPING_ENCODER_PIN_HISTORY.items():
        assert in_head_history(repository_commit), repository_commit
        assert encoder_pinned_at(repository_commit) == encoder_ref, repository_commit
        # The recorded commit introduced the pin.
        assert encoder_pinned_at(f"{repository_commit}^") != encoder_ref


def test_the_list_names_every_encoder_pinned_through_the_recorded_commit() -> None:
    require_git_history()
    assert in_head_history(PIN_HISTORY_RECORDED_THROUGH)
    assert (
        encoders_pinned_through(PIN_HISTORY_RECORDED_THROUGH)
        == ENCODERS_THAT_SKIP_MANIFEST_ONLY_CHANGES
    )


# Fixture repositories commit as a fixed identity and read no user or system
# git configuration, so signing settings, hooks or a missing identity on the
# machine running the tests change nothing.
FIXTURE_GIT_ENVIRONMENT = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Pin gate fixture",
    "GIT_AUTHOR_EMAIL": "pin-gate-fixture@example.invalid",
    "GIT_COMMITTER_NAME": "Pin gate fixture",
    "GIT_COMMITTER_EMAIL": "pin-gate-fixture@example.invalid",
}


def fixture_git(repository: Path, *args: str) -> str:
    # Dropping every inherited GIT_* variable keeps a git hook's GIT_INDEX_FILE
    # or GIT_DIR from aiming these commits at the hook's repository.
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    done = subprocess.run(
        ["git", *args],
        cwd=repository,
        env={**environment, **FIXTURE_GIT_ENVIRONMENT},
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout


def commit_fixture_pin(repository: Path, encoder_ref: str) -> None:
    write_workflow_pin(repository, encoder_ref)
    fixture_git(repository, "add", "--all")
    fixture_git(repository, "commit", "--quiet", "--message", f"Pin {encoder_ref[:8]}")


def test_the_pin_scan_reads_a_merged_branch_that_undid_its_pin(tmp_path: Path) -> None:
    # rulespec-tz#18 pinned ba9c705e on a branch, restored 164abed9 on the same
    # branch and merged it, so the merge left repository-checks.yml as main had
    # it. This builds that history.
    kept, undone = "1" * 40, "2" * 40
    repository = tmp_path / "repository"
    repository.mkdir()
    fixture_git(repository, "init", "--quiet", "--initial-branch=main")
    commit_fixture_pin(repository, kept)
    before_branch = fixture_git(repository, "rev-parse", "HEAD").strip()
    fixture_git(repository, "switch", "--quiet", "--create", "branch")
    commit_fixture_pin(repository, undone)
    commit_fixture_pin(repository, kept)
    fixture_git(repository, "switch", "--quiet", "main")
    fixture_git(repository, "merge", "--quiet", "--no-ff", "-m", "Merge branch", "branch")
    # Control: a walk limited to the workflow's path drops the branch.
    walked = fixture_git(repository, "rev-list", "HEAD", "--", WORKFLOW.as_posix())
    assert {encoder_pinned_at(each, repository) for each in walked.split()} == {kept}
    assert encoders_pinned_through("HEAD", repository) == {kept, undone}
    # The scan stops at the commit its caller names.
    assert encoders_pinned_through(before_branch, repository) == {kept}


def test_the_pin_scan_reads_commits_as_written_not_as_replaced(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    fixture_git(repository, "init", "--quiet", "--initial-branch=main")
    commit_fixture_pin(repository, "1" * 40)
    pinned = fixture_git(repository, "rev-parse", "HEAD").strip()
    fixture_git(repository, "switch", "--quiet", "--orphan", "replacement")
    commit_fixture_pin(repository, "2" * 40)
    fixture_git(repository, "replace", pinned, "HEAD")
    # Control: a read that follows the replace ref sees the replacement's pin.
    shown = fixture_git(repository, "show", f"{pinned}:{WORKFLOW.as_posix()}")
    assert "2" * 40 in shown
    assert encoders_pinned_through(pinned, repository) == {"1" * 40}


# The variables these tests expect git's list to name, written out apart from
# GIT_VARIABLES_THE_LIST_MUST_NAME so that a change to either shows.
VARIABLES_THAT_AIM_GIT_ELSEWHERE = (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_SHALLOW_FILE",
    "GIT_WORK_TREE",
)


def test_git_drops_every_variable_git_lists_as_local_to_a_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listed = set(fixture_git(tmp_path, "rev-parse", "--local-env-vars").split())
    # Control: git's list names the variables that aim a command elsewhere.
    assert set(VARIABLES_THAT_AIM_GIT_ELSEWHERE) <= listed
    for variable in listed:
        monkeypatch.setenv(variable, str(tmp_path / variable))
    assert not git_environment().keys() & listed


@pytest.mark.parametrize("missing", VARIABLES_THAT_AIM_GIT_ELSEWHERE)
def test_git_refuses_to_run_when_git_lists_too_few_local_variables(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    def git_listing(*names: str) -> None:
        listing = "".join(f"{name}\n" for name in names)

        def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 0, stdout=listing, stderr="")

        monkeypatch.setattr(subprocess, "run", run)

    # Control: a list that names all seven, plus one more, passes.
    git_listing(*VARIABLES_THAT_AIM_GIT_ELSEWHERE, "GIT_PREFIX")
    assert repository_local_git_variables.__wrapped__() == {
        *VARIABLES_THAT_AIM_GIT_ELSEWHERE,
        "GIT_PREFIX",
    }
    git_listing(
        *(name for name in VARIABLES_THAT_AIM_GIT_ELSEWHERE if name != missing),
        "GIT_PREFIX",
    )
    with pytest.raises(AssertionError, match=f"omits \\['{missing}'\\]"):
        repository_local_git_variables.__wrapped__()


# Where each variable that locates a repository points inside a hook, relative
# to the hook's repository.
HOOK_REPOSITORY_PATHS = {
    "GIT_COMMON_DIR": ".git",
    "GIT_DIR": ".git",
    "GIT_INDEX_FILE": ".git/index",
    "GIT_OBJECT_DIRECTORY": ".git/objects",
    "GIT_WORK_TREE": ".",
}


def repository_state(repository: Path) -> tuple[str, bytes, str]:
    return (
        fixture_git(repository, "for-each-ref"),
        (repository / ".git" / "index").read_bytes(),
        fixture_git(repository, "count-objects", "-v"),
    )


@pytest.mark.parametrize(
    "variables",
    [("GIT_DIR", "GIT_INDEX_FILE"), *((name,) for name in sorted(HOOK_REPOSITORY_PATHS))],
    ids="+".join,
)
def test_git_commands_stay_in_their_repository_inside_a_git_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variables: tuple[str, ...]
) -> None:
    # The hook's repository holds a commit, a pin of its own and a staged file,
    # so a command that strays into it changes its refs, index or objects, or
    # reads its pin.
    hook_repository = tmp_path / "hook"
    hook_repository.mkdir()
    fixture_git(hook_repository, "init", "--quiet", "--initial-branch=main")
    commit_fixture_pin(hook_repository, "3" * 40)
    (hook_repository / "staged.txt").write_text("staged\n")
    fixture_git(hook_repository, "add", "staged.txt")
    before = repository_state(hook_repository)
    for variable in variables:
        monkeypatch.setenv(
            variable, str(hook_repository / HOOK_REPOSITORY_PATHS[variable])
        )
    repository = tmp_path / "repository"
    repository.mkdir()
    fixture_git(repository, "init", "--quiet", "--initial-branch=main")
    commit_fixture_pin(repository, "1" * 40)
    assert encoders_pinned_through("HEAD", repository) == {"1" * 40}
    assert repository_state(hook_repository) == before


def write_workflow_pin(root: Path, encoder_ref: str) -> None:
    """Pin the encoder in repository-checks.yml, as this repository does."""
    workflow = root / WORKFLOW
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(
        yaml.safe_dump(
            {"jobs": {"validate": {"with": {"axiom-encode-ref": encoder_ref}}}}
        )
    )


def write_toolchain_pin(root: Path, encoder_ref: str) -> None:
    """Pin the encoder in workflow-toolchain.toml, as rulespec-us does."""
    write_workflow_pin(
        root, "${{ needs.workflow-toolchain.outputs.axiom_encode_ref }}"
    )
    toolchain = root / WORKFLOW_TOOLCHAIN
    toolchain.parent.mkdir(parents=True, exist_ok=True)
    toolchain.write_text(f'[workflow_toolchain]\naxiom_encode_ref = "{encoder_ref}"\n')


PIN_LAYOUTS = {"workflow": write_workflow_pin, "toolchain": write_toolchain_pin}


# The encoder reads manifests from APPLIED_ENCODING_MANIFEST_DIR,
# Path(".axiom") / "encoding-manifests" in src/axiom_encode/cli.py at every
# listed pin. The fixtures write there, apart from MANIFEST_ROOT, so a gate
# that looks anywhere else fails them.
ENCODER_MANIFEST_DIR = Path(".axiom") / "encoding-manifests"


def write_manifest(root: Path, relative: str, content: bytes) -> None:
    path = root / ENCODER_MANIFEST_DIR / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def refusal(manifest: str, encoder_ref: str) -> str:
    return (
        f"{manifest}: the pinned encoder {encoder_ref[:8]} does not verify a "
        "change that adds only manifests"
    )


def path_order(relative: str) -> tuple[str, ...]:
    return PurePosixPath(relative).parts


# A change that adds only this manifest names a module that exists and does
# not change, and carries no signature, file hashes or producer.
UNSIGNED_MODULE = "rw/statutes/example/rule.yaml"
UNSIGNED_MANIFEST = "rw/statutes/example/rule.json"
UNSIGNED_CONTENT = json.dumps(
    {
        "schema_version": "axiom-encode/applied-rulespec/v5",
        "applied_files": [{"path": UNSIGNED_MODULE}],
    }
).encode()


def write_unsigned_manifest_only_change(root: Path) -> None:
    for module in (UNSIGNED_MODULE, UNSIGNED_MODULE.replace(".yaml", ".test.yaml")):
        (root / module).parent.mkdir(parents=True, exist_ok=True)
        (root / module).write_text("format: rulespec/v1\n")
    write_manifest(root, UNSIGNED_MANIFEST, UNSIGNED_CONTENT)


@pytest.mark.parametrize("layout", sorted(PIN_LAYOUTS))
@pytest.mark.parametrize(
    "encoder_ref", sorted(ENCODERS_THAT_SKIP_MANIFEST_ONLY_CHANGES)
)
def test_an_unsigned_manifest_is_refused_while_the_guard_skips_it(
    tmp_path: Path, encoder_ref: str, layout: str
) -> None:
    PIN_LAYOUTS[layout](tmp_path, encoder_ref)
    write_unsigned_manifest_only_change(tmp_path)
    assert manifests_the_guard_skips(tmp_path) == [
        refusal(UNSIGNED_MANIFEST, encoder_ref)
    ]


@pytest.mark.parametrize("layout", sorted(PIN_LAYOUTS))
@pytest.mark.parametrize(
    "encoder_ref",
    [FIRST_ENCODER_THAT_CHECKS_MANIFEST_ONLY_CHANGES, "0" * 40, "f" * 40],
)
def test_an_unlisted_encoder_leaves_manifests_to_the_guard(
    tmp_path: Path, encoder_ref: str, layout: str
) -> None:
    PIN_LAYOUTS[layout](tmp_path, encoder_ref)
    write_unsigned_manifest_only_change(tmp_path)
    assert manifests_the_guard_skips(tmp_path) == []


# Whatever a manifest holds, the skipping guard never reads it.
MANIFEST_CONTENTS = {
    "rw/statutes/a/rule.json": json.dumps(
        {
            "schema_version": "axiom-encode/applied-rulespec/v5",
            "applied_files": [
                {"path": "rw/statutes/a/rule.yaml", "sha256": "0" * 64}
            ],
            "signature": {"algorithm": "ed25519-domain-v1", "value": "AAAA"},
        }
    ).encode(),
    "rw/statutes/b/rule.json": json.dumps(
        {"schema_version": "axiom-encode/applied-rulespec/v1"}
    ).encode(),
    "rw/regulations/c/rule.json": b"{",
    "rw/policies/d/rule.json": b"",
    "rw/legislation/e/rule.json": "{}".encode("utf-16"),
    "rw/statutes/f/rule.json": b"\xff\xfe\xfd",
    "rw/statutes/g/rule.json": b"[]",
    "rw/statutes/a/rule.test.json": b"{}",
    # Path order compares part by part, so a/ sorts before a-b/.
    "rw/statutes/a-b/rule.json": b"{}",
    "rw/statutes/h/.hidden.json": b"{}",
    "programs/i.json": b"{}",
    "top-level.json": b"{}",
    "deep/a/b/c/d/e/f/rule.json": b"{}",
}


@pytest.mark.parametrize(
    "encoder_ref", sorted(ENCODERS_THAT_SKIP_MANIFEST_ONLY_CHANGES)
)
def test_every_manifest_gets_a_line_while_the_guard_skips_them(
    tmp_path: Path, encoder_ref: str
) -> None:
    write_workflow_pin(tmp_path, encoder_ref)
    for manifest, content in MANIFEST_CONTENTS.items():
        write_manifest(tmp_path, manifest, content)
    assert manifests_the_guard_skips(tmp_path) == [
        refusal(manifest, encoder_ref)
        for manifest in sorted(MANIFEST_CONTENTS, key=path_order)
    ]


def test_a_link_named_like_a_manifest_gets_a_line(tmp_path: Path) -> None:
    # git tracks a symbolic link as a file, so the guard would see this path.
    encoder_ref = sorted(ENCODERS_THAT_SKIP_MANIFEST_ONLY_CHANGES)[0]
    write_workflow_pin(tmp_path, encoder_ref)
    link = tmp_path / ENCODER_MANIFEST_DIR / "rw/statutes/a/rule.json"
    link.parent.mkdir(parents=True)
    link.symlink_to(tmp_path / "nowhere.json")
    assert manifests_the_guard_skips(tmp_path) == [
        refusal("rw/statutes/a/rule.json", encoder_ref)
    ]


def test_lines_do_not_depend_on_the_order_the_filesystem_lists_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    encoder_ref = sorted(ENCODERS_THAT_SKIP_MANIFEST_ONLY_CHANGES)[0]
    write_workflow_pin(tmp_path, encoder_ref)
    for manifest, content in MANIFEST_CONTENTS.items():
        write_manifest(tmp_path, manifest, content)
    listed = manifests_the_guard_skips(tmp_path)
    rglob = Path.rglob
    monkeypatch.setattr(
        Path, "rglob", lambda self, pattern: reversed(list(rglob(self, pattern)))
    )
    assert manifests_the_guard_skips(tmp_path) == listed


def test_a_tree_without_manifests_passes_while_the_guard_skips_them(
    tmp_path: Path,
) -> None:
    write_workflow_pin(tmp_path, sorted(ENCODERS_THAT_SKIP_MANIFEST_ONLY_CHANGES)[0])
    assert manifests_the_guard_skips(tmp_path) == []
    (tmp_path / ENCODER_MANIFEST_DIR).mkdir(parents=True)
    assert manifests_the_guard_skips(tmp_path) == []


# Paths a tree can hold under the manifest root. The guard counts the `.json`
# ones as manifests and ignores the rest.
TREE_PATHS = (
    "rw/statutes/a/rule.json",
    "rw/regulations/b/rule.json",
    "rw/statutes/a/rule.test.json",
    "programs/c.json",
    "rw/statutes/a/notes.md",
    ".DS_Store",
)


def test_lines_name_exactly_the_json_paths_in_every_tree(tmp_path: Path) -> None:
    """Build every subset of TREE_PATHS under both pin layouts.

    At a skipping pin, the lines name each `.json` path once, in path order.
    At any other pin there are none. The file contents and the order the
    files appear in change nothing.
    """
    skipping = sorted(ENCODERS_THAT_SKIP_MANIFEST_ONLY_CHANGES)[0]
    for mask in range(1 << len(TREE_PATHS)):
        chosen = [path for bit, path in enumerate(TREE_PATHS) if mask >> bit & 1]
        manifests = sorted(
            (path for path in chosen if path.endswith(".json")), key=path_order
        )
        for layout, write_pin in PIN_LAYOUTS.items():
            for encoder_ref in (
                skipping,
                FIRST_ENCODER_THAT_CHECKS_MANIFEST_ONLY_CHANGES,
            ):
                for reverse, content in ((False, b""), (True, UNSIGNED_CONTENT)):
                    root = tmp_path / f"{mask}-{layout}-{encoder_ref[:8]}-{reverse}"
                    write_pin(root, encoder_ref)
                    for path in reversed(chosen) if reverse else chosen:
                        write_manifest(root, path, content)
                    expected = (
                        [refusal(path, encoder_ref) for path in manifests]
                        if encoder_ref == skipping
                        else []
                    )
                    assert manifests_the_guard_skips(root) == expected, (
                        chosen,
                        layout,
                        encoder_ref,
                        reverse,
                    )
