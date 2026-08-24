"""Validate and execute only reviewed test-access profiles.

The guard deliberately exposes no option for arbitrary pytest targets.  A run
can select only a named profile committed in the test-access manifest.  Any
profile containing a protected/gated module is rejected before pytest starts.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Mapping

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "configs/test_access_manifest_v1_0_0.yaml"
ALLOWED_CATEGORIES = {
    "synthetic/config-only",
    "development-only",
    "protected/gated",
}
RUNNABLE_CATEGORIES = {"synthetic/config-only", "development-only"}
SAFE_RELATIVE_PREFIXES = (
    ".venv-classical/",
    ".venv-qnn-mlp/",
    "configs/",
    "data/",
    "docs/",
    "environments/",
    "notebooks/",
    "reports/",
    "scripts/",
    "src/",
    "tests/",
)


class TestAccessGuardError(RuntimeError):
    """Raised when a manifest or requested run violates the access contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TestAccessGuardError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_yaml(path: Path) -> dict[str, Any]:
    _require(path.is_file() and not path.is_symlink(), f"Missing regular file: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), f"Expected YAML mapping: {path}")
    return payload


def _relative_path(value: object, *, field: str) -> str:
    text = str(value)
    pure = PurePosixPath(text)
    _require(text == pure.as_posix(), f"{field} must use normalized POSIX syntax: {text}")
    _require(not pure.is_absolute(), f"{field} must be repository-relative: {text}")
    _require(".." not in pure.parts, f"{field} may not escape the repository: {text}")
    _require(not any(char in text for char in "*?[]{}"), f"{field} may not contain globs: {text}")
    _require(text.startswith(SAFE_RELATIVE_PREFIXES), f"{field} has an unsupported prefix: {text}")
    return text


def _git(*args: str, root: Path = ROOT) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )
    _require(
        completed.returncode == 0,
        completed.stderr.strip() or f"Git command failed: {' '.join(args)}",
    )
    return completed.stdout.strip()


def tracked_test_paths(root: Path = ROOT) -> list[str]:
    # Include a newly created Step 7A guard regression before its first commit.
    # Canonical execution separately requires every reviewed file to be tracked.
    output = _git(
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "tests/test_*.py",
        root=root,
    )
    return sorted(line for line in output.splitlines() if line)


def _test_index(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    modules = manifest.get("test_modules")
    _require(isinstance(modules, list) and modules, "test_modules must be a non-empty list")
    index: dict[str, Mapping[str, Any]] = {}
    for item in modules:
        _require(isinstance(item, dict), "Each test_modules entry must be a mapping")
        test_id = str(item.get("id", ""))
        _require(test_id and test_id not in index, f"Duplicate or empty test id: {test_id}")
        index[test_id] = item
    return index


def validate_manifest(manifest: Mapping[str, Any], *, root: Path = ROOT) -> dict[str, int]:
    _require(manifest.get("schema_version") == 1, "Unsupported test-access schema")
    identity = manifest.get("test_access_manifest") or {}
    _require(identity.get("id") == "test_access_manifest", "Unexpected manifest id")
    _require(str(identity.get("version")) == "1.0.0", "Unexpected manifest version")
    _require(
        identity.get("execution_authorized") is False,
        "The v1.0.0 manifest must remain fail-closed after incident v1.2.0",
    )

    exception = manifest.get("procedural_exception") or {}
    _require(exception.get("authorized_by_user") is True, "Same-session exception is not explicit")
    _require(
        exception.get("review_kind") == "same_session_technical_review",
        "Review must be labelled same_session_technical_review",
    )
    _require(exception.get("independent_review_claimed") is False, "Review may not be called independent")
    _require(exception.get("step_6_blockers_waived") is False, "Step 6 blockers may not be erased")

    environments = manifest.get("environments") or {}
    _require(isinstance(environments, dict) and environments, "No environments declared")
    for environment_id, environment in environments.items():
        _require(isinstance(environment, dict), f"Invalid environment: {environment_id}")
        interpreter = _relative_path(environment.get("interpreter"), field="interpreter")
        _require((root / interpreter).is_file(), f"Missing interpreter: {interpreter}")
        _require(environment.get("owner"), f"Missing environment owner: {environment_id}")

    contracts = manifest.get("input_contracts") or {}
    _require(isinstance(contracts, dict) and contracts, "No input contracts declared")
    for contract_id, contract in contracts.items():
        _require(isinstance(contract, dict), f"Invalid input contract: {contract_id}")
        paths = contract.get("exact_repository_paths") or []
        _require(isinstance(paths, list), f"Invalid exact_repository_paths: {contract_id}")
        normalized = [_relative_path(path, field=f"input_contracts.{contract_id}") for path in paths]
        _require(len(normalized) == len(set(normalized)), f"Duplicate path in contract: {contract_id}")
        for relative in normalized:
            _require((root / relative).exists(), f"Missing declared input: {relative}")
        authority = contract.get("pinned_path_authority")
        if authority is not None:
            _require(isinstance(authority, dict), f"Invalid pinned authority: {contract_id}")
            relative = _relative_path(authority.get("path"), field=f"authority.{contract_id}")
            _require(_sha256(root / relative) == authority.get("sha256"), f"Authority hash mismatch: {relative}")

    tests = _test_index(manifest)
    manifest_paths: list[str] = []
    category_counts = {category: 0 for category in ALLOWED_CATEGORIES}
    for test_id, item in tests.items():
        path = _relative_path(item.get("path"), field=f"test_modules.{test_id}.path")
        manifest_paths.append(path)
        _require(path.startswith("tests/test_") and path.endswith(".py"), f"Invalid test path: {path}")
        _require((root / path).is_file(), f"Missing test module: {path}")
        _require(item.get("pytest_target") == path, f"pytest_target must equal path: {test_id}")
        category = item.get("category")
        _require(category in ALLOWED_CATEGORIES, f"Invalid category for {test_id}: {category}")
        category_counts[str(category)] += 1
        _require(item.get("environment") in environments, f"Unknown environment for {test_id}")
        _require(item.get("input_contract") in contracts, f"Unknown input contract for {test_id}")
        operations = item.get("operations")
        _require(isinstance(operations, list) and operations, f"Missing operations for {test_id}")
        if category == "protected/gated":
            _require(item.get("enabled") is False, f"Protected test must be disabled: {test_id}")
        else:
            _require(item.get("enabled") is True, f"Runnable test must be enabled: {test_id}")

    _require(sorted(manifest_paths) == tracked_test_paths(root), "Manifest does not exactly cover tracked test inventory")

    profiles = manifest.get("profiles") or {}
    _require(isinstance(profiles, dict) and profiles, "No run profiles declared")
    for profile_id, profile in profiles.items():
        _require(isinstance(profile, dict), f"Invalid profile: {profile_id}")
        ids = profile.get("test_ids")
        _require(isinstance(ids, list) and ids, f"Empty profile: {profile_id}")
        _require(len(ids) == len(set(ids)), f"Duplicate test id in profile: {profile_id}")
        for test_id in ids:
            _require(test_id in tests, f"Unknown test id in profile {profile_id}: {test_id}")
            _require(tests[test_id]["category"] in RUNNABLE_CATEGORIES, f"Protected test in profile {profile_id}: {test_id}")
            _require(tests[test_id]["enabled"] is True, f"Disabled test in profile {profile_id}: {test_id}")
        if profile_id == "synthetic-config-only":
            _require(
                all(tests[test_id]["category"] == "synthetic/config-only" for test_id in ids),
                "Synthetic profile contains development-only tests",
            )

    review = manifest.get("review") or {}
    review_allowlist = _relative_path(review.get("exact_allowlist"), field="review.exact_allowlist")
    _require((root / review_allowlist).is_file(), "Missing exact review allowlist")
    review_payload = _load_yaml(root / review_allowlist)
    review_identity = review_payload.get("test_access_review_allowlist") or {}
    _require(review_identity.get("id") == "test_access_review_allowlist", "Unexpected review allowlist id")
    _require(str(review_identity.get("version")) == "1.0.0", "Unexpected review allowlist version")
    content_paths = review_payload.get("exact_content_paths") or []
    _require(isinstance(content_paths, list) and content_paths, "Review content allowlist is empty")
    normalized_review_paths = [
        _relative_path(path, field="review.exact_content_paths") for path in content_paths
    ]
    _require(len(normalized_review_paths) == len(set(normalized_review_paths)), "Duplicate review content path")
    _require(set(manifest_paths).issubset(normalized_review_paths), "Review allowlist does not cover every test module")
    _require(
        not any(path.startswith(("data/", "reports/")) for path in normalized_review_paths),
        "Step 7B content review may not read data or report artifacts",
    )
    for relative in normalized_review_paths:
        _require((root / relative).is_file(), f"Missing review content path: {relative}")
    _require(review_payload.get("tracked_fixture_paths") == [], "Unexpected tracked fixture content")
    return category_counts


def _require_review_pass(manifest_path: Path, manifest: Mapping[str, Any], *, root: Path) -> None:
    review = manifest.get("review") or {}
    result_relative = _relative_path(review.get("result_path"), field="review.result_path")
    result_path = root / result_relative
    payload = _load_yaml(result_path)
    _require(payload.get("verdict") == "TEST_ACCESS_REVIEW_PASS", "Canonical suite requires TEST_ACCESS_REVIEW_PASS")
    _require(payload.get("review_kind") == "same_session_technical_review", "Review kind mismatch")
    _require(payload.get("independent_review_claimed") is False, "Review may not claim independence")
    _require(payload.get("subject_manifest_sha256") == _sha256(manifest_path), "Reviewed manifest hash mismatch")
    guard_relative = str(Path(__file__).resolve().relative_to(root))
    _require(payload.get("subject_guard_sha256") == _sha256(root / guard_relative), "Reviewed guard hash mismatch")
    subject_commit = str(payload.get("subject_commit", ""))
    _require(len(subject_commit) == 40, "Review subject commit must be a full Git id")
    _git("merge-base", "--is-ancestor", subject_commit, "HEAD", root=root)
    for relative in (str(manifest_path.relative_to(root)), guard_relative, result_relative):
        _git("ls-files", "--error-unmatch", "--", relative, root=root)
        _require(not _git("status", "--porcelain", "--", relative, root=root), f"Reviewed file is dirty: {relative}")


def selected_tests(manifest: Mapping[str, Any], profile_id: str, order: str) -> list[Mapping[str, Any]]:
    profiles = manifest.get("profiles") or {}
    _require(profile_id in profiles, f"Unknown profile: {profile_id}")
    index = _test_index(manifest)
    selected = [index[test_id] for test_id in profiles[profile_id]["test_ids"]]
    _require(all(item["category"] in RUNNABLE_CATEGORIES for item in selected), "Protected/gated test selection refused")
    if order == "reverse":
        selected.reverse()
    return selected


def _sanitized_environment(temp_root: Path, root: Path) -> dict[str, str]:
    return {
        "HOME": str(temp_root),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "LOKY_MAX_CPU_COUNT": "1",
        "MPLCONFIGDIR": str(temp_root / "matplotlib"),
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONPATH": str(root),
        "QNN_TEST_ACCESS_GUARD": "1",
        "TMPDIR": str(temp_root),
        "VECLIB_MAXIMUM_THREADS": "1",
    }


def run_profile(
    manifest_path: Path,
    manifest: Mapping[str, Any],
    profile_id: str,
    order: str,
    *,
    root: Path = ROOT,
) -> int:
    validate_manifest(manifest, root=root)
    identity = manifest.get("test_access_manifest") or {}
    _require(
        identity.get("execution_authorized") is True,
        "Manifest execution is blocked by data access incident v1.2.0",
    )
    profile = manifest["profiles"].get(profile_id) or {}
    if profile.get("requires_review_pass"):
        _require_review_pass(manifest_path, manifest, root=root)
    selected = selected_tests(manifest, profile_id, order)
    environments = manifest["environments"]

    temp_parent = Path(str(manifest["output_policy"]["temporary_parent"]))
    _require(temp_parent == Path("/private/tmp"), "Only /private/tmp is permitted for suite outputs")
    temp_root = Path(tempfile.mkdtemp(prefix="qnn-safe-suite-v1-0-0-", dir=temp_parent))
    print(f"TEST_ACCESS_TEMP_ROOT={temp_root}")
    try:
        return_code = 0
        for item in selected:
            environment_id = str(item["environment"])
            target = str(item["pytest_target"])
            interpreter = root / str(environments[environment_id]["interpreter"])
            command = [
                str(interpreter),
                "-m",
                "src.testing.compat_test_runner",
                target,
            ]
            print(
                f"TEST_ACCESS_PROFILE={profile_id} ORDER={order} "
                f"ENV={environment_id} TEST_ID={item['id']}"
            )
            print("COMMAND=" + " ".join(command))
            completed = subprocess.run(
                command,
                cwd=root,
                env=_sanitized_environment(temp_root, root),
                check=False,
            )
            if completed.returncode:
                return_code = 1
        return return_code
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    run = subparsers.add_parser("run")
    run.add_argument("--profile", required=True)
    run.add_argument("--order", choices=("manifest", "reverse"), default="manifest")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    manifest_path = args.manifest.resolve()
    try:
        _require(manifest_path.is_relative_to(ROOT), "Manifest must be inside the repository")
        manifest = _load_yaml(manifest_path)
        if args.command == "validate":
            counts = validate_manifest(manifest)
            print("TEST_ACCESS_MANIFEST_VALID " + " ".join(f"{key}={counts[key]}" for key in sorted(counts)))
            return 0
        return run_profile(manifest_path, manifest, args.profile, args.order)
    except TestAccessGuardError as error:
        print(f"TEST_ACCESS_GUARD_REFUSED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
