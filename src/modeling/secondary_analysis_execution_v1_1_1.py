"""Input-key amendment for secondary-development execution v1.1.1.

The frozen v1.1.0 controller remains byte-identical.  This thin versioned layer
changes only the join adapter for the additional robustness-target projection:
its source identity is ``(cik10, feature_year)`` and is canonically mapped to the
model sample's ``research_universe_company_year_id`` (``CIK10-YYYY``).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any, Mapping

import pandas as pd
import yaml

from src.modeling import secondary_analysis_execution as base


ROOT = base.ROOT
DEFAULT_CONFIG = (
    ROOT / "configs/secondary_development_execution_v1_1_1_input_key_fix.yaml"
)
DEFAULT_OUTPUT = ROOT / "data/model_runs/secondary_development_v1_1_1"
_BASE_PREFLIGHT_CONTEXT = base._preflight_context
_BASE_LOAD_EXECUTION_CONFIG = base.load_execution_config


def _merge(base_value: Any, overlay_value: Any) -> Any:
    if isinstance(base_value, Mapping) and isinstance(overlay_value, Mapping):
        result = dict(base_value)
        for key, value in overlay_value.items():
            result[key] = _merge(result.get(key), value)
        return result
    return overlay_value


def load_execution_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    resolved = path.resolve()
    payload = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    base._require(isinstance(payload, dict), "Execution amendment must be a mapping.")
    extension = payload.get("extends")
    base._require(isinstance(extension, Mapping), "Execution amendment must extend v1.1.0.")
    base_path = (ROOT / str(extension["path"])).resolve()
    base._require(base_path == ROOT / "configs/secondary_development_execution_v1_1_0.yaml", "Wrong amendment base.")
    base._require(base.file_sha256(base_path) == str(extension["sha256"]), "Base execution hash mismatch.")
    inherited = _BASE_LOAD_EXECUTION_CONFIG(base_path)
    merged = _merge(inherited, {key: value for key, value in payload.items() if key != "extends"})
    section = merged["secondary_development_execution"]
    base._require(section["id"] == "secondary_development_execution_v1_1_1", "Wrong amendment ID.")
    base._require(section["version"] == "1.1.1", "Wrong amendment version.")
    base._require(section["status"] == "executable_input_key_amendment_frozen", "Amendment is not frozen.")
    amendment = section["input_key_amendment"]
    base._require(amendment["scope"] == "robustness_target_join_key_only", "Amendment scope changed.")
    for field in (
        "target_values_changed", "sample_membership_changed", "fold_policy_changed",
        "task_roster_changed", "methodology_changed",
    ):
        base._require(amendment[field] is False, f"Forbidden amendment change: {field}")
    return merged


def verify_amendment_authority(config: Mapping[str, Any]) -> dict[str, str]:
    authority = config["secondary_development_execution"]["amendment_authority"]
    verified: dict[str, str] = {}
    for name, item in authority.items():
        path = (ROOT / str(item["path"])).resolve()
        base._require(path.is_relative_to(ROOT), f"Amendment authority escapes repository: {name}")
        base._require(path.is_file(), f"Missing amendment authority: {name}")
        actual = base.file_sha256(path)
        base._require(actual == str(item["sha256"]), f"Amendment authority mismatch: {name}")
        verified[name] = actual
    return verified


def canonical_company_year_id(cik10: Any, feature_year: Any) -> str:
    cik = str(cik10).strip()
    if cik.endswith(".0") and cik[:-2].isdigit():
        cik = cik[:-2]
    base._require(bool(re.fullmatch(r"[0-9]{1,10}", cik)), "Invalid CIK in robustness target.")
    year = int(feature_year)
    base._require(2011 <= year <= 2020, "PROTECTED_DATA_ACCESS_BLOCKED")
    return f"{cik.zfill(10)}-{year}"


def _load_project_sample_and_robustness(
    runner: base.ProductionExperimentRunner, config: Mapping[str, Any]
) -> tuple[pd.DataFrame, Any, dict[str, Any]]:
    sample, expectations = runner.load_frozen_project_sample()
    section = config["secondary_development_execution"]
    target_item = section["authority"]["robustness_target_train"]
    target_path = base._resolve(target_item["path"])
    base._require(target_path.is_file(), "REQUIRED_DEVELOPMENT_INPUT_MISSING")
    base._require(base.file_sha256(target_path) == target_item["sha256"], "Robustness target hash mismatch.")
    columns = list(section["data_boundary"]["robustness_target_columns"])
    try:
        target = pd.read_csv(
            target_path, usecols=columns, dtype={"cik10": str}, low_memory=False
        )
    except ValueError as error:
        raise base.SecondaryExecutionIntegrityError(
            "REQUIRED_DEVELOPMENT_COLUMN_MISSING"
        ) from error
    years = pd.to_numeric(target["feature_year"], errors="raise").astype(int)
    found = set(years)
    permitted = set(range(2011, 2021))
    if not found <= permitted:
        raise base.ProtectedDataAccessError(
            f"Forbidden years in robustness target: {sorted(found - permitted)}"
        )
    target["feature_year"] = years
    key = "research_universe_company_year_id"
    target[key] = [
        canonical_company_year_id(cik, year)
        for cik, year in zip(target["cik10"], target["feature_year"], strict=True)
    ]
    base._require(not target[key].duplicated().any(), "Duplicate robustness target identity.")
    merged = sample.merge(
        target.drop(columns=["cik10"]),
        on=key,
        how="left",
        validate="one_to_one",
        suffixes=("", "_robustness"),
    )
    base._require(
        merged["feature_year"].eq(merged["feature_year_robustness"]).all(),
        "Robustness target year alignment mismatch.",
    )
    base._require(
        merged["target_status_robustness"].eq("available").all(),
        "Robustness target status differs from supervised sample.",
    )
    numeric = [
        "deterioration_score_1y", "D1_roa", "D2_ocf_assets",
        "D3_current_ratio", "D4_liabilities_assets", "D5_revenues",
    ]
    for column in numeric:
        merged[column] = pd.to_numeric(merged[column], errors="raise")
        base._require(merged[column].notna().all(), f"Missing robustness target component: {column}")
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
        "input_key_amendment_version": "1.1.1",
        "input_key_construction": "CIK10-YYYY",
        "sample_membership_n": len(merged),
        "sample_membership_sha256": base.membership_sha256(merged[key].tolist()),
        "robustness_target_sha256": base.file_sha256(target_path),
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
        "id": "secondary_development_execution_v1_1_1",
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
        from src.modeling.verify_secondary_analysis_execution_v1_1_1 import (
            verify_secondary_analysis_execution_v1_1_1,
        )

        report = verify_secondary_analysis_execution_v1_1_1()
        base._require(report["status"] == "PASS", "v1.1.1 package verification failed.")
    return _BASE_PREFLIGHT_CONTEXT(config_path, output_dir, synthetic=synthetic)


def activate_amendment() -> None:
    base.DEFAULT_CONFIG = DEFAULT_CONFIG
    base.load_execution_config = load_execution_config
    base._load_project_sample_and_robustness = _load_project_sample_and_robustness
    base._output_identity = _output_identity
    base._preflight_context = _patched_preflight_context
    # Keep the historical v1.1.0 verifier bound to its historical loader even
    # though this process activates the v1.1.1 controller globals.
    from src.modeling import verify_secondary_analysis_execution_package as base_verifier

    base_verifier.DEFAULT_CONFIG = (
        ROOT / "configs/secondary_development_execution_v1_1_0.yaml"
    )
    base_verifier.load_execution_config = _BASE_LOAD_EXECUTION_CONFIG


def create_report(config_path: Path, output_dir: Path) -> dict[str, Any]:
    report = base.create_report(config_path, output_dir)
    report["id"] = "secondary_development_execution_v1_1_1"
    report["input_key_amendment"] = "1.1.1"
    base.atomic_write_json(output_dir / "run_manifest.json", report)
    result_path = output_dir / "secondary_development_report.json"
    if result_path.is_file():
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result["id"] = "secondary_development_results_v1_1_1"
        result["input_key_amendment"] = "1.1.1"
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
            ROOT / f"data/model_runs/secondary_development_v1_1_1_{args.mode}"
        ).resolve()
    else:
        output_dir = DEFAULT_OUTPUT.resolve()
    base._require(config_path == DEFAULT_CONFIG.resolve(), "Only canonical v1.1.1 config may execute.")
    if args.mode == "status":
        result = base.package_status(config_path)
        result["amendment_authority"] = verify_amendment_authority(
            load_execution_config(config_path)
        )
    elif args.mode == "plan":
        result = base.write_plan(config_path, output_dir)
        result["id"] = "secondary_development_execution_plan_v1_1_1"
        result["input_key_amendment"] = "1.1.1"
        base.atomic_write_json(output_dir / "secondary_analysis_execution_plan.json", result)
    elif args.mode == "smoke":
        result = base.synthetic_smoke(config_path, output_dir)
        result["input_key_amendment"] = "1.1.1"
    elif args.mode == "preflight":
        _config, _schedule, tasks, _runner, _sample, folds = base._preflight_context(
            config_path, output_dir
        )
        result = {
            "status": "PASS", "planned_tasks": len(tasks), "fold_ids": list(folds),
            "input_key_amendment": "1.1.1", "project_data_read": True,
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


activate_amendment()


if __name__ == "__main__":
    main()
