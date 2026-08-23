"""Verify the compact, development-only post-coarse result freeze.

The verifier reads only 2011--2020 development artifacts and compact reports.
It never opens protected-period inputs and never writes project artifacts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "configs/post_coarse_v1_3_0_results_freeze_manifest.yaml"


class PostCoarseFreezeError(RuntimeError):
    """Raised when a frozen result artifact or invariant does not match."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PostCoarseFreezeError(f"Expected a JSON object: {path}")
    return payload


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PostCoarseFreezeError(message)


def _verify_file_entry(entry: Mapping[str, Any]) -> Path:
    path = ROOT / str(entry["path"])
    _require(path.is_file(), f"Missing frozen artifact: {path}")
    _require(path.stat().st_size == int(entry["bytes"]), f"Size mismatch: {path}")
    _require(_sha256(path) == str(entry["sha256"]), f"SHA-256 mismatch: {path}")
    expected_status = entry.get("json_status")
    if expected_status is not None:
        _require(
            _load_json(path).get("status") == expected_status,
            f"JSON status mismatch: {path}",
        )
    expected_rows = entry.get("csv_data_rows")
    if expected_rows is not None:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        _require(len(rows) == int(expected_rows), f"CSV row-count mismatch: {path}")
    return path


def verify_post_coarse_results_freeze(
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    _require(isinstance(manifest, dict), "Freeze manifest must be a mapping.")
    freeze = manifest.get("post_coarse_results_freeze") or {}
    _require(freeze.get("status") == "FROZEN", "Result freeze is not FROZEN.")
    _require(
        freeze.get("verdict") == "POST_COARSE_V1_3_0_RESULTS_INTEGRITY_PASS",
        "Unexpected result-freeze verdict.",
    )
    _require(
        freeze.get("protected_feature_years_opened") is False,
        "Freeze declares protected-period access.",
    )

    verified_files = 0
    for section in (
        "compact_model_run_artifacts",
        "report_artifacts",
        "verification_sources",
    ):
        entries = manifest.get(section) or []
        _require(isinstance(entries, list) and entries, f"Empty freeze section: {section}")
        for entry in entries:
            _verify_file_entry(entry)
            verified_files += 1

    output_dir = ROOT / "data/model_runs/post_coarse_v1_3_0"
    report_dir = ROOT / "reports/post_coarse_v1_3_0"
    run = _load_json(output_dir / "run_manifest.json")
    confirmation = _load_json(output_dir / "confirmation_phase_manifest.json")
    ranking = _load_json(output_dir / "final_primary_development_ranking.json")
    neural = _load_json(output_dir / "neural_comparison_manifest.json")
    bootstrap = _load_json(
        output_dir / "neural_comparison_clustered_bootstrap.json"
    )
    ledger = _load_json(output_dir / "qnn_confirmation_resource_ledger.json")
    report = _load_json(report_dir / "report_manifest.json")

    for name, payload in (
        ("run", run),
        ("confirmation", confirmation),
        ("ranking", ranking),
        ("neural comparison", neural),
        ("bootstrap", bootstrap),
        ("report", report),
    ):
        _require(payload.get("status") == "COMPLETE", f"{name} is not COMPLETE.")
        _require(
            payload.get("protected_feature_years_opened") is False,
            f"{name} has an invalid protected-period flag.",
        )

    expected = manifest["frozen_counts"]
    _require(
        len(confirmation.get("primary_confirmed_result_references") or [])
        == int(expected["primary_confirmation_slots"]),
        "Primary confirmation count mismatch.",
    )
    _require(
        len(confirmation.get("qnn_confirmed_result_references") or [])
        == int(expected["qnn_confirmation_slots"]),
        "QNN confirmation count mismatch.",
    )
    _require(
        len(confirmation.get("extra_seed_candidate_result_references") or [])
        == int(expected["extra_seed_candidate_results"]),
        "Extra-seed result count mismatch.",
    )
    _require(
        len(ranking.get("family_representatives") or [])
        == int(expected["final_family_representatives"]),
        "Final representative count mismatch.",
    )
    _require(
        len(ranking.get("calibration_and_threshold") or [])
        == int(expected["primary_calibrations_and_thresholds"]),
        "Primary calibration count mismatch.",
    )
    _require(
        len(neural.get("rows") or []) == int(expected["neural_comparison_rows"]),
        "Neural-comparison row count mismatch.",
    )
    _require(
        len(neural.get("calibration_and_threshold") or [])
        == int(expected["neural_calibrations_and_thresholds"]),
        "Neural calibration count mismatch.",
    )

    method = bootstrap.get("method") or {}
    _require(
        int(method.get("replicates_requested", -1))
        == int(expected["bootstrap_replicates"]),
        "Bootstrap requested-replicate count mismatch.",
    )
    _require(
        int(method.get("replicates_valid", -1))
        == int(expected["bootstrap_valid_replicates"]),
        "Bootstrap valid-replicate count mismatch.",
    )
    _require(
        int(method.get("replicates_degenerate_discarded", -1))
        == int(expected["bootstrap_degenerate_replicates"]),
        "Bootstrap degenerate-replicate count mismatch.",
    )
    _require(
        len(bootstrap.get("rows") or []) == int(expected["bootstrap_rows"]),
        "Bootstrap result-row count mismatch.",
    )

    first_attempt = int(expected["qnn_confirmation_first_global_attempt"])
    attempts = [
        attempt
        for attempt in ledger.get("attempts") or []
        if int(attempt.get("global_attempt", 0)) >= first_attempt
    ]
    _require(
        len(attempts) == int(expected["qnn_confirmation_fold_fits"]),
        "QNN confirmation attempt count mismatch.",
    )
    _require(
        all(
            attempt.get("status") == "COMPLETED"
            and attempt.get("outcome") == "COMPLETE"
            and attempt.get("retry_reason") == "INITIAL"
            for attempt in attempts
        ),
        "QNN confirmation contains a failed or retried attempt.",
    )
    _require(ledger.get("limit_reached") is False, "QNN resource limit was reached.")

    hash_fields = {
        "refinement_phase_manifest_sha256": "refinement_phase_manifest.json",
        "qnn_phase_manifest_sha256": "qnn_phase_manifest.json",
        "confirmation_classical_phase_manifest_sha256": (
            "confirmation_classical_phase_manifest.json"
        ),
        "qnn_confirmation_resource_ledger_sha256": (
            "qnn_confirmation_resource_ledger.json"
        ),
        "confirmation_phase_manifest_sha256": "confirmation_phase_manifest.json",
        "final_primary_development_ranking_sha256": (
            "final_primary_development_ranking.json"
        ),
        "neural_comparison_manifest_sha256": "neural_comparison_manifest.json",
        "neural_comparison_clustered_bootstrap_sha256": (
            "neural_comparison_clustered_bootstrap.json"
        ),
    }
    for field, filename in hash_fields.items():
        _require(
            run.get(field) == _sha256(output_dir / filename),
            f"Run-manifest hash mismatch: {field}",
        )
    _require(
        run.get("neural_comparison_inference_completed") is True
        and run.get("neural_comparison_inference_status") == "COMPLETE",
        "Run manifest does not freeze completed inference.",
    )

    for filename, expected_sha in (report.get("source_manifest_sha256") or {}).items():
        _require(
            _sha256(output_dir / filename) == expected_sha,
            f"Report source hash mismatch: {filename}",
        )
    generated_tables = sorted(path.name for path in report_dir.glob("*.csv"))
    _require(
        generated_tables == list(report.get("generated_tables") or []),
        "Report table inventory mismatch.",
    )

    access = manifest.get("access_boundary") or {}
    _require(
        access.get("this_freeze_authorizes_2021_2024_access") is False,
        "Result freeze must not authorize protected-period access.",
    )

    return {
        "schema_version": 1,
        "status": "PASS",
        "verdict": freeze["verdict"],
        "verified_files": verified_files,
        "qnn_confirmation_fold_fits": len(attempts),
        "bootstrap_valid_replicates": int(method["replicates_valid"]),
        "report_tables": len(generated_tables),
        "protected_feature_years_opened": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    result = verify_post_coarse_results_freeze(args.manifest)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
