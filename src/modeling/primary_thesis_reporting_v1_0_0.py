"""Deterministic reporting-only package for frozen development and gated periods."""

from __future__ import annotations

from collections import Counter
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping

import yaml


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "configs/primary_thesis_reporting_contract_v1_0_0.yaml"
ACCESS_MANIFEST_PATH = ROOT / "configs/primary_thesis_reporting_access_manifest_v1_0_0.yaml"
FREEZE_MANIFEST_PATH = ROOT / "configs/primary_thesis_reporting_package_freeze_v1_0_0.yaml"
REVIEW_PATH = ROOT / "configs/primary_thesis_reporting_access_review_v1_0_0_result.json"
SCHEMA_PATH = ROOT / "configs/primary_thesis_reporting_output_schema_v1_0_0.json"
EXECUTION_RESULT_PATH = ROOT / "configs/primary_thesis_reporting_execution_v1_0_0_result.json"
FREEZE_RESULT_PATH = ROOT / "configs/primary_thesis_reporting_freeze_v1_0_0_result.json"
OUTPUT_ROOT = ROOT / "reports/primary_thesis_reporting_v1_0_0"

DEVELOPMENT_FIELDS = (
    "rank",
    "family",
    "stage",
    "feature_block",
    "configuration_id",
    "training_seed",
    "status",
    "pooled_oof_pr_auc",
    "pooled_oof_roc_auc",
    "parameters",
    "period_role",
    "population_boundary",
    "claim_class",
    "required_labels",
    "source_path",
    "source_sha256",
)

PROTECTED_FIELDS = (
    "period_role",
    "period_label",
    "year",
    "family",
    "feature_block",
    "configuration_id",
    "n",
    "positive_n",
    "average_precision",
    "roc_auc",
    "brier_score",
    "f1_frozen_threshold",
    "precision_frozen_threshold",
    "recall_frozen_threshold",
    "average_precision_ci_lower",
    "average_precision_ci_upper",
    "roc_auc_ci_lower",
    "roc_auc_ci_upper",
    "f1_ci_lower",
    "f1_ci_upper",
    "bootstrap_replicates",
    "bootstrap_valid_replicates",
    "fully_unseen_claimed",
    "selection_or_tuning_performed",
    "claim_class",
    "required_labels",
    "mandatory_disclosure",
    "source_path",
    "source_sha256",
    "source_record",
)

BOUNDARY_FIELDS = (
    "period_role",
    "years",
    "estimand_boundary",
    "allowed_use",
    "fully_unseen_claim_allowed",
    "selection_or_tuning_performed",
    "required_labels",
    "mandatory_disclosure",
    "source_path",
    "source_sha256",
)

LEDGER_FIELDS = (
    "ledger_id",
    "output_table",
    "row_key",
    "field",
    "value",
    "definition",
    "denominator",
    "rounding",
    "source_path",
    "source_sha256",
    "source_record",
    "period_role",
    "population_boundary",
    "claim_class",
    "required_labels",
)


class ReportingError(RuntimeError):
    """Fail-closed reporting package error."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReportingError(message)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"Expected YAML mapping: {path}")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"Expected JSON object: {path}")
    return value


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _csv_bytes(fields: Iterable[str], rows: Iterable[Mapping[str, Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    field_list = list(fields)
    writer = csv.DictWriter(buffer, fieldnames=field_list, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in field_list})
    return buffer.getvalue().encode("utf-8")


def _canonical_sha(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _verified_file(item: Mapping[str, Any]) -> Path:
    path = ROOT / str(item["path"])
    _require(path.is_file(), f"Missing exact source: {path}")
    _require(_sha(path) == str(item["sha256"]), f"Source hash mismatch: {path}")
    return path


def _verify_package_files() -> dict[str, Any]:
    freeze = _load_yaml(FREEZE_MANIFEST_PATH)
    artifacts = freeze.get("artifacts")
    _require(isinstance(artifacts, list) and artifacts, "Package freeze artifacts are absent.")
    for item in artifacts:
        _verified_file(item)
    contract = _load_yaml(CONTRACT_PATH)
    _require(contract["primary_thesis_reporting"]["mode"] == "GATED_SUCCESSOR_MODE", "Wrong mode.")
    decisions = contract["reporting_decisions"]
    _require(
        decisions["new_post_result_statistics"] == "OMIT"
        and decisions["new_paired_comparisons"] == "OMIT"
        and decisions["fp_fn_case_studies_and_runtime_cost"] == "OMIT",
        "Post-result reporting decisions are not conservative.",
    )
    allowlist = _load_yaml(ACCESS_MANIFEST_PATH)
    _require(
        allowlist["authority"]["contract_sha256"] == _sha(CONTRACT_PATH),
        "Access manifest contract authority mismatch.",
    )
    return {"verdict": "PRIMARY_REPORTING_PACKAGE_PREFLIGHT_PASS"}


def _scope_sha(scope: Mapping[str, Any]) -> str:
    definition = scope.get("definition")
    _require(isinstance(definition, Mapping), "Scope definition is absent.")
    return _canonical_sha(definition)


def _reviewed_scope(name: str) -> tuple[str, str]:
    manifest = _load_yaml(ACCESS_MANIFEST_PATH)
    review = _load_json(REVIEW_PATH)
    scopes = manifest.get("scopes")
    _require(isinstance(scopes, Mapping) and name in scopes, "Unknown reporting scope.")
    scope = scopes[name]
    actual = _scope_sha(scope)
    _require(actual == scope.get("definition_sha256"), "Reporting scope hash mismatch.")
    _require(review.get("verdict") == "REPORTING_ALLOWLIST_REVIEW_PASS", "Reporting review did not pass.")
    _require(review.get("subject_manifest_sha256") == _sha(ACCESS_MANIFEST_PATH), "Review subject changed.")
    reviewed = review.get("scopes", {}).get(name, {})
    _require(reviewed.get("verdict") == "PASS", "Reporting scope review did not pass.")
    _require(reviewed.get("definition_sha256") == actual, "Reviewed reporting scope changed.")
    return str(scope["id"]), actual


def _load_real_sources() -> dict[str, Any]:
    contract = _load_yaml(CONTRACT_PATH)
    sources = contract["exact_value_sources"]
    verified = {name: _verified_file(item) for name, item in sources.items()}
    for item in contract["opaque_provenance_sources"]:
        _verified_file(item)
    spent_freeze = _load_json(verified["spent_freeze"])
    holdout_freeze = _load_json(verified["holdout_freeze"])
    _require(spent_freeze.get("verdict") == "SPENT_REPORT_FREEZE_PASS", "Spent report is not frozen.")
    _require(holdout_freeze.get("verdict") == "HOLDOUT_REPORT_FREEZE_PASS", "Holdout report is not frozen.")
    _require(
        spent_freeze.get("report_sha256") == _sha(verified["spent_report"]),
        "Spent freeze/report mismatch.",
    )
    _require(
        holdout_freeze.get("report_sha256") == _sha(verified["holdout_report"]),
        "Holdout freeze/report mismatch.",
    )
    with verified["development_ranking"].open(encoding="utf-8", newline="") as stream:
        development = list(csv.DictReader(stream))
    _require(len(development) == 9, "Development family roster is incomplete.")
    return {
        "development": development,
        "spent": _load_json(verified["spent_report"]),
        "holdout": _load_json(verified["holdout_report"]),
        "source_items": sources,
        "provenance_items": contract["opaque_provenance_sources"],
    }


def _development_rows(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    item = source["source_items"]["development_ranking"]
    rows: list[dict[str, Any]] = []
    for original in source["development"]:
        row = {field: original.get(field, "") for field in DEVELOPMENT_FIELDS}
        row.update(
            {
                "period_role": "development",
                "population_boundary": "pooled_oof_2015_2020",
                "claim_class": "development_only_conditional_on_selection",
                "required_labels": "development-only; conditional-on-selection; selection-unadjusted",
                "source_path": item["path"],
                "source_sha256": item["sha256"],
            }
        )
        rows.append(row)
    return rows


def _protected_rows(
    report: Mapping[str, Any],
    *,
    role: str,
    source_item: Mapping[str, Any],
) -> list[dict[str, Any]]:
    _require(report.get("fully_unseen_claimed") is False, f"{role} fully-unseen claim is forbidden.")
    _require(report.get("selection_or_tuning_performed") is False, f"{role} tuning flag changed.")
    source_rows = report.get("metric_rows")
    _require(isinstance(source_rows, list) and len(source_rows) == 18, f"{role} roster is incomplete.")
    expected_years = {"spent_development": {2021: 9, 2022: 9}, "holdout": {2023: 9, 2024: 9}}
    counts = Counter(int(row["year"]) for row in source_rows)
    _require(counts == expected_years[role], f"{role} year roster is incomplete.")
    required_labels = (
        "secondary spent-development; design-exposed; not independent validation"
        if role == "spent_development"
        else "temporal holdout; prior aggregate and label exposure disclosed; not fully unseen"
    )
    claim_class = (
        "secondary_design_exposed_spent_development"
        if role == "spent_development"
        else "temporal_holdout_with_mandatory_prior_exposure_disclosure"
    )
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(source_rows):
        metrics = item["metrics"]
        intervals = item["cluster_bootstrap"]["intervals"]
        identity = item["identity"]
        rows.append(
            {
                "period_role": role,
                "period_label": report["period_label"],
                "year": int(item["year"]),
                "family": identity["family"],
                "feature_block": identity["feature_block"],
                "configuration_id": identity["configuration_id"],
                "n": int(item["n"]),
                "positive_n": int(item["positive_n"]),
                "average_precision": metrics["pr_auc"],
                "roc_auc": metrics["roc_auc"],
                "brier_score": metrics["brier_score"],
                "f1_frozen_threshold": metrics["f1_frozen_threshold"],
                "precision_frozen_threshold": metrics["precision_frozen_threshold"],
                "recall_frozen_threshold": metrics["recall_frozen_threshold"],
                "average_precision_ci_lower": intervals["pr_auc"]["lower"],
                "average_precision_ci_upper": intervals["pr_auc"]["upper"],
                "roc_auc_ci_lower": intervals["roc_auc"]["lower"],
                "roc_auc_ci_upper": intervals["roc_auc"]["upper"],
                "f1_ci_lower": intervals["f1_frozen_threshold"]["lower"],
                "f1_ci_upper": intervals["f1_frozen_threshold"]["upper"],
                "bootstrap_replicates": int(item["cluster_bootstrap"]["replicates"]),
                "bootstrap_valid_replicates": int(item["cluster_bootstrap"]["valid_replicates"]),
                "fully_unseen_claimed": False,
                "selection_or_tuning_performed": False,
                "claim_class": claim_class,
                "required_labels": required_labels,
                "mandatory_disclosure": report["prior_exposure_disclosure"],
                "source_path": source_item["path"],
                "source_sha256": source_item["sha256"],
                "source_record": f"metric_rows[{index}]",
            }
        )
    return sorted(rows, key=lambda row: (row["year"], row["configuration_id"]))


def _boundary_rows(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    development_item = source["source_items"]["development_ranking"]
    spent_item = source["source_items"]["spent_report"]
    holdout_item = source["source_items"]["holdout_report"]
    return [
        {
            "period_role": "development",
            "years": "2015-2020 OOF",
            "estimand_boundary": "development-only pooled out-of-fold performance",
            "allowed_use": "frozen primary development ranking; no independent-test claim",
            "fully_unseen_claim_allowed": False,
            "selection_or_tuning_performed": "completed before protected-period extension",
            "required_labels": "development-only; conditional-on-selection; selection-unadjusted",
            "mandatory_disclosure": "No independent post-selection test is claimed.",
            "source_path": development_item["path"],
            "source_sha256": development_item["sha256"],
        },
        {
            "period_role": "spent_development",
            "years": "2021-2022",
            "estimand_boundary": "secondary design-exposed spent-development evidence",
            "allowed_use": "secondary evidence only; cannot activate tuning or reselection",
            "fully_unseen_claim_allowed": False,
            "selection_or_tuning_performed": False,
            "required_labels": "design-exposed; spent development; not independent validation",
            "mandatory_disclosure": source["spent"]["prior_exposure_disclosure"],
            "source_path": spent_item["path"],
            "source_sha256": spent_item["sha256"],
        },
        {
            "period_role": "holdout",
            "years": "2023-2024",
            "estimand_boundary": "temporal model-performance holdout with prior exposure disclosure",
            "allowed_use": "frozen temporal evidence; no post-result methodology change",
            "fully_unseen_claim_allowed": False,
            "selection_or_tuning_performed": False,
            "required_labels": "holdout; prior aggregate and label exposure disclosed; not fully unseen",
            "mandatory_disclosure": source["holdout"]["prior_exposure_disclosure"],
            "source_path": holdout_item["path"],
            "source_sha256": holdout_item["sha256"],
        },
    ]


def _availability_rows() -> list[dict[str, Any]]:
    return [
        {"requested_output": "frozen aggregate AP ROC-AUC Brier F1 precision recall", "status": "AVAILABLE", "reason": "Present in exact frozen aggregate reports."},
        {"requested_output": "clustered bootstrap intervals for AP ROC-AUC F1", "status": "AVAILABLE", "reason": "Present in exact frozen aggregate reports; copied without recomputation."},
        {"requested_output": "log loss", "status": "OMIT_NOT_IN_FROZEN_AGGREGATE", "reason": "No row-level computation is authorized for this package."},
        {"requested_output": "calibration intercept slope and calibration curve", "status": "OMIT_NOT_IN_FROZEN_AGGREGATE", "reason": "No row-level computation is authorized for this package."},
        {"requested_output": "sector size XBRL retention and composition", "status": "OMIT_NOT_IN_FROZEN_AGGREGATE", "reason": "No protected row-level composition read is authorized."},
        {"requested_output": "new paired comparisons FP FN cases and runtime costs", "status": "OMIT_BY_PRECOMMITTED_DECISION", "reason": "Avoid post-result exploratory expansion."},
    ]


def _ledger(
    development: list[dict[str, Any]],
    protected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    definitions = {
        "rank": ("Frozen family rank by pooled development average precision.", "nine frozen family representatives"),
        "pooled_oof_pr_auc": ("Pooled OOF average precision, historically labelled PR-AUC.", "OOF company-year observations 2015-2020"),
        "pooled_oof_roc_auc": ("Pooled OOF ROC-AUC.", "OOF company-year observations 2015-2020"),
    }
    for row in development:
        key = f"development|{row['configuration_id']}"
        for field, (definition, denominator) in definitions.items():
            rows.append(
                {
                    "ledger_id": f"DEV-{len(rows) + 1:04d}",
                    "output_table": "tables/01_development_family_ranking.csv",
                    "row_key": key,
                    "field": field,
                    "value": row[field],
                    "definition": definition,
                    "denominator": denominator,
                    "rounding": "source precision; recommended display 4 decimals for metrics",
                    "source_path": row["source_path"],
                    "source_sha256": row["source_sha256"],
                    "source_record": f"configuration_id={row['configuration_id']}",
                    "period_role": "development",
                    "population_boundary": "pooled_oof_2015_2020",
                    "claim_class": row["claim_class"],
                    "required_labels": row["required_labels"],
                }
            )
    protected_fields = {
        "year": ("Feature/prediction year.", "not applicable"),
        "n": ("Number of evaluable company-year observations.", "aligned available-label observations"),
        "positive_n": ("Number of positive target labels.", "aligned available-label observations"),
        "average_precision": ("Average precision, historically labelled PR-AUC.", "aligned available-label observations"),
        "roc_auc": ("ROC-AUC.", "aligned available-label observations"),
        "brier_score": ("Mean squared probabilistic forecast error.", "aligned available-label observations"),
        "f1_frozen_threshold": ("F1 at the frozen development threshold.", "aligned available-label observations"),
        "precision_frozen_threshold": ("Precision at the frozen development threshold.", "predicted positives"),
        "recall_frozen_threshold": ("Recall at the frozen development threshold.", "positive labels"),
        "average_precision_ci_lower": ("Lower 2.5th percentile clustered-bootstrap AP bound.", "economic_group_id clustered bootstrap"),
        "average_precision_ci_upper": ("Upper 97.5th percentile clustered-bootstrap AP bound.", "economic_group_id clustered bootstrap"),
        "roc_auc_ci_lower": ("Lower 2.5th percentile clustered-bootstrap ROC-AUC bound.", "economic_group_id clustered bootstrap"),
        "roc_auc_ci_upper": ("Upper 97.5th percentile clustered-bootstrap ROC-AUC bound.", "economic_group_id clustered bootstrap"),
        "f1_ci_lower": ("Lower 2.5th percentile clustered-bootstrap F1 bound.", "economic_group_id clustered bootstrap"),
        "f1_ci_upper": ("Upper 97.5th percentile clustered-bootstrap F1 bound.", "economic_group_id clustered bootstrap"),
        "bootstrap_replicates": ("Requested clustered-bootstrap replicates.", "economic_group_id clusters"),
        "bootstrap_valid_replicates": ("Valid non-degenerate clustered-bootstrap replicates.", "requested bootstrap replicates"),
    }
    for row in protected:
        key = f"{row['period_role']}|{row['year']}|{row['configuration_id']}"
        for field, (definition, denominator) in protected_fields.items():
            rows.append(
                {
                    "ledger_id": f"PROT-{len(rows) + 1:04d}",
                    "output_table": "tables/02_protected_period_metrics.csv",
                    "row_key": key,
                    "field": field,
                    "value": row[field],
                    "definition": definition,
                    "denominator": denominator,
                    "rounding": "source precision; recommended display 4 decimals for metrics",
                    "source_path": row["source_path"],
                    "source_sha256": row["source_sha256"],
                    "source_record": row["source_record"],
                    "period_role": row["period_role"],
                    "population_boundary": row["period_label"],
                    "claim_class": row["claim_class"],
                    "required_labels": row["required_labels"],
                }
            )
    return rows


def build_artifacts(source: Mapping[str, Any]) -> dict[str, bytes]:
    development = _development_rows(source)
    spent = _protected_rows(
        source["spent"],
        role="spent_development",
        source_item=source["source_items"]["spent_report"],
    )
    holdout = _protected_rows(
        source["holdout"],
        role="holdout",
        source_item=source["source_items"]["holdout_report"],
    )
    protected = spent + holdout
    boundaries = _boundary_rows(source)
    provenance = [
        {
            "package": item["package"],
            "path": item["path"],
            "sha256": item["sha256"],
            "access_mode": "opaque_hash_provenance_only",
            "values_included": False,
        }
        for item in source["provenance_items"]
    ]
    ledger = _ledger(development, protected)
    readme = """# Primary thesis reporting v1.0.0 — GATED_SUCCESSOR_MODE

This package is a deterministic navigation and evidence bundle, not thesis prose.

- `tables/01_development_family_ranking.csv`: frozen development-only family ranking.
- `tables/02_protected_period_metrics.csv`: separate spent-development and holdout rows.
- `tables/03_period_boundaries.csv`: claim boundaries and mandatory labels.
- `tables/04_reporting_availability.csv`: available and deliberately omitted outputs.
- `tables/05_package_provenance.csv`: opaque provenance for upstream packages.
- `evidence_ledger.csv` / `evidence_ledger.json`: number-level source mapping.

Never pool development, spent-development and holdout into one estimand. The bundle
does not support an independent-test, fully-unseen-holdout or quantum-advantage claim.
"""
    artifacts = {
        "README.md": readme.encode("utf-8"),
        "tables/01_development_family_ranking.csv": _csv_bytes(DEVELOPMENT_FIELDS, development),
        "tables/02_protected_period_metrics.csv": _csv_bytes(PROTECTED_FIELDS, protected),
        "tables/03_period_boundaries.csv": _csv_bytes(BOUNDARY_FIELDS, boundaries),
        "tables/04_reporting_availability.csv": _csv_bytes(
            ("requested_output", "status", "reason"), _availability_rows()
        ),
        "tables/05_package_provenance.csv": _csv_bytes(
            ("package", "path", "sha256", "access_mode", "values_included"), provenance
        ),
        "evidence_ledger.csv": _csv_bytes(LEDGER_FIELDS, ledger),
        "evidence_ledger.json": _json_bytes(
            {
                "schema_version": 1,
                "status": "COMPLETE",
                "mode": "GATED_SUCCESSOR_MODE",
                "narrative_or_interpretation_included": False,
                "records": ledger,
            }
        ),
    }
    manifest_files = [
        {
            "path": name,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        for name, payload in sorted(artifacts.items())
    ]
    artifacts["manifest.json"] = _json_bytes(
        {
            "schema_version": 1,
            "status": "COMPLETE",
            "mode": "GATED_SUCCESSOR_MODE",
            "development_rows": len(development),
            "protected_metric_rows": len(protected),
            "evidence_ledger_records": len(ledger),
            "figures": 0,
            "files": manifest_files,
        }
    )
    return artifacts


def _write_artifacts(output_root: Path, artifacts: Mapping[str, bytes]) -> None:
    _require(not output_root.exists(), f"Output root already exists: {output_root}")
    for relative, payload in artifacts.items():
        path = output_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def _verify_output(output_root: Path, expected: Mapping[str, bytes]) -> dict[str, Any]:
    expected_names = set(expected)
    actual_names = {
        str(path.relative_to(output_root)) for path in output_root.rglob("*") if path.is_file()
    }
    _require(actual_names == expected_names, "Reporting output file set mismatch.")
    for name, payload in expected.items():
        _require((output_root / name).read_bytes() == payload, f"Reporting output mismatch: {name}")
    manifest = _load_json(output_root / "manifest.json")
    schema = _load_json(SCHEMA_PATH)
    required = set(schema["required"])
    _require(
        required <= set(manifest)
        and manifest.get("schema_version") == schema["properties"]["schema_version"]["const"]
        and manifest.get("status") == schema["properties"]["status"]["const"]
        and manifest.get("mode") == schema["properties"]["mode"]["const"]
        and manifest.get("development_rows") == 9
        and manifest.get("protected_metric_rows") == 36
        and manifest.get("figures") == 0,
        "Reporting output cardinality mismatch.",
    )
    forbidden = b"protected_period_holdout_evaluation_v1_0_0_result.json"
    _require(
        all(forbidden not in payload for payload in expected.values()),
        "Failed holdout v1.0.0 entered the reporting package.",
    )
    return {
        "verdict": "PRIMARY_REPORTING_OUTPUT_PASS",
        "output_manifest_sha256": _sha(output_root / "manifest.json"),
        "output_files": len(expected),
        "development_rows": 9,
        "protected_metric_rows": 36,
        "figures": 0,
    }


def verify_package_action() -> dict[str, Any]:
    return _verify_package_files()


def generate_action() -> dict[str, Any]:
    _verify_package_files()
    scope_id, scope_hash = _reviewed_scope("reporting_generation_scope")
    source = _load_real_sources()
    artifacts = build_artifacts(source)
    _write_artifacts(OUTPUT_ROOT, artifacts)
    verified = _verify_output(OUTPUT_ROOT, artifacts)
    execution = {
        "schema_version": 1,
        "verdict": "PRIMARY_REPORTING_EXECUTION_PASS",
        "mode": "GATED_SUCCESSOR_MODE",
        "scope_id": scope_id,
        "scope_sha256": scope_hash,
        "access_manifest_sha256": _sha(ACCESS_MANIFEST_PATH),
        "package_freeze_manifest_sha256": _sha(FREEZE_MANIFEST_PATH),
        "output_manifest_sha256": verified["output_manifest_sha256"],
        "output_files": verified["output_files"],
        "development_rows": verified["development_rows"],
        "protected_metric_rows": verified["protected_metric_rows"],
        "new_statistics_computed": False,
        "row_level_protected_content_read": False,
        "model_fit_refit_or_prediction_performed": False,
    }
    EXECUTION_RESULT_PATH.write_bytes(_json_bytes(execution))
    return execution


def verify_output_action() -> dict[str, Any]:
    _verify_package_files()
    _reviewed_scope("reporting_generation_scope")
    source = _load_real_sources()
    return _verify_output(OUTPUT_ROOT, build_artifacts(source))


def freeze_action() -> dict[str, Any]:
    _verify_package_files()
    scope_id, scope_hash = _reviewed_scope("reporting_freeze_scope")
    execution = _load_json(EXECUTION_RESULT_PATH)
    _require(execution.get("verdict") == "PRIMARY_REPORTING_EXECUTION_PASS", "Execution did not pass.")
    source = _load_real_sources()
    expected = build_artifacts(source)
    verified = _verify_output(OUTPUT_ROOT, expected)
    with tempfile.TemporaryDirectory(prefix="primary_reporting_reproduction_") as directory:
        reproduced_root = Path(directory) / "package"
        _write_artifacts(reproduced_root, expected)
        reproduced = _verify_output(reproduced_root, expected)
    result = {
        "schema_version": 1,
        "verdict": "PRIMARY_REPORTING_FREEZE_PASS",
        "mode": "GATED_SUCCESSOR_MODE",
        "scope_id": scope_id,
        "scope_sha256": scope_hash,
        "execution_result_sha256": _sha(EXECUTION_RESULT_PATH),
        "output_manifest_sha256": verified["output_manifest_sha256"],
        "reproduced_manifest_sha256": reproduced["output_manifest_sha256"],
        "deterministic_reproduction": verified["output_manifest_sha256"]
        == reproduced["output_manifest_sha256"],
        "development_spent_holdout_estimands_separate": True,
        "failed_v1_0_0_output_included": False,
        "row_level_protected_content_read": False,
        "new_statistics_computed": False,
        "model_fit_refit_or_prediction_performed": False,
        "figure_outputs": 0,
        "visual_qa": "NOT_APPLICABLE_NO_CANONICAL_FIGURES",
    }
    _require(result["deterministic_reproduction"], "Reporting reproduction differs.")
    FREEZE_RESULT_PATH.write_bytes(_json_bytes(result))
    return result


ACTIONS = {
    "verify-package": verify_package_action,
    "generate": generate_action,
    "verify-output": verify_output_action,
    "freeze": freeze_action,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=tuple(ACTIONS))
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    result = ACTIONS[arguments.action]()
    print(json.dumps({"action": arguments.action, "verdict": result["verdict"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
