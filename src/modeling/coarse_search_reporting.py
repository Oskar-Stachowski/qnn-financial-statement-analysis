"""Descriptive reporting for already-completed classical/MLP coarse search.

This module is intentionally read-only with respect to experiment inputs. It never
constructs estimators, never calls ``fit``, never runs cross-validation, and never
opens the protected 2021--2024 holdout. Its only accepted primary source is the
canonical ``classical_mlp_coarse_search_manifest.json`` emitted by the frozen
production runner.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml


MANIFEST_NAME = "classical_mlp_coarse_search_manifest.json"
EXPECTED_MODE = "classical_mlp_coarse_search"
EXPECTED_YEARS: tuple[int, ...] = (2015, 2016, 2017, 2018, 2019, 2020)
BLOCK_ORDER: tuple[str, ...] = ("L", "L+D", "L+D+R")
BLOCK_AGNOSTIC = "BLOCK_AGNOSTIC"
FAMILY_ORDER: tuple[str, ...] = (
    "dummy_prior",
    "fixed_l2_logistic",
    "elastic_net_logistic",
    "rbf_svm",
    "hist_gradient_boosting",
    "xgboost",
    "random_forest",
    "pytorch_mlp",
)
FAMILY_LABELS: dict[str, str] = {
    "dummy_prior": "Dummy (prior)",
    "fixed_l2_logistic": "Regresja logistyczna fixed L2",
    "elastic_net_logistic": "Regresja logistyczna Elastic Net",
    "rbf_svm": "SVM RBF",
    "hist_gradient_boosting": "HistGradientBoosting",
    "xgboost": "XGBoost",
    "random_forest": "Random Forest",
    "pytorch_mlp": "MLP (PyTorch)",
}


class CoarseSearchReportingError(RuntimeError):
    """Base exception for the read-only reporting layer."""


class CoarseSearchArtifactNotFound(CoarseSearchReportingError):
    """No canonical full coarse-search manifest was found."""


class AmbiguousCoarseSearchSource(CoarseSearchReportingError):
    """More than one distinct valid source exists and none is explicitly selected."""


class CoarseSearchIntegrityError(CoarseSearchReportingError):
    """The selected source violates the expected coarse-search contract."""


@dataclass(frozen=True)
class ManifestSource:
    project_root: Path
    manifest_path: Path
    output_root: Path
    payload: Mapping[str, Any]
    sha256: str
    run_manifest_path: Path | None
    run_manifest_verified: bool

    @property
    def relative_manifest_path(self) -> str:
        return self.manifest_path.relative_to(self.project_root).as_posix()


@dataclass
class CoarseSearchReport:
    source: ManifestSource
    source_summary: pd.DataFrame
    integrity_summary: pd.DataFrame
    integrity_issues: pd.DataFrame
    inventory: pd.DataFrame
    candidates: pd.DataFrame
    tables: dict[str, pd.DataFrame]
    figures: dict[str, Path]
    output_dir: Path
    summary_markdown: str
    ranking_method: str
    analysis_manifest_path: Path


def find_project_root(start: Path | None = None) -> Path:
    """Locate the repository root without relying on an absolute local path."""

    current = (start or Path.cwd()).resolve()
    markers = (
        Path("configs/production_experiment_runner_v1_0_0.yaml"),
        Path("src/modeling/production_runner.py"),
    )
    for candidate in (current, *current.parents):
        if all((candidate / marker).is_file() for marker in markers):
            return candidate
    raise FileNotFoundError(
        "Nie znaleziono katalogu głównego repozytorium. Oczekiwano plików "
        "configs/production_experiment_runner_v1_0_0.yaml oraz "
        "src/modeling/production_runner.py."
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CoarseSearchIntegrityError(f"Nie można odczytać JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CoarseSearchIntegrityError(f"Oczekiwano obiektu JSON w pliku: {path}")
    return value


def _safe_path(root: Path, raw_path: str | Path) -> Path:
    path = Path(raw_path)
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise CoarseSearchIntegrityError(
            f"Ścieżka artefaktu wychodzi poza repozytorium: {raw_path}"
        ) from exc
    return resolved


def _candidate_identity(report: Mapping[str, Any]) -> tuple[str, str, str, int]:
    return (
        str(report.get("family")),
        str(report.get("feature_block")),
        str(report.get("configuration_id")),
        int(report.get("training_seed", -1)),
    )


def _identity_text(report: Mapping[str, Any]) -> str:
    family, block, configuration_id, seed = _candidate_identity(report)
    return f"{family}|{block}|{configuration_id}|seed={seed}"


def _verify_run_manifest(manifest_path: Path, manifest_sha256: str) -> tuple[Path | None, bool]:
    run_manifest_path = manifest_path.parent / "run_manifest.json"
    if not run_manifest_path.is_file():
        return None, False
    try:
        run_manifest = _read_json(run_manifest_path)
    except CoarseSearchIntegrityError:
        return run_manifest_path, False
    expected = run_manifest.get("classical_mlp_coarse_search_manifest_sha256")
    return run_manifest_path, bool(expected and str(expected) == manifest_sha256)


def discover_coarse_search_manifests(project_root: Path) -> list[Path]:
    """Find exact canonical manifest names while ignoring virtual environments."""

    root = project_root.resolve()
    ignored_parts = {".git", ".venv", "venv", "site-packages", "node_modules", "__pycache__"}
    discovered: list[Path] = []
    for path in root.rglob(MANIFEST_NAME):
        try:
            relative = path.resolve().relative_to(root)
        except ValueError:
            continue
        if ignored_parts.intersection(relative.parts):
            continue
        if path.is_file():
            discovered.append(path.resolve())
    return sorted(set(discovered), key=lambda item: item.as_posix())


def _load_source(project_root: Path, manifest_path: Path) -> ManifestSource:
    payload = _read_json(manifest_path)
    digest = file_sha256(manifest_path)
    run_manifest_path, run_manifest_verified = _verify_run_manifest(manifest_path, digest)
    return ManifestSource(
        project_root=project_root.resolve(),
        manifest_path=manifest_path.resolve(),
        output_root=manifest_path.resolve().parent,
        payload=payload,
        sha256=digest,
        run_manifest_path=run_manifest_path,
        run_manifest_verified=run_manifest_verified,
    )


def select_canonical_manifest(
    project_root: Path,
    manifest_override: str | Path | None = None,
) -> ManifestSource:
    """Select one canonical full coarse-search source without arbitrary guessing."""

    root = project_root.resolve()
    explicit = manifest_override or os.environ.get("COARSE_SEARCH_MANIFEST")
    if explicit:
        path = _safe_path(root, explicit)
        if not path.is_file():
            raise CoarseSearchArtifactNotFound(
                f"Wskazany manifest coarse searchu nie istnieje: {path}"
            )
        source = _load_source(root, path)
        if source.payload.get("mode") != EXPECTED_MODE:
            raise CoarseSearchIntegrityError(
                "Wskazany plik nie jest pełnym manifestem classical/MLP coarse searchu: "
                f"mode={source.payload.get('mode')!r}."
            )
        return source

    valid_sources: list[ManifestSource] = []
    rejected: list[str] = []
    for path in discover_coarse_search_manifests(root):
        try:
            source = _load_source(root, path)
        except CoarseSearchReportingError as exc:
            rejected.append(f"{path}: {exc}")
            continue
        if source.payload.get("mode") != EXPECTED_MODE:
            rejected.append(
                f"{path}: mode={source.payload.get('mode')!r}, oczekiwano {EXPECTED_MODE!r}"
            )
            continue
        if source.payload.get("status") != "COMPLETE":
            rejected.append(
                f"{path}: status={source.payload.get('status')!r}, oczekiwano 'COMPLETE'"
            )
            continue
        if source.payload.get("source_kind") == "synthetic":
            rejected.append(f"{path}: syntetyczny run nie jest źródłem wyników pracy")
            continue
        valid_sources.append(source)

    if not valid_sources:
        detail = "\n".join(f"- {item}" for item in rejected[:10])
        suffix = f"\nOdrzucone pliki:\n{detail}" if detail else ""
        raise CoarseSearchArtifactNotFound(
            "Nie znaleziono pełnego canonical coarse-search manifestu. Notebook celowo "
            "nie używa real-data smoke testu i nie uruchamia nowego treningu. Oczekiwany "
            "plik to **/classical_mlp_coarse_search_manifest.json, zwykle pod "
            "data/model_runs/<run_id>/. Można też ustawić względną ścieżkę w "
            "MANIFEST_OVERRIDE lub zmiennej COARSE_SEARCH_MANIFEST."
            + suffix
        )

    by_hash: dict[str, list[ManifestSource]] = {}
    for source in valid_sources:
        by_hash.setdefault(source.sha256, []).append(source)
    if len(by_hash) == 1:
        identical = next(iter(by_hash.values()))
        return sorted(
            identical,
            key=lambda source: (
                not source.run_manifest_verified,
                len(source.relative_manifest_path),
                source.relative_manifest_path,
            ),
        )[0]

    verified = [source for source in valid_sources if source.run_manifest_verified]
    if len(verified) == 1:
        return verified[0]

    paths = "\n".join(
        f"- {source.relative_manifest_path} (sha256={source.sha256}, "
        f"run_manifest_verified={source.run_manifest_verified})"
        for source in valid_sources
    )
    raise AmbiguousCoarseSearchSource(
        "Znaleziono więcej niż jeden różny manifest coarse searchu. Nie wybrano "
        "arbitralnie źródła prawdy. Ustaw MANIFEST_OVERRIDE na jeden z plików:\n"
        + paths
    )


def _expected_coarse_positions_from_frozen_registry() -> int | None:
    try:
        from src.modeling.model_execution_contract import (  # type: ignore
            canonical_candidate_index,
            load_contract,
            load_registry,
        )

        index = canonical_candidate_index(load_contract(), load_registry())
        return sum(entry.get("stage") == "coarse" for entry in index)
    except Exception:
        return None


def _issue(
    issues: list[dict[str, Any]],
    severity: str,
    code: str,
    message: str,
    candidate_identity: str | None = None,
) -> None:
    issues.append(
        {
            "severity": severity,
            "code": code,
            "message": message,
            "candidate_identity": candidate_identity,
        }
    )




def _audit_authority_hashes(
    source: ManifestSource,
    issues: list[dict[str, Any]],
) -> None:
    """Verify that the result manifest points to the current frozen authorities."""

    root = source.project_root
    payload = source.payload
    runner_config_path = root / "configs/production_experiment_runner_v1_0_0.yaml"
    if not runner_config_path.is_file():
        _issue(
            issues,
            "ERROR",
            "RUNNER_CONFIG_MISSING",
            f"Brak {runner_config_path.relative_to(root).as_posix()}.",
        )
        return

    actual_runner_sha = file_sha256(runner_config_path)
    declared_runner_sha = payload.get("runner_config_sha256")
    if declared_runner_sha is None:
        _issue(
            issues,
            "WARNING",
            "RUNNER_CONFIG_SHA_NOT_DECLARED",
            "Manifest nie deklaruje runner_config_sha256.",
        )
    elif str(declared_runner_sha) != actual_runner_sha:
        _issue(
            issues,
            "ERROR",
            "RUNNER_CONFIG_SHA_MISMATCH",
            f"runner_config_sha256: manifest={declared_runner_sha}, repo={actual_runner_sha}.",
        )

    try:
        runner_config = yaml.safe_load(runner_config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        _issue(
            issues,
            "ERROR",
            "RUNNER_CONFIG_PARSE_ERROR",
            f"Nie można odczytać runner config: {exc}",
        )
        return
    if not isinstance(runner_config, Mapping):
        _issue(issues, "ERROR", "RUNNER_CONFIG_INVALID", "Runner config nie jest mappingiem.")
        return

    authority = runner_config.get("authority") or {}
    checks = (
        ("execution_contract", "contract_sha256"),
        ("candidate_registry", "candidate_registry_sha256"),
    )
    for authority_key, manifest_sha_key in checks:
        specification = authority.get(authority_key)
        if not isinstance(specification, Mapping) or "path" not in specification:
            _issue(
                issues,
                "ERROR",
                "AUTHORITY_PATH_MISSING",
                f"Runner config nie definiuje authority.{authority_key}.path.",
            )
            continue
        try:
            authority_path = _safe_path(root, str(specification["path"]))
        except CoarseSearchIntegrityError as exc:
            _issue(issues, "ERROR", "UNSAFE_AUTHORITY_PATH", str(exc))
            continue
        if not authority_path.is_file():
            _issue(
                issues,
                "ERROR",
                "AUTHORITY_FILE_MISSING",
                f"Brak authority file: {authority_path.relative_to(root).as_posix()}.",
            )
            continue
        actual_sha = file_sha256(authority_path)
        configured_sha = specification.get("sha256")
        if configured_sha is not None and str(configured_sha) != actual_sha:
            _issue(
                issues,
                "ERROR",
                "RUNNER_AUTHORITY_SHA_MISMATCH",
                f"authority.{authority_key}: config={configured_sha}, repo={actual_sha}.",
            )
        manifest_sha = payload.get(manifest_sha_key)
        if manifest_sha is None:
            _issue(
                issues,
                "WARNING",
                "RESULT_AUTHORITY_SHA_NOT_DECLARED",
                f"Manifest nie deklaruje {manifest_sha_key}.",
            )
        elif str(manifest_sha) != actual_sha:
            _issue(
                issues,
                "ERROR",
                "RESULT_AUTHORITY_SHA_MISMATCH",
                f"{manifest_sha_key}: manifest={manifest_sha}, repo={actual_sha}.",
            )

    declared_candidate_index_sha = payload.get("candidate_index_sha256")
    try:
        from src.modeling.model_execution_contract import (  # type: ignore
            canonical_candidate_index,
            canonical_sha256,
            load_contract,
            load_registry,
        )

        coarse_index = [
            entry
            for entry in canonical_candidate_index(load_contract(), load_registry())
            if entry.get("stage") == "coarse"
        ]
        actual_candidate_index_sha = canonical_sha256(coarse_index)
    except Exception:
        actual_candidate_index_sha = None
    if actual_candidate_index_sha is not None:
        if declared_candidate_index_sha is None:
            _issue(
                issues,
                "WARNING",
                "CANDIDATE_INDEX_SHA_NOT_DECLARED",
                "Manifest nie deklaruje candidate_index_sha256.",
            )
        elif str(declared_candidate_index_sha) != actual_candidate_index_sha:
            _issue(
                issues,
                "ERROR",
                "CANDIDATE_INDEX_SHA_MISMATCH",
                f"candidate_index_sha256: manifest={declared_candidate_index_sha}, "
                f"repo={actual_candidate_index_sha}.",
            )


def audit_manifest(
    source: ManifestSource,
    *,
    verify_oof_hashes: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Audit source integrity without recalculating saved metrics."""

    payload = source.payload
    reports = payload.get("candidate_results")
    issues: list[dict[str, Any]] = []
    _audit_authority_hashes(source, issues)

    if payload.get("schema_version") != 1:
        _issue(issues, "ERROR", "UNEXPECTED_SCHEMA_VERSION", "Oczekiwano schema_version=1.")
    if payload.get("mode") != EXPECTED_MODE:
        _issue(issues, "ERROR", "UNEXPECTED_MODE", f"mode={payload.get('mode')!r}")
    if payload.get("status") != "COMPLETE":
        _issue(
            issues,
            "ERROR",
            "RUN_NOT_COMPLETE",
            f"Manifest ma status={payload.get('status')!r}, oczekiwano COMPLETE.",
        )
    if payload.get("source_kind") == "synthetic":
        _issue(issues, "ERROR", "SYNTHETIC_SOURCE", "Syntetyczny run nie jest źródłem wyników pracy.")

    forbidden_true_flags = (
        "model_selection_performed",
        "refinement_performed",
        "qnn_performed",
        "calibration_or_threshold_performed",
        "robustness_or_interpretability_performed",
        "external_validation_or_test_opened",
        "protected_feature_years_opened",
    )
    for flag in forbidden_true_flags:
        if payload.get(flag) is True:
            _issue(
                issues,
                "ERROR",
                "STAGE_BOUNDARY_VIOLATION",
                f"Manifest ma {flag}=true; notebook ma dokumentować wyłącznie coarse search.",
            )

    if not isinstance(reports, list) or not reports:
        _issue(issues, "ERROR", "MISSING_CANDIDATE_RESULTS", "Brak niepustej listy candidate_results.")
        reports = []

    executed = payload.get("executed_candidate_positions")
    if executed is not None and int(executed) != len(reports):
        _issue(
            issues,
            "ERROR",
            "CANDIDATE_COUNT_MISMATCH",
            f"executed_candidate_positions={executed}, candidate_results={len(reports)}.",
        )
    frozen_expected = _expected_coarse_positions_from_frozen_registry()
    if frozen_expected is not None and len(reports) != frozen_expected:
        _issue(
            issues,
            "ERROR",
            "FROZEN_CANDIDATE_COUNT_MISMATCH",
            f"Frozen registry oczekuje {frozen_expected} pozycji coarse; znaleziono {len(reports)}.",
        )

    identities = [_candidate_identity(report) for report in reports]
    duplicate_count = len(identities) - len(set(identities))
    if duplicate_count:
        _issue(
            issues,
            "ERROR",
            "DUPLICATE_CANDIDATE_IDENTITY",
            f"Znaleziono {duplicate_count} zduplikowanych tożsamości konfiguracji.",
        )

    complete_count = 0
    missing_metric_count = 0
    missing_runtime_count = 0
    missing_oof_count = 0
    verified_oof_count = 0
    available_families: set[str] = set()
    complete_families: set[str] = set()
    available_blocks: set[str] = set()
    pooled_count_signatures: set[tuple[int, int]] = set()
    fold_count_signatures: dict[int, set[tuple[int, int]]] = {year: set() for year in EXPECTED_YEARS}

    required_report_fields = (
        "family",
        "configuration_id",
        "feature_block",
        "parameters",
        "training_seed",
        "status",
        "runtime_seconds",
    )
    for report in reports:
        identity = _identity_text(report)
        for field in required_report_fields:
            if field not in report:
                _issue(
                    issues,
                    "ERROR",
                    "MISSING_REPORT_FIELD",
                    f"Brakuje pola {field!r}.",
                    identity,
                )
        family = str(report.get("family"))
        block = str(report.get("feature_block"))
        available_families.add(family)
        available_blocks.add(block)
        if family == "qnn":
            _issue(
                issues,
                "ERROR",
                "QNN_PRESENT_IN_CLASSICAL_COARSE",
                "QNN nie może zmieniać rankingu classical/MLP coarse candidates.",
                identity,
            )
        manifest_seed = payload.get("training_seed")
        if manifest_seed is not None and int(report.get("training_seed", -1)) != int(manifest_seed):
            _issue(
                issues,
                "ERROR",
                "TRAINING_SEED_MISMATCH",
                f"Candidate seed={report.get('training_seed')}, manifest seed={manifest_seed}.",
                identity,
            )
        if family == "dummy_prior" and block != BLOCK_AGNOSTIC:
            _issue(
                issues,
                "ERROR",
                "DUMMY_BLOCK_MISMATCH",
                "Dummy powinien mieć wariant BLOCK_AGNOSTIC.",
                identity,
            )
        if family != "dummy_prior" and block not in BLOCK_ORDER:
            _issue(
                issues,
                "ERROR",
                "UNKNOWN_FEATURE_BLOCK",
                f"Nieoczekiwany wariant feature block: {block!r}.",
                identity,
            )

        runtime = report.get("runtime_seconds")
        if runtime is None or not math.isfinite(float(runtime)) or float(runtime) < 0:
            missing_runtime_count += 1
            _issue(
                issues,
                "ERROR" if report.get("status") == "COMPLETE" else "WARNING",
                "MISSING_OR_INVALID_RUNTIME",
                f"Nieprawidłowy runtime_seconds={runtime!r}.",
                identity,
            )

        if report.get("status") == "COMPLETE":
            complete_count += 1
            complete_families.add(family)
            pooled_n = report.get("pooled_oof_n")
            pooled_positive_n = report.get("pooled_oof_positive_n")
            if pooled_n is not None and pooled_positive_n is not None:
                pooled_count_signatures.add((int(pooled_n), int(pooled_positive_n)))
            for metric in ("pooled_oof_pr_auc", "pooled_oof_roc_auc"):
                value = report.get(metric)
                if value is None or not math.isfinite(float(value)):
                    missing_metric_count += 1
                    _issue(
                        issues,
                        "ERROR",
                        "MISSING_COMPLETE_METRIC",
                        f"Brakuje skończonej metryki {metric}.",
                        identity,
                    )
                elif not 0.0 <= float(value) <= 1.0:
                    _issue(
                        issues,
                        "ERROR",
                        "METRIC_OUT_OF_RANGE",
                        f"{metric}={value!r} poza zakresem [0, 1].",
                        identity,
                    )

            per_fold = report.get("per_fold")
            if not isinstance(per_fold, list):
                _issue(
                    issues,
                    "ERROR",
                    "MISSING_PER_FOLD_RESULTS",
                    "Brak listy per_fold dla kompletnej konfiguracji.",
                    identity,
                )
            else:
                years = [int(item.get("validation_feature_year", -1)) for item in per_fold]
                if tuple(years) != EXPECTED_YEARS:
                    _issue(
                        issues,
                        "ERROR",
                        "YEARLY_FOLD_SET_MISMATCH",
                        f"Oczekiwano lat {EXPECTED_YEARS}, otrzymano {years}.",
                        identity,
                    )
                for item in per_fold:
                    n = item.get("n")
                    positive_n = item.get("positive_n")
                    year = int(item.get("validation_feature_year", -1))
                    if n is not None and positive_n is not None and year in fold_count_signatures:
                        fold_count_signatures[year].add((int(n), int(positive_n)))
                    pr_auc = item.get("pr_auc")
                    roc_auc = item.get("roc_auc")
                    if n is None or positive_n is None or int(n) <= 0:
                        _issue(
                            issues,
                            "ERROR",
                            "INVALID_FOLD_COUNTS",
                            f"Nieprawidłowe n/positive_n w {item.get('fold_id')!r}.",
                            identity,
                        )
                    elif not 0 <= int(positive_n) <= int(n):
                        _issue(
                            issues,
                            "ERROR",
                            "INVALID_POSITIVE_COUNT",
                            f"positive_n={positive_n}, n={n}.",
                            identity,
                        )
                    for name, value in (("pr_auc", pr_auc), ("roc_auc", roc_auc)):
                        if value is None or not math.isfinite(float(value)):
                            _issue(
                                issues,
                                "ERROR",
                                "MISSING_FOLD_METRIC",
                                f"Brakuje {name} dla {item.get('fold_id')!r}.",
                                identity,
                            )

            relative_oof = report.get("canonical_oof_predictions")
            expected_sha = report.get("canonical_oof_predictions_sha256")
            if not relative_oof:
                missing_oof_count += 1
                _issue(
                    issues,
                    "WARNING",
                    "OOF_ARTIFACT_NOT_DECLARED",
                    "Brak ścieżki canonical_oof_predictions; użyte zostaną zapisane per-fold metrics.",
                    identity,
                )
            else:
                try:
                    oof_path = _safe_path(source.output_root, str(relative_oof))
                except CoarseSearchIntegrityError as exc:
                    _issue(issues, "ERROR", "UNSAFE_OOF_PATH", str(exc), identity)
                    continue
                if not oof_path.is_file():
                    missing_oof_count += 1
                    _issue(
                        issues,
                        "WARNING",
                        "OOF_ARTIFACT_MISSING",
                        f"Nie znaleziono {oof_path}.",
                        identity,
                    )
                elif verify_oof_hashes:
                    actual_sha = file_sha256(oof_path)
                    if expected_sha and actual_sha != str(expected_sha):
                        _issue(
                            issues,
                            "ERROR",
                            "OOF_SHA256_MISMATCH",
                            f"Oczekiwano {expected_sha}, otrzymano {actual_sha}.",
                            identity,
                        )
                    else:
                        verified_oof_count += 1
                else:
                    verified_oof_count += 1

    declared_families = payload.get("executed_families")
    if isinstance(declared_families, list) and set(map(str, declared_families)) != available_families:
        _issue(
            issues,
            "ERROR",
            "EXECUTED_FAMILIES_MISMATCH",
            f"executed_families={declared_families}, candidate families={sorted(available_families)}.",
        )
    if complete_count == 0:
        _issue(issues, "ERROR", "NO_COMPLETE_CANDIDATES", "Brak kompletnych coarse candidates.")
    if "dummy_prior" not in complete_families:
        _issue(issues, "ERROR", "DUMMY_BASELINE_MISSING", "Brak kompletnego dummy_prior.")
    if "fixed_l2_logistic" not in complete_families:
        _issue(issues, "ERROR", "FIXED_L2_BASELINE_MISSING", "Brak kompletnego fixed_l2_logistic.")
    if len(pooled_count_signatures) > 1:
        _issue(
            issues,
            "ERROR",
            "POOLED_OOF_COUNT_MISMATCH",
            f"Kompletne konfiguracje mają różne pooled n/positive_n: {sorted(pooled_count_signatures)}.",
        )
    for year, signatures in fold_count_signatures.items():
        if len(signatures) > 1:
            _issue(
                issues,
                "ERROR",
                "YEARLY_COUNT_MISMATCH",
                f"Rok {year} ma niespójne n/positive_n między konfiguracjami: {sorted(signatures)}.",
            )

    manifest_folds = payload.get("folds")
    if isinstance(manifest_folds, list):
        manifest_fold_counts = {
            int(item.get("validation_feature_year", -1)): (
                int(item.get("validation_n", -1)),
                int(item.get("validation_positive_n", -1)),
            )
            for item in manifest_folds
            if isinstance(item, Mapping)
        }
        for year in EXPECTED_YEARS:
            signatures = fold_count_signatures[year]
            if signatures and year in manifest_fold_counts and next(iter(signatures)) != manifest_fold_counts[year]:
                _issue(
                    issues,
                    "ERROR",
                    "MANIFEST_FOLD_SUMMARY_MISMATCH",
                    f"Rok {year}: candidate per_fold={next(iter(signatures))}, manifest folds={manifest_fold_counts[year]}.",
                )

    if not source.run_manifest_verified:
        _issue(
            issues,
            "WARNING",
            "RUN_MANIFEST_NOT_VERIFIED",
            "Brak zgodnego run_manifest.json lub brak zgodności SHA-256; źródło wybrano na podstawie pełnego manifestu.",
        )

    issues_df = pd.DataFrame(
        issues,
        columns=["severity", "code", "message", "candidate_identity"],
    )
    summary = pd.DataFrame(
        [
            {
                "manifest": source.relative_manifest_path,
                "manifest_sha256": source.sha256,
                "run_manifest_verified": source.run_manifest_verified,
                "candidate_positions": len(reports),
                "complete_candidate_positions": complete_count,
                "technically_invalid_positions": len(reports) - complete_count,
                "families": ", ".join(sorted(available_families, key=_family_rank)),
                "feature_blocks": ", ".join(sorted(available_blocks, key=_block_rank)),
                "duplicate_identities": duplicate_count,
                "missing_complete_metrics": missing_metric_count,
                "missing_or_invalid_runtime": missing_runtime_count,
                "oof_artifacts_verified_or_present": verified_oof_count,
                "oof_artifacts_missing_or_undeclared": missing_oof_count,
                "errors": int((issues_df["severity"] == "ERROR").sum()) if not issues_df.empty else 0,
                "warnings": int((issues_df["severity"] == "WARNING").sum()) if not issues_df.empty else 0,
            }
        ]
    )
    inventory = _build_inventory(reports)
    return summary, issues_df, inventory


def _family_rank(value: str) -> int:
    try:
        return FAMILY_ORDER.index(value)
    except ValueError:
        return len(FAMILY_ORDER)


def _block_rank(value: str) -> int:
    if value == BLOCK_AGNOSTIC:
        return -1
    try:
        return BLOCK_ORDER.index(value)
    except ValueError:
        return len(BLOCK_ORDER)


def _build_inventory(reports: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    rows = []
    for report in reports:
        rows.append(
            {
                "family": str(report.get("family")),
                "feature_block": str(report.get("feature_block")),
                "status": str(report.get("status")),
                "metric_missing": report.get("pooled_oof_pr_auc") is None,
                "runtime_missing": report.get("runtime_seconds") is None,
            }
        )
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    inventory = (
        frame.groupby(["family", "feature_block", "status"], dropna=False)
        .agg(
            configurations=("status", "size"),
            missing_pr_auc=("metric_missing", "sum"),
            missing_runtime=("runtime_missing", "sum"),
        )
        .reset_index()
    )
    inventory["family_order"] = inventory["family"].map(_family_rank)
    inventory["block_order"] = inventory["feature_block"].map(_block_rank)
    return inventory.sort_values(
        ["family_order", "block_order", "status"], kind="stable"
    ).drop(columns=["family_order", "block_order"]).reset_index(drop=True)


def _quantized_metric(value: float) -> Decimal:
    quantum = Decimal(1).scaleb(-6)
    return Decimal(str(float(value))).quantize(quantum, rounding=ROUND_HALF_EVEN)


def _fallback_ranking_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    complete = str(row.get("status")) == "COMPLETE"
    metric = row.get("pooled_oof_pr_auc")
    metric_key = (
        -_quantized_metric(float(metric))
        if complete and metric is not None and math.isfinite(float(metric))
        else Decimal("Infinity")
    )
    parameters = row.get("parameters") or {}
    imbalance = str(parameters.get("imbalance", "none"))
    return (
        0 if complete else 1,
        metric_key,
        _block_rank(str(row.get("feature_block"))),
        _family_rank(str(row.get("family"))),
        0 if imbalance == "none" else 1,
        json.dumps(parameters, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        str(row.get("configuration_id", "")).encode("utf-8"),
    )


def _rank_reports(
    reports: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    rows = [
        {
            "stage": "coarse",
            "family": str(report.get("family")),
            "feature_block": str(report.get("feature_block")),
            "configuration_id": str(report.get("configuration_id")),
            "parameters": report.get("parameters") or {},
            "training_seed": int(report.get("training_seed", -1)),
            "status": str(report.get("status")),
            "pooled_oof_pr_auc": report.get("pooled_oof_pr_auc"),
            "selected_ansatz_id": None,
        }
        for report in reports
    ]
    try:
        from src.modeling.model_execution_contract import (  # type: ignore
            load_contract,
            rank_candidates,
        )

        ranked = rank_candidates(rows, load_contract())
        return ranked, "frozen_model_execution_contract_v1_2_0"
    except Exception:
        return sorted(rows, key=_fallback_ranking_key), "documented_fallback_equivalent_for_coarse_ties"


def _family_label(family: str) -> str:
    return FAMILY_LABELS.get(family, family)


def _parameter_text(parameters: Any) -> str:
    if not isinstance(parameters, Mapping):
        return "{}"
    return json.dumps(parameters, ensure_ascii=False, sort_keys=True, separators=(", ", ": "))


def candidate_frame(
    reports: Sequence[Mapping[str, Any]],
) -> tuple[pd.DataFrame, str]:
    ranked, ranking_method = _rank_reports(reports)
    rank_map = {
        (
            str(row["family"]),
            str(row["feature_block"]),
            str(row["configuration_id"]),
            int(row["training_seed"]),
        ): rank
        for rank, row in enumerate(ranked, 1)
    }
    rows: list[dict[str, Any]] = []
    for report in reports:
        identity = _candidate_identity(report)
        n = report.get("pooled_oof_n")
        positive_n = report.get("pooled_oof_positive_n")
        positive_share = (
            float(positive_n) / float(n)
            if n not in (None, 0) and positive_n is not None
            else np.nan
        )
        rows.append(
            {
                "rank": rank_map[identity],
                "family": identity[0],
                "family_label": _family_label(identity[0]),
                "configuration_id": identity[2],
                "model_configuration": f"{_family_label(identity[0])} | {identity[2]}",
                "feature_block": identity[1],
                "parameters": report.get("parameters") or {},
                "parameters_display": _parameter_text(report.get("parameters") or {}),
                "training_seed": identity[3],
                "status": str(report.get("status")),
                "failure_code": report.get("failure_code"),
                "convergence_status": report.get("convergence_status"),
                "pooled_oof_n": n,
                "pooled_oof_positive_n": positive_n,
                "pooled_oof_positive_share": positive_share,
                "pooled_oof_pr_auc": report.get("pooled_oof_pr_auc"),
                "pooled_oof_roc_auc": report.get("pooled_oof_roc_auc"),
                "fold_pr_auc_mean": report.get("fold_pr_auc_mean"),
                "fold_pr_auc_sample_sd": report.get("fold_pr_auc_sample_sd"),
                "runtime_seconds": report.get("runtime_seconds"),
                "delta_pr_auc_vs_dummy": report.get("delta_pr_auc_vs_dummy"),
                "delta_pr_auc_vs_fixed_l2": report.get("delta_pr_auc_vs_fixed_l2"),
                "per_fold": report.get("per_fold"),
                "canonical_oof_predictions": report.get("canonical_oof_predictions"),
                "canonical_oof_predictions_sha256": report.get(
                    "canonical_oof_predictions_sha256"
                ),
                "candidate_manifest": report.get("candidate_manifest"),
                "candidate_manifest_sha256": report.get("candidate_manifest_sha256"),
                "identity": _identity_text(report),
            }
        )
    frame = pd.DataFrame(rows).sort_values("rank", kind="stable").reset_index(drop=True)
    return frame, ranking_method


def _complete(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.loc[
        (frame["status"] == "COMPLETE")
        & frame["pooled_oof_pr_auc"].notna()
        & frame["pooled_oof_roc_auc"].notna()
    ].copy()


def best_by_family(frame: pd.DataFrame) -> pd.DataFrame:
    complete = _complete(frame).sort_values("rank", kind="stable")
    return (
        complete.groupby("family", sort=False, group_keys=False)
        .head(1)
        .sort_values("rank", kind="stable")
        .reset_index(drop=True)
    )


def best_by_family_and_block(frame: pd.DataFrame) -> pd.DataFrame:
    complete = _complete(frame).sort_values("rank", kind="stable")
    leaders = (
        complete.groupby(["family", "feature_block"], sort=False, group_keys=False)
        .head(1)
        .copy()
    )
    leaders["family_order"] = leaders["family"].map(_family_rank)
    leaders["block_order"] = leaders["feature_block"].map(_block_rank)
    return (
        leaders.sort_values(["family_order", "block_order"], kind="stable")
        .drop(columns=["family_order", "block_order"])
        .reset_index(drop=True)
    )


def feature_block_overall(frame: pd.DataFrame) -> pd.DataFrame:
    complete = _complete(frame)
    complete = complete.loc[complete["feature_block"].isin(BLOCK_ORDER)].copy()
    rows: list[dict[str, Any]] = []
    for block in BLOCK_ORDER:
        subset = complete.loc[complete["feature_block"] == block].sort_values(
            "rank", kind="stable"
        )
        if subset.empty:
            continue
        leader = subset.iloc[0]
        rows.append(
            {
                "feature_block": block,
                "complete_candidates": len(subset),
                "best_family": leader["family"],
                "best_family_label": leader["family_label"],
                "best_configuration_id": leader["configuration_id"],
                "best_pooled_oof_pr_auc": leader["pooled_oof_pr_auc"],
                "leader_pooled_oof_roc_auc": leader["pooled_oof_roc_auc"],
                "leader_runtime_seconds": leader["runtime_seconds"],
                "median_pooled_oof_pr_auc": subset["pooled_oof_pr_auc"].median(),
                "mean_pooled_oof_pr_auc": subset["pooled_oof_pr_auc"].mean(),
                "median_runtime_seconds": subset["runtime_seconds"].median(),
                "total_runtime_seconds": subset["runtime_seconds"].sum(),
            }
        )
    return pd.DataFrame(rows)


def yearly_results_for_family_leaders(
    frame: pd.DataFrame,
    leaders: pd.DataFrame,
) -> pd.DataFrame:
    del frame
    rows: list[dict[str, Any]] = []
    for _, leader in leaders.iterrows():
        per_fold = leader.get("per_fold")
        if not isinstance(per_fold, list):
            continue
        for fold in per_fold:
            n = int(fold["n"])
            positive_n = int(fold["positive_n"])
            rows.append(
                {
                    "family": leader["family"],
                    "family_label": leader["family_label"],
                    "configuration_id": leader["configuration_id"],
                    "feature_block": leader["feature_block"],
                    "fold_id": fold["fold_id"],
                    "year": int(fold["validation_feature_year"]),
                    "n": n,
                    "positive_n": positive_n,
                    "positive_share": positive_n / n,
                    "pr_auc": float(fold["pr_auc"]),
                    "roc_auc": float(fold["roc_auc"]),
                    "runtime_seconds": float(fold.get("runtime_seconds", 0.0)),
                    "status": fold.get("status"),
                }
            )
    yearly = pd.DataFrame(rows)
    if not yearly.empty:
        yearly["family_order"] = yearly["family"].map(_family_rank)
        yearly = yearly.sort_values(
            ["family_order", "year"], kind="stable"
        ).drop(columns="family_order").reset_index(drop=True)
    return yearly


def pareto_frontier(frame: pd.DataFrame) -> pd.DataFrame:
    complete = _complete(frame)
    complete = complete.loc[
        complete["runtime_seconds"].notna()
        & np.isfinite(complete["runtime_seconds"].astype(float))
        & (complete["runtime_seconds"].astype(float) >= 0)
    ].copy()
    ordered = complete.sort_values(
        ["runtime_seconds", "pooled_oof_pr_auc"],
        ascending=[True, False],
        kind="stable",
    )
    frontier_indices: list[int] = []
    best_quality = -math.inf
    for index, row in ordered.iterrows():
        quality = float(row["pooled_oof_pr_auc"])
        if quality > best_quality:
            frontier_indices.append(index)
            best_quality = quality
    frontier = complete.loc[frontier_indices].sort_values(
        ["runtime_seconds", "pooled_oof_pr_auc"],
        ascending=[True, False],
        kind="stable",
    )
    return frontier.reset_index(drop=True)


def baseline_comparison(frame: pd.DataFrame, leaders: pd.DataFrame) -> pd.DataFrame:
    complete = _complete(frame).sort_values("rank", kind="stable")
    dummy = complete.loc[complete["family"] == "dummy_prior"].iloc[0]
    fixed = complete.loc[complete["family"] == "fixed_l2_logistic"].iloc[0]
    global_leader = complete.iloc[0]

    roles_by_identity: dict[str, list[str]] = {}
    row_by_identity: dict[str, pd.Series] = {}

    def add(row: pd.Series, role: str) -> None:
        identity = str(row["identity"])
        row_by_identity[identity] = row
        roles_by_identity.setdefault(identity, []).append(role)

    add(dummy, "Dummy")
    add(fixed, "fixed L2 logistic")
    for _, row in leaders.iterrows():
        add(row, f"prowizoryczny lider rodziny: {row['family_label']}")
    add(global_leader, "top coarse candidate")

    rows: list[dict[str, Any]] = []
    dummy_metric = float(dummy["pooled_oof_pr_auc"])
    fixed_metric = float(fixed["pooled_oof_pr_auc"])
    for identity, source_row in row_by_identity.items():
        metric = float(source_row["pooled_oof_pr_auc"])
        rows.append(
            {
                "role": "; ".join(dict.fromkeys(roles_by_identity[identity])),
                "family": source_row["family"],
                "family_label": source_row["family_label"],
                "configuration_id": source_row["configuration_id"],
                "feature_block": source_row["feature_block"],
                "pooled_oof_pr_auc": metric,
                "pooled_oof_roc_auc": source_row["pooled_oof_roc_auc"],
                "runtime_seconds": source_row["runtime_seconds"],
                "delta_pr_auc_vs_dummy": metric - dummy_metric,
                "delta_pr_auc_vs_fixed_l2": metric - fixed_metric,
                "identity": identity,
                "rank": source_row["rank"],
            }
        )
    return pd.DataFrame(rows).sort_values("rank", kind="stable").reset_index(drop=True)


def thesis_family_summary(
    leaders: pd.DataFrame,
    refinement_qualified: Sequence[Mapping[str, Any]] | None,
) -> pd.DataFrame:
    qualified = {
        str(item.get("family"))
        for item in (refinement_qualified or [])
        if isinstance(item, Mapping)
    }
    rows: list[dict[str, Any]] = []
    for _, row in leaders.sort_values("rank", kind="stable").iterrows():
        family = str(row["family"])
        if family in {"dummy_prior", "fixed_l2_logistic"}:
            status = "baseline"
        elif family in qualified:
            status = "kandydat do refinementu"
        else:
            status = "prowizoryczny lider rodziny"
        rows.append(
            {
                "Rodzina": row["family_label"],
                "Wariant": row["feature_block"],
                "Pooled OOF PR-AUC": row["pooled_oof_pr_auc"],
                "ROC-AUC": row["pooled_oof_roc_auc"],
                "Runtime [s]": row["runtime_seconds"],
                "Status": status,
                "configuration_id": row["configuration_id"],
            }
        )
    return pd.DataFrame(rows)


def _presentation_columns(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.drop(
        columns=[
            "parameters",
            "per_fold",
            "canonical_oof_predictions",
            "canonical_oof_predictions_sha256",
            "candidate_manifest",
            "candidate_manifest_sha256",
        ],
        errors="ignore",
    )


def _write_dataframe(frame: pd.DataFrame, base_path: Path) -> list[Path]:
    base_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path = base_path.with_suffix(".csv")
    frame.to_csv(csv_path, index=False, float_format="%.17g")
    written = [csv_path]
    md_path = base_path.with_suffix(".md")
    try:
        md_path.write_text(frame.to_markdown(index=False, floatfmt=".6f") + "\n", encoding="utf-8")
        written.append(md_path)
    except ImportError:
        pass
    return written


def _save_figure(fig: plt.Figure, base_path: Path) -> tuple[Path, Path]:
    base_path.parent.mkdir(parents=True, exist_ok=True)
    png_path = base_path.with_suffix(".png")
    svg_path = base_path.with_suffix(".svg")
    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    fig.savefig(svg_path, bbox_inches="tight")
    plt.close(fig)
    return png_path, svg_path


def _plot_best_by_family(leaders: pd.DataFrame, figures_dir: Path) -> tuple[Path, Path]:
    plot_data = leaders.sort_values("pooled_oof_pr_auc", ascending=True, kind="stable")
    fig, ax = plt.subplots(figsize=(11, 6.5))
    bars = ax.barh(plot_data["family_label"], plot_data["pooled_oof_pr_auc"])
    ax.set_xlim(0.0, 1.0)
    ax.set_xlabel("Pooled OOF PR-AUC")
    ax.set_ylabel("Rodzina modelu")
    ax.set_title("Najlepszy pooled OOF PR-AUC według rodziny — coarse search")
    ax.grid(axis="x", alpha=0.25)
    for bar, value in zip(bars, plot_data["pooled_oof_pr_auc"], strict=True):
        ax.text(
            min(float(value) + 0.01, 0.98),
            bar.get_y() + bar.get_height() / 2,
            f"{float(value):.4f}",
            va="center",
        )
    fig.tight_layout()
    return _save_figure(fig, figures_dir / "01_best_pooled_oof_pr_auc_by_family")


def _plot_feature_blocks(
    family_block: pd.DataFrame, figures_dir: Path
) -> tuple[Path, Path]:
    data = family_block.loc[
        family_block["feature_block"].isin(BLOCK_ORDER)
        & (family_block["family"] != "dummy_prior")
    ].copy()
    data["family_order"] = data["family"].map(_family_rank)
    data = data.sort_values(["family_order", "feature_block"], kind="stable")
    pivot = data.pivot(
        index="family_label", columns="feature_block", values="pooled_oof_pr_auc"
    ).reindex(columns=list(BLOCK_ORDER))
    ordered_labels = [
        _family_label(family)
        for family in FAMILY_ORDER
        if family != "dummy_prior" and family in set(data["family"])
    ]
    pivot = pivot.reindex(ordered_labels)
    fig, ax = plt.subplots(figsize=(13, 7))
    pivot.plot(kind="bar", ax=ax, width=0.82)
    ax.set_ylim(0.0, 1.0)
    ax.set_xlabel("Rodzina modelu")
    ax.set_ylabel("Najlepszy pooled OOF PR-AUC")
    ax.set_title("Porównanie wariantów L, L+D i L+D+R — wyniki rozwojowe OOF")
    ax.legend(title="Wariant")
    ax.grid(axis="y", alpha=0.25)
    ax.tick_params(axis="x", labelrotation=30)
    fig.tight_layout()
    return _save_figure(fig, figures_dir / "02_feature_block_comparison")


def _plot_yearly(yearly: pd.DataFrame, figures_dir: Path) -> tuple[Path, Path]:
    fig, ax = plt.subplots(figsize=(12.5, 7))
    ordered_families = sorted(yearly["family"].unique(), key=_family_rank)
    for family in ordered_families:
        subset = yearly.loc[yearly["family"] == family].sort_values("year")
        ax.plot(
            subset["year"],
            subset["pr_auc"],
            marker="o",
            label=str(subset["family_label"].iloc[0]),
        )
    ax.set_xticks(list(EXPECTED_YEARS))
    ax.set_ylim(0.0, 1.0)
    ax.set_xlabel("Rok walidacyjny")
    ax.set_ylabel("PR-AUC (OOF)")
    ax.set_title("PR-AUC według roku 2015–2020 — prowizoryczni liderzy rodzin")
    ax.grid(alpha=0.25)
    ax.legend(title="Rodzina", bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.tight_layout()
    return _save_figure(fig, figures_dir / "03_yearly_pr_auc_2015_2020")


def _plot_pr_vs_roc(frame: pd.DataFrame, figures_dir: Path) -> tuple[Path, Path]:
    data = _complete(frame)
    fig, ax = plt.subplots(figsize=(10, 7))
    for family in sorted(data["family"].unique(), key=_family_rank):
        subset = data.loc[data["family"] == family]
        ax.scatter(
            subset["pooled_oof_roc_auc"],
            subset["pooled_oof_pr_auc"],
            label=_family_label(family),
            alpha=0.72,
        )
    leader = data.sort_values("rank", kind="stable").iloc[0]
    ax.annotate(
        f"Prowizoryczny lider: {leader['family_label']}",
        (leader["pooled_oof_roc_auc"], leader["pooled_oof_pr_auc"]),
        xytext=(8, 8),
        textcoords="offset points",
    )
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    ax.set_xlabel("Pooled OOF ROC-AUC")
    ax.set_ylabel("Pooled OOF PR-AUC")
    ax.set_title("Pooled OOF PR-AUC względem ROC-AUC — coarse candidates")
    ax.grid(alpha=0.25)
    ax.legend(title="Rodzina", bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.tight_layout()
    return _save_figure(fig, figures_dir / "04_pooled_pr_auc_vs_roc_auc")


def _plot_pr_vs_runtime(
    frame: pd.DataFrame,
    frontier: pd.DataFrame,
    figures_dir: Path,
) -> tuple[Path, Path]:
    data = _complete(frame)
    data = data.loc[data["runtime_seconds"].astype(float) > 0].copy()
    fig, ax = plt.subplots(figsize=(10.5, 7))
    for family in sorted(data["family"].unique(), key=_family_rank):
        subset = data.loc[data["family"] == family]
        ax.scatter(
            subset["runtime_seconds"],
            subset["pooled_oof_pr_auc"],
            label=_family_label(family),
            alpha=0.72,
        )
    if not frontier.empty:
        ax.scatter(
            frontier["runtime_seconds"],
            frontier["pooled_oof_pr_auc"],
            marker="x",
            s=95,
            linewidths=1.7,
            label="Pareto frontier",
        )
    runtimes = data["runtime_seconds"].astype(float)
    use_log = bool(runtimes.min() > 0 and runtimes.max() / runtimes.min() >= 100)
    if use_log:
        ax.set_xscale("log")
    ax.set_xlabel("Runtime [s]" + (" — skala logarytmiczna" if use_log else ""))
    ax.set_ylabel("Pooled OOF PR-AUC")
    ax.set_ylim(0.0, 1.0)
    ax.set_title("Pooled OOF PR-AUC względem runtime — coarse search")
    ax.grid(alpha=0.25)
    ax.legend(title="Rodzina", bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.tight_layout()
    return _save_figure(fig, figures_dir / "05_pooled_pr_auc_vs_runtime")


def _summary_markdown(
    frame: pd.DataFrame,
    leaders: pd.DataFrame,
    yearly: pd.DataFrame,
    baseline: pd.DataFrame,
    frontier: pd.DataFrame,
    refinement_qualified: Sequence[Mapping[str, Any]] | None,
) -> str:
    complete = _complete(frame).sort_values("rank", kind="stable")
    leader = complete.iloc[0]
    dummy = complete.loc[complete["family"] == "dummy_prior"].iloc[0]
    fixed = complete.loc[complete["family"] == "fixed_l2_logistic"].iloc[0]
    leader_yearly = yearly.loc[yearly["identity"] == leader["identity"]] if "identity" in yearly else yearly.loc[
        (yearly["family"] == leader["family"])
        & (yearly["configuration_id"] == leader["configuration_id"])
        & (yearly["feature_block"] == leader["feature_block"])
    ]
    annual_min = float(leader_yearly["pr_auc"].min())
    annual_max = float(leader_yearly["pr_auc"].max())
    annual_range = annual_max - annual_min
    frontier_identities = set(frontier["identity"]) if "identity" in frontier else set()
    leader_on_frontier = str(leader["identity"]) in frontier_identities
    qualified_families = [
        _family_label(str(item.get("family")))
        for item in (refinement_qualified or [])
        if isinstance(item, Mapping)
    ]
    qualified_text = ", ".join(qualified_families) if qualified_families else "brak rodzin"
    del leaders, baseline
    return (
        "# Podsumowanie wyników rozwojowych OOF\n\n"
        f"W coarse searchu najwyższy pooled OOF PR-AUC uzyskał **{leader['family_label']}** "
        f"w wariancie **{leader['feature_block']}** (configuration_id: "
        f"`{leader['configuration_id']}`): **{float(leader['pooled_oof_pr_auc']):.6f}**. "
        "Jest to prowizoryczny lider klasycznej/MLP części coarse searchu; wynik nie jest finalny.\n\n"
        f"Bezwzględna przewaga PR-AUC nad Dummy wynosi "
        f"**{float(leader['pooled_oof_pr_auc']) - float(dummy['pooled_oof_pr_auc']):.6f}**, "
        f"a nad najlepszym fixed L2 logistic **{float(leader['pooled_oof_pr_auc']) - float(fixed['pooled_oof_pr_auc']):.6f}**. "
        "Różnice te nie są automatycznie dowodem istotności statystycznej.\n\n"
        f"Dla prowizorycznego lidera roczny PR-AUC w latach 2015–2020 mieści się od "
        f"**{annual_min:.6f}** do **{annual_max:.6f}** (rozstęp **{annual_range:.6f}**). "
        "Jest to opis zmienności między latami; bez osobnej analizy niepewności nie należy "
        "nadawać mu interpretacji testu stabilności.\n\n"
        f"Pareto frontier jakość–runtime obejmuje **{len(frontier)}** konfiguracji. "
        f"Prowizoryczny lider {'znajduje się' if leader_on_frontier else 'nie znajduje się'} "
        "na tej granicy. Nie wyznaczono arbitralnego jednego „najlepszego kompromisu”.\n\n"
        f"Do dalszego refinementu zgodnie z zapisanym manifestem kwalifikują się: "
        f"**{qualified_text}**.\n\n"
        "Wyników nie należy traktować jako finalnych: refinement, confirmation seeds i QNN "
        "należą do kolejnych etapów, a finalny holdout 2021–2024 nie jest używany w tej analizie.\n"
    )


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    raise TypeError(f"Nie można zserializować typu {type(value)!r}")


def _write_analysis_manifest(
    *,
    source: ManifestSource,
    output_dir: Path,
    ranking_method: str,
    generated_paths: Iterable[Path],
    integrity_summary: pd.DataFrame,
) -> Path:
    files = []
    for path in sorted(set(generated_paths), key=lambda item: item.as_posix()):
        if not path.is_file():
            continue
        files.append(
            {
                "path": path.relative_to(output_dir).as_posix(),
                "sha256": file_sha256(path),
                "bytes": path.stat().st_size,
            }
        )
    payload = {
        "schema_version": 1,
        "mode": "descriptive_classical_mlp_coarse_search_reporting",
        "source_manifest": source.relative_manifest_path,
        "source_manifest_sha256": source.sha256,
        "run_manifest_verified": source.run_manifest_verified,
        "ranking_method": ranking_method,
        "primary_metric": "pooled_oof_pr_auc_2015_2020",
        "validation_years": list(EXPECTED_YEARS),
        "model_fit_performed": False,
        "new_cross_validation_performed": False,
        "new_hyperparameter_search_performed": False,
        "refinement_performed": False,
        "confirmation_performed": False,
        "qnn_performed": False,
        "protected_feature_years_opened": False,
        "integrity_summary": integrity_summary.iloc[0].to_dict(),
        "generated_files": files,
    }
    path = output_dir / "analysis_manifest.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=_json_default)
        + "\n",
        encoding="utf-8",
    )
    return path


def build_coarse_search_report(
    *,
    project_root: Path | None = None,
    manifest_override: str | Path | None = None,
    output_dir: Path | None = None,
    verify_oof_hashes: bool = True,
) -> CoarseSearchReport:
    """Build all descriptive tables and figures from one canonical saved run."""

    root = find_project_root(project_root)
    source = select_canonical_manifest(root, manifest_override)
    integrity_summary, integrity_issues, inventory = audit_manifest(
        source, verify_oof_hashes=verify_oof_hashes
    )
    errors = integrity_issues.loc[integrity_issues["severity"] == "ERROR"]
    if not errors.empty:
        preview = "\n".join(
            f"- {row.code}: {row.message} ({row.candidate_identity or 'run'})"
            for row in errors.head(20).itertuples(index=False)
        )
        raise CoarseSearchIntegrityError(
            "Kontrola integralności canonical coarse-search manifestu zakończyła się błędem:\n"
            + preview
        )

    reports = list(source.payload["candidate_results"])
    candidates, ranking_method = candidate_frame(reports)
    leaders = best_by_family(candidates)
    family_block = best_by_family_and_block(candidates)
    block_overall = feature_block_overall(candidates)
    yearly = yearly_results_for_family_leaders(candidates, leaders)
    # A stable identity column simplifies downstream narrative and exports.
    if not yearly.empty:
        yearly["identity"] = yearly.apply(
            lambda row: (
                f"{row['family']}|{row['feature_block']}|{row['configuration_id']}|"
                f"seed={int(candidates.loc[(candidates['family'] == row['family']) & (candidates['feature_block'] == row['feature_block']) & (candidates['configuration_id'] == row['configuration_id']), 'training_seed'].iloc[0])}"
            ),
            axis=1,
        )
    frontier = pareto_frontier(candidates)
    baseline = baseline_comparison(candidates, leaders)
    top20 = _complete(candidates).sort_values("rank", kind="stable").head(20).copy()
    thesis_summary = thesis_family_summary(
        leaders, source.payload.get("refinement_qualified_families")
    )

    out = (output_dir or (root / "reports/coarse_search_thesis")).resolve()
    try:
        out.relative_to(root)
    except ValueError as exc:
        raise CoarseSearchReportingError(
            "Katalog wyjściowy powinien znajdować się wewnątrz repozytorium."
        ) from exc
    tables_dir = out / "tables"
    figures_dir = out / "figures"
    out.mkdir(parents=True, exist_ok=True)

    source_summary = pd.DataFrame(
        [
            {
                "source_manifest": source.relative_manifest_path,
                "source_manifest_sha256": source.sha256,
                "output_root": source.output_root.relative_to(root).as_posix(),
                "run_manifest": (
                    source.run_manifest_path.relative_to(root).as_posix()
                    if source.run_manifest_path is not None
                    else None
                ),
                "run_manifest_verified": source.run_manifest_verified,
                "mode": source.payload.get("mode"),
                "status": source.payload.get("status"),
                "source_kind": source.payload.get("source_kind"),
                "training_seed": source.payload.get("training_seed"),
                "runtime_seconds": source.payload.get("runtime_seconds"),
            }
        ]
    )

    tables: dict[str, pd.DataFrame] = {
        "best_by_family": _presentation_columns(leaders),
        "feature_blocks_overall": block_overall,
        "best_by_family_and_block": _presentation_columns(family_block),
        "yearly_pr_auc": yearly,
        "top20": _presentation_columns(top20),
        "baseline_comparison": baseline,
        "thesis_family_summary": thesis_summary,
        "pareto_frontier": _presentation_columns(frontier),
        "integrity_issues": integrity_issues,
        "inventory": inventory,
        "all_candidates": _presentation_columns(candidates),
    }

    generated_paths: list[Path] = []
    table_names = {
        "best_by_family": "01_best_model_by_family",
        "feature_blocks_overall": "02_feature_blocks_overall",
        "best_by_family_and_block": "03_best_by_family_and_feature_block",
        "yearly_pr_auc": "04_yearly_pr_auc_2015_2020",
        "top20": "05_top20_coarse_candidates",
        "baseline_comparison": "06_baseline_comparison",
        "thesis_family_summary": "07_thesis_family_summary",
        "pareto_frontier": "08_pareto_frontier_quality_runtime",
        "integrity_issues": "09_integrity_issues",
        "inventory": "10_candidate_inventory",
        "all_candidates": "11_all_coarse_candidates",
    }
    for key, frame in tables.items():
        generated_paths.extend(_write_dataframe(frame, tables_dir / table_names[key]))

    figure_pairs = {
        "best_by_family": _plot_best_by_family(leaders, figures_dir),
        "feature_blocks": _plot_feature_blocks(family_block, figures_dir),
        "yearly_pr_auc": _plot_yearly(yearly, figures_dir),
        "pr_auc_vs_roc_auc": _plot_pr_vs_roc(candidates, figures_dir),
        "pr_auc_vs_runtime": _plot_pr_vs_runtime(candidates, frontier, figures_dir),
    }
    figures = {key: paths[0] for key, paths in figure_pairs.items()}
    for paths in figure_pairs.values():
        generated_paths.extend(paths)

    summary_markdown = _summary_markdown(
        candidates,
        leaders,
        yearly,
        baseline,
        frontier,
        source.payload.get("refinement_qualified_families"),
    )
    summary_path = out / "summary.md"
    summary_path.write_text(summary_markdown, encoding="utf-8")
    generated_paths.append(summary_path)
    generated_paths.extend(_write_dataframe(source_summary, out / "source_summary"))
    generated_paths.extend(_write_dataframe(integrity_summary, out / "integrity_summary"))

    analysis_manifest_path = _write_analysis_manifest(
        source=source,
        output_dir=out,
        ranking_method=ranking_method,
        generated_paths=generated_paths,
        integrity_summary=integrity_summary,
    )

    return CoarseSearchReport(
        source=source,
        source_summary=source_summary,
        integrity_summary=integrity_summary,
        integrity_issues=integrity_issues,
        inventory=inventory,
        candidates=candidates,
        tables=tables,
        figures=figures,
        output_dir=out,
        summary_markdown=summary_markdown,
        ranking_method=ranking_method,
        analysis_manifest_path=analysis_manifest_path,
    )
