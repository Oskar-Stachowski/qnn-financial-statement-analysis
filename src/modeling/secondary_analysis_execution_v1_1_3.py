"""Robustness-signal source amendment for secondary execution v1.1.3.

The frozen production target-application projection already contains the D1--D5
signals for every supervised-sample row.  This layer uses that exact, previously
pinned file and avoids deserializing the narrower interim target source.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yaml

from src.modeling import secondary_analysis_execution as base
from src.modeling import secondary_analysis_execution_v1_1_1 as v111


ROOT = base.ROOT
DEFAULT_CONFIG = (
    ROOT / "configs/secondary_development_execution_v1_1_3_signal_source_fix.yaml"
)
DEFAULT_OUTPUT = ROOT / "data/model_runs/secondary_development_v1_1_3"
_BASE_PREFLIGHT_CONTEXT = v111._BASE_PREFLIGHT_CONTEXT


def _merge(base_value: Any, overlay_value: Any) -> Any:
    if isinstance(base_value, Mapping) and isinstance(overlay_value, Mapping):
        result = dict(base_value)
        for key, value in overlay_value.items():
            result[key] = _merge(result.get(key), value)
        return result
    return overlay_value


def load_execution_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    payload = yaml.safe_load(path.resolve().read_text(encoding="utf-8"))
    base._require(isinstance(payload, dict), "v1.1.3 config must be a mapping.")
    extension = payload.get("extends")
    base._require(isinstance(extension, Mapping), "v1.1.3 must extend v1.1.1.")
    base_path = (ROOT / str(extension["path"])).resolve()
    expected = ROOT / "configs/secondary_development_execution_v1_1_1_input_key_fix.yaml"
    base._require(base_path == expected, "Wrong v1.1.3 amendment base.")
    base._require(base.file_sha256(base_path) == str(extension["sha256"]), "v1.1.1 config hash mismatch.")
    inherited = v111.load_execution_config(base_path)
    merged = _merge(inherited, {key: value for key, value in payload.items() if key != "extends"})
    section = merged["secondary_development_execution"]
    base._require(section["id"] == "secondary_development_execution_v1_1_3", "Wrong v1.1.3 ID.")
    base._require(section["version"] == "1.1.3", "Wrong v1.1.3 version.")
    base._require(section["status"] == "executable_signal_source_amendment_frozen", "v1.1.3 is not frozen.")
    amendment = section["signal_source_amendment"]
    base._require(amendment["scope"] == "robustness_signal_source_only", "v1.1.3 scope changed.")
    base._require(amendment["additional_interim_target_deserialization"] is False, "Interim target read enabled.")
    for field in (
        "target_values_changed", "sample_membership_changed", "fold_policy_changed",
        "task_roster_changed", "methodology_changed",
    ):
        base._require(amendment[field] is False, f"Forbidden v1.1.3 change: {field}")
    return merged


def verify_amendment_authority(config: Mapping[str, Any]) -> dict[str, str]:
    authority = config["secondary_development_execution"]["amendment_authority_v1_1_3"]
    verified: dict[str, str] = {}
    for name, item in authority.items():
        path = (ROOT / str(item["path"])).resolve()
        base._require(path.is_relative_to(ROOT), f"v1.1.3 authority escapes repository: {name}")
        base._require(path.is_file(), f"Missing v1.1.3 authority: {name}")
        actual = base.file_sha256(path)
        base._require(actual == str(item["sha256"]), f"v1.1.3 authority mismatch: {name}")
        verified[name] = actual
    return verified


def _load_project_sample_and_robustness(
    runner: base.ProductionExperimentRunner, config: Mapping[str, Any]
) -> tuple[pd.DataFrame, Any, dict[str, Any]]:
    sample, expectations = runner.load_frozen_project_sample()
    section = config["secondary_development_execution"]
    source = section["authority"]["robustness_signal_source"]
    source_path = base._resolve(source["path"])
    base._require(source_path.is_file(), "REQUIRED_DEVELOPMENT_INPUT_MISSING")
    base._require(base.file_sha256(source_path) == str(source["sha256"]), "Robustness signal-source hash mismatch.")
    columns = list(section["data_boundary"]["robustness_target_columns"])
    try:
        signals = pd.read_csv(source_path, usecols=columns, low_memory=False)
    except ValueError as error:
        raise base.SecondaryExecutionIntegrityError(
            "REQUIRED_DEVELOPMENT_COLUMN_MISSING"
        ) from error
    key = "research_universe_company_year_id"
    signals[key] = signals[key].astype(str)
    years = pd.to_numeric(signals["feature_year"], errors="raise").astype(int)
    found = set(years)
    permitted = set(range(2011, 2021))
    if not found <= permitted:
        raise base.ProtectedDataAccessError(
            f"Forbidden years in robustness signal source: {sorted(found - permitted)}"
        )
    signals["feature_year"] = years
    base._require(not signals[key].duplicated().any(), "Duplicate robustness signal identity.")
    merged = sample.merge(
        signals, on=key, how="left", validate="one_to_one",
        suffixes=("", "_robustness"),
    )
    base._require(
        merged["feature_year"].eq(merged["feature_year_robustness"]).all(),
        "Robustness signal year alignment mismatch.",
    )
    base._require(
        merged["target_status_robustness"].eq("available").all(),
        "Robustness signal status differs from supervised sample.",
    )
    numeric = [
        "deterioration_score_1y", "D1_roa", "D2_ocf_assets",
        "D3_current_ratio", "D4_liabilities_assets", "D5_revenues",
    ]
    for column in numeric:
        merged[column] = pd.to_numeric(merged[column], errors="raise")
        base._require(merged[column].notna().all(), f"Missing robustness signal: {column}")
    for column in numeric[1:]:
        base._require(merged[column].isin([0, 1]).all(), f"Nonbinary robustness signal: {column}")
    merged["target__deterioration_score_at_least_2"] = (
        merged["deterioration_score_1y"] >= 2
    ).astype(int)
    merged["target__deterioration_score_at_least_4"] = (
        merged["deterioration_score_1y"] >= 4
    ).astype(int)
    alternative = (
        merged[["D1_roa", "D2_ocf_assets"]].max(axis=1)
        + merged["D3_current_ratio"]
        + merged["D4_liabilities_assets"]
        + merged["D5_revenues"]
    )
    merged[
        "target__operating_performance_max_D1_D2_alternative_score_at_least_3"
    ] = (alternative >= 3).astype(int)
    merged = runner._canonicalize_sample(merged)
    folds = runner.verify_sample_and_folds(merged, expectations)
    audit = {
        "signal_source_amendment_version": "1.1.3",
        "signal_source_role": "frozen_production_target_application_train",
        "additional_interim_target_deserialized": False,
        "sample_membership_n": len(merged),
        "sample_membership_sha256": base.membership_sha256(merged[key].tolist()),
        "robustness_signal_source_sha256": base.file_sha256(source_path),
        "feature_year_min": int(merged["feature_year"].min()),
        "feature_year_max": int(merged["feature_year"].max()),
        "fold_ids": list(folds),
        "project_data_read": True,
        "protected_feature_years_opened": False,
    }
    return merged, expectations, audit


def _output_identity(config_path: Path, git_index_sha256: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": "secondary_development_execution_v1_1_3",
        "execution_config_sha256": base.file_sha256(config_path),
        "base_execution_config_sha256": base.file_sha256(
            ROOT / "configs/secondary_development_execution_v1_1_0.yaml"
        ),
        "frozen_schedule_sha256": base.file_sha256(
            ROOT / "configs/secondary_development_analyses_v1_0_0.yaml"
        ),
        "package_git_index_sha256": git_index_sha256,
        "protected_feature_years_opened": False,
    }


def _patched_preflight_context(
    config_path: Path, output_dir: Path, *, synthetic: bool = False
) -> Any:
    config = load_execution_config(config_path)
    verify_amendment_authority(config)
    if not synthetic:
        from src.modeling.verify_secondary_analysis_execution_v1_1_3 import (
            verify_secondary_analysis_execution_v1_1_3,
        )

        report = verify_secondary_analysis_execution_v1_1_3()
        base._require(report["status"] == "PASS", "v1.1.3 package verification failed.")
    return _BASE_PREFLIGHT_CONTEXT(config_path, output_dir, synthetic=synthetic)


def activate_amendment() -> None:
    base.DEFAULT_CONFIG = DEFAULT_CONFIG
    base.load_execution_config = load_execution_config
    base._load_project_sample_and_robustness = _load_project_sample_and_robustness
    base._output_identity = _output_identity
    base._preflight_context = _patched_preflight_context


def synthetic_smoke_isolated(
    config_path: Path = DEFAULT_CONFIG, output_dir: Path = DEFAULT_OUTPUT
) -> dict[str, Any]:
    """Run the data-free smoke without leaking v1.1.3 globals to importers."""
    names = (
        "DEFAULT_CONFIG",
        "load_execution_config",
        "_load_project_sample_and_robustness",
        "_output_identity",
        "_preflight_context",
    )
    previous = {name: getattr(base, name) for name in names}
    try:
        activate_amendment()
        return base.synthetic_smoke(config_path, output_dir)
    finally:
        for name, value in previous.items():
            setattr(base, name, value)


def create_report(config_path: Path, output_dir: Path) -> dict[str, Any]:
    report = base.create_report(config_path, output_dir)
    report["id"] = "secondary_development_execution_v1_1_3"
    report["signal_source_amendment"] = "1.1.3"
    base.atomic_write_json(output_dir / "run_manifest.json", report)
    result_path = output_dir / "secondary_development_report.json"
    if result_path.is_file():
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result["id"] = "secondary_development_results_v1_1_3"
        result["signal_source_amendment"] = "1.1.3"
        base.atomic_write_json(result_path, result)
    return report


def main() -> None:
    activate_amendment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=(
            "status", "plan", "smoke", "preflight", "pca-controls",
            "interpretability", "robustness-classical", "robustness-qnn",
            "report", "all",
        ),
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    config_path = args.config.resolve()
    if args.output_dir is not None:
        output_dir = args.output_dir.resolve()
    elif args.mode in {"plan", "smoke"}:
        output_dir = (
            ROOT / f"data/model_runs/secondary_development_v1_1_3_{args.mode}"
        ).resolve()
    else:
        output_dir = DEFAULT_OUTPUT.resolve()
    base._require(config_path == DEFAULT_CONFIG.resolve(), "Only canonical v1.1.3 config may execute.")
    if args.mode == "status":
        result = base.package_status(config_path)
        result["amendment_authority_v1_1_3"] = verify_amendment_authority(
            load_execution_config(config_path)
        )
    elif args.mode == "plan":
        result = base.write_plan(config_path, output_dir)
        result["id"] = "secondary_development_execution_plan_v1_1_3"
        result["signal_source_amendment"] = "1.1.3"
        base.atomic_write_json(output_dir / "secondary_analysis_execution_plan.json", result)
    elif args.mode == "smoke":
        result = base.synthetic_smoke(config_path, output_dir)
        result["signal_source_amendment"] = "1.1.3"
    elif args.mode == "preflight":
        _config, _schedule, tasks, _runner, _sample, folds = base._preflight_context(
            config_path, output_dir
        )
        result = {
            "status": "PASS", "planned_tasks": len(tasks), "fold_ids": list(folds),
            "signal_source_amendment": "1.1.3", "project_data_read": True,
            "project_model_fit_performed": False,
            "protected_feature_years_opened": False,
        }
    elif args.mode == "pca-controls":
        result = base.execute_pca_controls(config_path, output_dir)
    elif args.mode == "interpretability":
        result = base.execute_interpretability(config_path, output_dir)
    elif args.mode == "robustness-classical":
        result = base.execute_classical_robustness(config_path, output_dir)
    elif args.mode == "robustness-qnn":
        result = base.execute_qnn_robustness(config_path, output_dir)
    elif args.mode == "report":
        result = create_report(config_path, output_dir)
    else:
        base.execute_pca_controls(config_path, output_dir)
        base.execute_interpretability(config_path, output_dir)
        base.execute_classical_robustness(config_path, output_dir)
        base.execute_qnn_robustness(config_path, output_dir)
        result = create_report(config_path, output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
