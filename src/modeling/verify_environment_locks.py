"""Fail-closed verification of complete hashed environment locks and reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

import yaml

from src.modeling.model_execution_contract import file_sha256, load_contract


ROOT = Path(__file__).resolve().parents[2]
PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([^ \\\n]+)")


def parsed_pins(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [index for index, line in enumerate(lines) if PIN.match(line)]
    for position, start in enumerate(starts):
        match = PIN.match(lines[start])
        assert match is not None
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        stanza = "\n".join(lines[start:end])
        if "--hash=sha256:" not in stanza:
            raise ValueError(f"Unhashed locked requirement: {match.group(1)}")
        key = match.group(1).lower()
        if key in pins:
            raise ValueError(f"Duplicate locked requirement: {key}")
        pins[key] = match.group(2)
    if not pins or "not pinned" in path.read_text(encoding="utf-8").lower():
        raise ValueError(f"Incomplete lockfile: {path}")
    return pins


def verify(manifest_path: Path) -> dict[str, Any]:
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    contract = load_contract()
    checks: dict[str, Any] = {}
    for role in ("classical", "qnn_mlp"):
        item = manifest["environments"][role]
        lock_path = ROOT / item["lockfile"]
        report_path = ROOT / item["fresh_install_import_smoke_report"]
        pins = parsed_pins(lock_path)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        expected = contract["software_environment_identity"][f"{role}_expected"]
        expected_packages = {key.lower(): str(value) for key, value in expected["packages"].items()}
        checks[role] = {
            "lock_sha256_matches": file_sha256(lock_path) == item["lockfile_sha256"],
            "report_sha256_matches": file_sha256(report_path) == item["fresh_install_import_smoke_report_sha256"],
            "python_matches": report["runtime_identity"]["python_version"]
            == str(expected["python"]),
            "root_packages_match": all(
                pins.get(package) == version
                for package, version in expected_packages.items()
            ),
            "all_locked_requirements_hashed": True,
            "locked_distribution_count": len(pins),
            "fresh_install_import_status": report["status"],
            "exact_installed_distribution_match": report.get(
                "lock_verification", {}
            ).get("status")
            == "EXACT_MATCH",
            "audited_lock_sha256_matches": report.get("lock_verification", {}).get(
                "lockfile_sha256"
            )
            == item["lockfile_sha256"],
            "audited_distribution_count_matches": report.get(
                "lock_verification", {}
            ).get("installed_distribution_count_excluding_pip")
            == len(pins),
        }
    ready = all(
        row["lock_sha256_matches"]
        and row["report_sha256_matches"]
        and row["python_matches"]
        and row["root_packages_match"]
        and row["fresh_install_import_status"] == "READY"
        and row["exact_installed_distribution_match"]
        and row["audited_lock_sha256_matches"]
        and row["audited_distribution_count_matches"]
        for row in checks.values()
    )
    return {
        "schema_version": 1,
        "status": "PASS" if ready else "FAIL",
        "checks": checks,
        "project_data_opened": False,
        "model_fit_performed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "configs/model_environments_v1_0_0.yaml",
    )
    args = parser.parse_args()
    report = verify(args.manifest)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    raise SystemExit(0 if report["status"] == "PASS" else 2)


if __name__ == "__main__":
    main()
