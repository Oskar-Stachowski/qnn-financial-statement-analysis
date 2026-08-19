"""Build the train/CV-safe raw X_t v1.1.0 resolver correction.

This module does not alter any frozen v1 file.  It first materializes a
2011--2020 projection from the mixed-period v1 CSV with a byte-level routing
guard: only the first three non-sensitive routing fields are inspected before
a protected-period row is discarded.  Company Facts objects are likewise
decoded only when their exact accession belongs to the allowed train
projection.

The feature formulas are reused from the frozen v1 function code object and
bound to the versioned resolver without mutating the frozen module or its
globals.
"""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import re
from types import FunctionType
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pandas as pd
import yaml

from src.data import primitive_resolver_v1_1 as semantic_v1_1
from src.data import x_t_pit as v1


BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = BASE_DIR / "configs/x_t_pit_v1_1_0.yaml"
_TRAIN_ROW_PREFIX = re.compile(rb"^([^,\r\n]*),([^,\r\n]*),(20[0-9]{2}),")
_TARGET_APPLICATION_ROW_PREFIX = re.compile(
    rb"^([^,\r\n]*),([^,\r\n]*),([^,\r\n]*),(20[0-9]{2}),"
)
_FLAT_JSON_OBJECT = re.compile(rb"\{[^{}]*\}")
_MANUAL_REVIEW_PREFIX = "manual_primary_statement_sign_review:"
_REVIEWED_PRIMITIVES = (
    "assets",
    "liabilities",
    "current_assets",
    "current_liabilities",
    "revenues",
)
_WORKER_STATE: dict[str, Any] = {}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_patch_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    if not isinstance(config, dict) or "x_t_patch" not in config:
        raise ValueError(f"Incomplete X_t v1.1 config: {path}")
    return config


def resolved_v1_1_config(patch_config: dict[str, Any]) -> dict[str, Any]:
    base_path = BASE_DIR / str(patch_config["x_t_patch"]["base_frozen_config"])
    config = v1.load_config(base_path)
    config["x_t"] = dict(config["x_t"])
    config["x_t"].update(
        {
            "version": str(patch_config["x_t_patch"]["version"]),
            "status": str(patch_config["x_t_patch"]["status"]),
            "feature_year_start": 2011,
            "feature_year_end": 2020,
            "development_year_start": 2011,
            "development_year_end": 2020,
            "test_years": [],
        }
    )
    return config


def materialize_train_projection(
    source_path: Path,
    destination_path: Path,
    *,
    maximum_feature_year: int = 2020,
) -> int:
    """Copy only allowed rows without decoding protected-period payloads."""

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination_path.with_suffix(destination_path.suffix + ".tmp")
    selected_rows = 0
    with source_path.open("rb") as source, temporary_path.open("wb") as destination:
        header = source.readline()
        expected = b"research_universe_company_year_id,cik10,feature_year,"
        if not header.startswith(expected):
            raise RuntimeError("Unexpected raw X_t routing-column prefix")
        destination.write(header)
        for raw_line in source:
            match = _TRAIN_ROW_PREFIX.match(raw_line)
            if match is None:
                raise RuntimeError("Unable to route raw X_t row without payload decoding")
            feature_year = int(match.group(3))
            if feature_year <= maximum_feature_year:
                destination.write(raw_line)
                selected_rows += 1
            elif feature_year not in {2021, 2022, 2023, 2024}:
                raise RuntimeError(f"Unexpected feature-year routing key: {feature_year}")
    temporary_path.replace(destination_path)
    return selected_rows


def materialize_target_application_train_projection(
    source_path: Path,
    destination_path: Path,
    *,
    maximum_feature_year: int = 2020,
) -> int:
    """Route the target-application artifact on its fourth field only."""

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination_path.with_suffix(destination_path.suffix + ".tmp")
    selected_rows = 0
    with source_path.open("rb") as source, temporary_path.open("wb") as destination:
        header = source.readline()
        expected = (
            b"research_universe_company_year_id,universe_anchor_accession,"
            b"cik10,feature_year,"
        )
        if not header.startswith(expected):
            raise RuntimeError("Unexpected target-application routing-column prefix")
        destination.write(header)
        for raw_line in source:
            match = _TARGET_APPLICATION_ROW_PREFIX.match(raw_line)
            if match is None:
                raise RuntimeError(
                    "Unable to route target-application row without payload decoding"
                )
            feature_year = int(match.group(4))
            if feature_year <= maximum_feature_year:
                destination.write(raw_line)
                selected_rows += 1
            elif feature_year not in {2021, 2022, 2023, 2024}:
                raise RuntimeError(f"Unexpected feature-year routing key: {feature_year}")
    temporary_path.replace(destination_path)
    return selected_rows


def _csv_prefix_field(raw_line: bytes, zero_based_index: int) -> bytes:
    """Return one early CSV field without parsing the remaining payload."""

    field_start = 0
    field_index = 0
    position = 0
    in_quotes = False
    while position < len(raw_line):
        byte = raw_line[position]
        if byte == ord('"'):
            if in_quotes and position + 1 < len(raw_line) and raw_line[position + 1] == ord('"'):
                position += 2
                continue
            in_quotes = not in_quotes
        elif byte == ord(",") and not in_quotes:
            if field_index == zero_based_index:
                return raw_line[field_start:position]
            field_index += 1
            field_start = position + 1
        elif byte in (ord("\r"), ord("\n")) and not in_quotes:
            if field_index == zero_based_index:
                return raw_line[field_start:position]
            break
        position += 1
    raise RuntimeError("CSV routing field is absent or record is unterminated")


def materialize_frozen_target_train_projection(
    source_path: Path,
    destination_path: Path,
    *,
    maximum_feature_year: int = 2020,
) -> int:
    """Route PIT-B v1 on field nine before its financial/target payload."""

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination_path.with_suffix(destination_path.suffix + ".tmp")
    selected_rows = 0
    with source_path.open("rb") as source, temporary_path.open("wb") as destination:
        header = source.readline()
        if _csv_prefix_field(header, 8) != b"feature_year":
            raise RuntimeError("Unexpected frozen-target feature-year column position")
        destination.write(header)
        for raw_line in source:
            raw_year = _csv_prefix_field(raw_line, 8).strip().strip(b'"')
            if not re.fullmatch(rb"20[0-9]{2}", raw_year):
                raise RuntimeError("Invalid frozen-target feature-year routing key")
            feature_year = int(raw_year)
            if feature_year <= maximum_feature_year:
                destination.write(raw_line)
                selected_rows += 1
            elif feature_year not in {2021, 2022}:
                raise RuntimeError(f"Unexpected frozen-target feature year: {feature_year}")
    temporary_path.replace(destination_path)
    return selected_rows


def _json_value_start(data: bytes, key: str, start: int, end: int) -> int | None:
    token = json.dumps(key, ensure_ascii=True).encode("ascii")
    position = data.find(token, start, end)
    if position < 0:
        return None
    position += len(token)
    while position < end and data[position] in b" \t\r\n":
        position += 1
    if position >= end or data[position] != ord(":"):
        return None
    position += 1
    while position < end and data[position] in b" \t\r\n":
        position += 1
    return position


def _matching_container_end(data: bytes, start: int, opener: int, closer: int) -> int:
    if start >= len(data) or data[start] != opener:
        raise RuntimeError("Expected JSON container opener")
    depth = 0
    in_string = False
    escaped = False
    for position in range(start, len(data)):
        byte = data[position]
        if in_string:
            if escaped:
                escaped = False
            elif byte == ord("\\"):
                escaped = True
            elif byte == ord('"'):
                in_string = False
            continue
        if byte == ord('"'):
            in_string = True
        elif byte == opener:
            depth += 1
        elif byte == closer:
            depth -= 1
            if depth == 0:
                return position + 1
    raise RuntimeError("Unterminated JSON container")


def _flat_objects(data: bytes, array_start: int, array_end: int) -> Iterable[bytes]:
    # SEC Company Facts unit entries are flat scalar mappings.  Matching the
    # flat objects in the native regex engine avoids a Python per-byte loop;
    # the separator checks make the assumption fail closed if the upstream
    # schema ever introduces nesting or another array item type.
    content = data[array_start + 1 : array_end - 1]
    position = 0
    for match in _FLAT_JSON_OBJECT.finditer(content):
        if content[position : match.start()].strip(b" \t\r\n,"):
            raise RuntimeError("Nested or non-object Company Facts USD item")
        yield match.group(0)
        position = match.end()
    if content[position:].strip(b" \t\r\n,"):
        raise RuntimeError("Unparsed Company Facts USD-array content")


def restricted_companyfacts_root(
    path: Path,
    *,
    allowed_accessions: set[str],
    required_tags: set[str],
) -> dict[str, Any]:
    """Decode financial fact objects only for explicitly allowed accessions."""

    if not path.exists():
        return {}
    data = path.read_bytes()
    facts: dict[str, Any] = {"us-gaap": {}}
    accession_pattern = re.compile(rb'"accn"\s*:\s*"([^"]+)"')
    for tag in sorted(required_tags):
        tag_start = _json_value_start(data, tag, 0, len(data))
        if tag_start is None or data[tag_start] != ord("{"):
            continue
        units_start = _json_value_start(data, "units", tag_start, len(data))
        if units_start is None or data[units_start] != ord("{"):
            continue
        usd_start = _json_value_start(data, "USD", units_start, len(data))
        if usd_start is None or data[usd_start] != ord("["):
            continue
        # Unit facts contain no nested arrays under the SEC schema.  Fail
        # closed rather than decoding anything if that contract changes.
        usd_close = data.find(b"]", usd_start + 1)
        if usd_close < 0:
            raise RuntimeError("Unterminated Company Facts USD array")
        usd_end = usd_close + 1
        if b"[" in data[usd_start + 1 : usd_close]:
            raise RuntimeError("Nested Company Facts USD array is unsupported")
        selected: list[dict[str, Any]] = []
        for raw_object in _flat_objects(data, usd_start, usd_end):
            accession_match = accession_pattern.search(raw_object)
            if accession_match is None:
                continue
            accession = accession_match.group(1).decode("ascii", errors="strict")
            if accession not in allowed_accessions:
                continue
            item = json.loads(raw_object)
            if not isinstance(item, dict) or str(item.get("accn", "")) != accession:
                raise RuntimeError("Company Facts accession routing mismatch")
            selected.append(item)
        if selected:
            facts["us-gaap"][tag] = {"units": {"USD": selected}}
    return facts


def reconstructed_negative_reviews(frame: pd.DataFrame) -> dict[tuple[str, str, str], dict[str, Any]]:
    reviews: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in frame.to_dict("records"):
        for primitive in _REVIEWED_PRIMITIVES:
            reason = str(row.get(f"current_t_{primitive}_reason", "") or "")
            if not reason.startswith(_MANUAL_REVIEW_PREFIX):
                continue
            key = (
                str(row["research_universe_company_year_id"]),
                str(row["anchor_accession"]),
                primitive,
            )
            reviews[key] = {
                "action": "ambiguous_na",
                "reason": reason.removeprefix(_MANUAL_REVIEW_PREFIX),
                "reconstructed_from_frozen_v1_train": True,
                "expected_tag": str(row.get(f"current_t_{primitive}_tag", "") or ""),
                "expected_strategy": str(
                    row.get(f"current_t_{primitive}_strategy", "") or ""
                ),
                "expected_accn": str(row.get(f"current_t_{primitive}_accn", "") or ""),
            }
    return reviews


def _apply_reconstructed_negative_review(
    selection: dict[str, Any],
    decision: dict[str, Any] | None,
) -> dict[str, Any]:
    if not decision or not decision.get("reconstructed_from_frozen_v1_train"):
        return v1.apply_negative_sign_review(selection, decision)
    if selection.get("status") != "selected" or selection.get("value") is None:
        raise RuntimeError("Frozen v1 negative review no longer has an upstream selection")
    for field, expected_key in (
        ("tag", "expected_tag"),
        ("strategy", "expected_strategy"),
        ("accn", "expected_accn"),
    ):
        expected = str(decision.get(expected_key, "") or "")
        if expected and str(selection.get(field, "") or "") != expected:
            raise RuntimeError(f"Frozen v1 negative-review provenance changed: {field}")
    result = dict(selection)
    result["value"] = None
    result["status"] = "ambiguous"
    result["reason"] = _MANUAL_REVIEW_PREFIX + str(decision["reason"])
    return result


_PROCESS_GLOBALS = dict(v1.process_eligible_row.__globals__)
_PROCESS_GLOBALS["semantic"] = semantic_v1_1
_PROCESS_GLOBALS["apply_negative_sign_review"] = _apply_reconstructed_negative_review
_PROCESS_ELIGIBLE_ROW = FunctionType(
    v1.process_eligible_row.__code__,
    _PROCESS_GLOBALS,
    name="process_eligible_row_v1_1",
    argdefs=v1.process_eligible_row.__defaults__,
    closure=v1.process_eligible_row.__closure__,
)
_PROCESS_ELIGIBLE_ROW.__kwdefaults__ = v1.process_eligible_row.__kwdefaults__


def source_rows_from_projection(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rename = {
        "anchor_accession": "accession",
        "anchor_form": "form",
        "anchor_filed": "filed",
        "anchor_accepted_at": "accepted_at",
        "anchor_period_end": "period_end",
        "anchor_document_fiscal_year_focus": "document_fiscal_year_focus",
        "anchor_document_fiscal_period_focus": "document_fiscal_period_focus",
        "anchor_xbrl_instance": "xbrl_instance",
    }
    metadata = list(v1.METADATA_COLUMNS)
    source = frame[metadata].rename(columns=rename).copy()
    return source.to_dict("records")


def _process_company(
    item: tuple[str, list[dict[str, Any]]],
    *,
    config: dict[str, Any],
    semantic_config: dict[str, Any],
    scope: semantic_v1_1.Scope,
    period_ends: dict[tuple[str, int], date],
    companyfacts_root: Path,
    evidence_root: Path,
    negative_sign_review: dict[tuple[str, str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    cik10, source_rows = item
    companyfacts_path = companyfacts_root / f"CIK{cik10}.json"
    relative_path = str(companyfacts_path.relative_to(BASE_DIR))
    allowed_accessions = {str(row.get("accession", "")) for row in source_rows}
    facts_root = restricted_companyfacts_root(
        companyfacts_path,
        allowed_accessions=allowed_accessions,
        required_tags=semantic_v1_1.required_tags(semantic_config),
    )
    accession_records = v1.records_by_accession(facts_root, semantic_config, scope)
    for source in source_rows:
        accession = str(source.get("accession", ""))
        if accession in accession_records:
            continue
        instance_records = v1.scope_xbrl_instance_records(
            source, semantic_config, scope
        )
        if instance_records:
            accession_records[accession].extend(instance_records)
    return [
        _PROCESS_ELIGIBLE_ROW(
            source,
            config=config,
            semantic_config=semantic_config,
            scope=scope,
            accession_records=accession_records,
            period_ends=period_ends,
            companyfacts_relative_path=relative_path,
            evidence_root=evidence_root,
            negative_sign_review=negative_sign_review,
        )
        for source in source_rows
    ]


def _initialize_worker(
    config: dict[str, Any],
    semantic_config: dict[str, Any],
    scope: semantic_v1_1.Scope,
    period_ends: dict[tuple[str, int], date],
    companyfacts_root: Path,
    evidence_root: Path,
    negative_sign_review: dict[tuple[str, str, str], dict[str, Any]],
) -> None:
    global _WORKER_STATE
    _WORKER_STATE = {
        "config": config,
        "semantic_config": semantic_config,
        "scope": scope,
        "period_ends": period_ends,
        "companyfacts_root": companyfacts_root,
        "evidence_root": evidence_root,
        "negative_sign_review": negative_sign_review,
    }


def _process_company_worker(
    item: tuple[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    if not _WORKER_STATE:
        raise RuntimeError("X_t v1.1 worker state was not initialized")
    return _process_company(item, **_WORKER_STATE)


def validate_train_artifact_path(
    path: Path,
    config: dict[str, Any],
    *,
    expected_rows: int,
) -> int:
    expected_columns = v1.output_columns(config)
    if list(pd.read_csv(path, nrows=0).columns) != expected_columns:
        raise RuntimeError("X_t v1.1 train schema differs from the frozen raw schema")
    validation_columns = [
        "research_universe_company_year_id",
        "feature_year",
        "split",
        "anchor_accession",
        "feature_policy_version",
    ]
    for primitive in v1.PRIMITIVES:
        for prefix in ("current_t", "comparative_tm1", "pair_current_t"):
            validation_columns.append(f"{prefix}_{primitive}_accn")
    for feature in v1.feature_names(config):
        validation_columns.extend([f"{feature}_status", f"{feature}_value"])
    seen: set[str] = set()
    row_count = 0
    for frame in pd.read_csv(
        path,
        usecols=validation_columns,
        dtype=str,
        keep_default_na=False,
        chunksize=2_000,
        low_memory=False,
    ):
        years = pd.to_numeric(frame["feature_year"], errors="raise").astype(int)
        if not years.between(2011, 2020).all() or not frame["split"].eq("train").all():
            raise RuntimeError("Protected or out-of-scope feature year entered X_t v1.1 train")
        if frame["feature_policy_version"].ne("1.1.0").any():
            raise RuntimeError("Unexpected X_t v1.1 feature-policy version")
        ids = frame["research_universe_company_year_id"].astype(str)
        if ids.duplicated().any() or any(item in seen for item in ids):
            raise RuntimeError("Duplicate X_t v1.1 company-year")
        seen.update(ids)
        for primitive in v1.PRIMITIVES:
            for prefix in ("current_t", "comparative_tm1", "pair_current_t"):
                selected_accn = frame[f"{prefix}_{primitive}_accn"]
                anchor_accn = frame["anchor_accession"]
                if (selected_accn.ne("") & selected_accn.ne(anchor_accn)).any():
                    raise RuntimeError(
                        f"Exact-accession invariant failed: {prefix}_{primitive}"
                    )
        for feature in v1.feature_names(config):
            available = frame[f"{feature}_status"].eq("available")
            values = pd.to_numeric(frame[f"{feature}_value"], errors="coerce")
            if (available & values.isna()).any() or (~available & values.notna()).any():
                raise RuntimeError(f"Feature status/value invariant failed: {feature}")
        row_count += len(frame)
    if row_count != expected_rows:
        raise RuntimeError(f"Expected {expected_rows:,} train rows, got {row_count:,}")
    return row_count


def materialize_fail_closed_correction(
    base_path: Path,
    source_candidate_path: Path,
    output_path: Path,
    config: dict[str, Any],
) -> dict[str, int]:
    """Apply only coverage-reducing resolver deltas to frozen v1 rows.

    The raw SEC cache is not itself content-addressed at the fact-file level,
    so a full contemporary source rebuild can contain unrelated source drift.
    This correction uses that rebuild only as resolver evidence and copies
    exactly old-selected -> new-ambiguous priority-barrier transitions.  Every
    other data/provenance cell remains the frozen v1 value.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    base_reader = pd.read_csv(base_path, chunksize=500, low_memory=False)
    candidate_reader = pd.read_csv(
        source_candidate_path, chunksize=500, low_memory=False
    )
    first_write = True
    row_count = 0
    current_cells = 0
    pair_cells = 0
    changed_ids: set[str] = set()
    for base, candidate in zip(base_reader, candidate_reader, strict=True):
        keys = ["research_universe_company_year_id", "cik10", "feature_year"]
        if not base[keys].fillna("").astype(str).equals(
            candidate[keys].fillna("").astype(str)
        ):
            raise RuntimeError("Source rebuild candidate is not aligned with frozen v1")
        corrected = base.copy()
        corrected["feature_policy_version"] = "1.1.0"
        for column in v1.ROW_DIAGNOSTIC_COLUMNS:
            corrected[column] = corrected[column].astype(object)
        changed_mask = pd.Series(False, index=base.index)
        current_masks: dict[str, pd.Series] = {}
        pair_masks: dict[str, pd.Series] = {}
        for primitive in v1.PRIMITIVES:
            current_mask = (
                base[f"current_t_{primitive}_status"].eq("selected")
                & candidate[f"current_t_{primitive}_status"].eq("ambiguous")
                & candidate[f"current_t_{primitive}_reason"].eq(
                    "higher_priority_context_ambiguous"
                )
            )
            pair_mask = (
                base[f"pair_{primitive}_status"].eq("selected")
                & candidate[f"pair_{primitive}_status"].eq("ambiguous")
                & candidate[f"pair_{primitive}_reason"].eq(
                    "higher_priority_context_ambiguous"
                )
            )
            current_masks[primitive] = current_mask
            pair_masks[primitive] = pair_mask
            if current_mask.any():
                current_columns = [
                    f"current_t_{primitive}_{field}" for field in v1.PROVENANCE_FIELDS
                ]
                corrected.loc[current_mask, current_columns] = candidate.loc[
                    current_mask, current_columns
                ].to_numpy()
                current_cells += int(current_mask.sum())
            if pair_mask.any():
                pair_columns = [
                    *[f"pair_{primitive}_{field}" for field in v1.PAIR_FIELDS],
                    *[
                        f"comparative_tm1_{primitive}_{field}"
                        for field in v1.PROVENANCE_FIELDS
                    ],
                    *[
                        f"pair_current_t_{primitive}_{field}"
                        for field in v1.PROVENANCE_FIELDS
                    ],
                ]
                corrected.loc[pair_mask, pair_columns] = candidate.loc[
                    pair_mask, pair_columns
                ].to_numpy()
                pair_cells += int(pair_mask.sum())
            changed_mask |= current_mask | pair_mask

        for feature in v1.feature_names(config):
            sources = base[f"{feature}_source_primitives"].fillna("").astype(str)
            roles = base[f"{feature}_source_roles"].fillna("").astype(str)
            feature_mask = pd.Series(False, index=base.index)
            for primitive in v1.PRIMITIVES:
                contains = sources.str.split(";").map(lambda items: primitive in items)
                feature_mask |= current_masks[primitive] & contains & roles.eq("current_t")
                feature_mask |= (
                    pair_masks[primitive]
                    & contains
                    & roles.str.contains("comparative_t_minus_1", regex=False)
                )
            if not feature_mask.any():
                continue
            feature_columns = [
                f"{feature}_{field}" for field in v1.FEATURE_FIELDS
            ]
            corrected.loc[feature_mask, feature_columns] = candidate.loc[
                feature_mask, feature_columns
            ].to_numpy()

        for index in corrected.index[changed_mask]:
            row = corrected.loc[index].to_dict()
            v1.finalize_row_status(row, config)
            for column in v1.ROW_DIAGNOSTIC_COLUMNS:
                corrected.at[index, column] = row[column]
        changed_ids.update(
            corrected.loc[changed_mask, "research_universe_company_year_id"].astype(str)
        )
        corrected.to_csv(
            temporary_path,
            mode="w" if first_write else "a",
            header=first_write,
            index=False,
            encoding="utf-8",
            lineterminator="\n",
            float_format="%.17g",
        )
        first_write = False
        row_count += len(corrected)
    temporary_path.replace(output_path)
    return {
        "rows": row_count,
        "changed_company_years": len(changed_ids),
        "current_primitive_cells": current_cells,
        "pair_primitive_cells": pair_cells,
    }


def build_raw_x_t_train(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    patch_config = load_patch_config(config_path)
    patch = patch_config["x_t_patch"]
    base_artifact = BASE_DIR / str(patch["base_frozen_artifact"])
    if sha256(base_artifact) != str(patch["base_frozen_artifact_sha256"]):
        raise RuntimeError("Frozen raw X_t v1 artifact hash changed")

    projection_path = BASE_DIR / str(patch_config["inputs"]["train_projection"])
    expected_rows = materialize_train_projection(base_artifact, projection_path)
    projection_columns = list(v1.METADATA_COLUMNS)
    for primitive in _REVIEWED_PRIMITIVES:
        projection_columns.extend(
            [
                f"current_t_{primitive}_reason",
                f"current_t_{primitive}_tag",
                f"current_t_{primitive}_strategy",
                f"current_t_{primitive}_accn",
            ]
        )
    projection = pd.read_csv(
        projection_path,
        usecols=list(dict.fromkeys(projection_columns)),
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    if len(projection) != expected_rows:
        raise RuntimeError("Train projection row count changed after parsing")
    if not pd.to_numeric(projection["feature_year"], errors="raise").between(2011, 2020).all():
        raise RuntimeError("Train projection contains a protected feature year")

    config = resolved_v1_1_config(patch_config)
    semantic_config = semantic_v1_1.load_config(
        BASE_DIR / str(patch_config["inputs"]["primitive_policy"])
    )
    base_scope = semantic_v1_1.parse_scope(semantic_config)
    pit = config["point_in_time"]
    scope = replace(
        base_scope,
        feature_year_start=2011,
        feature_year_end=2020,
        annual_period_min_days=int(pit["annual_period_min_days"]),
        annual_period_max_days=int(pit["annual_period_max_days"]),
        period_start_tolerance_days=int(pit["period_start_tolerance_days"]),
        minimum_denominator_usd=0.0,
    )
    source_rows = source_rows_from_projection(projection)
    period_ends = {
        (str(row["cik10"]).zfill(10), int(row["feature_year"])): date.fromisoformat(
            str(row["period_end"])
        )
        for row in source_rows
        if str(row.get("period_end", ""))
    }
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in source_rows:
        grouped[str(row["cik10"]).zfill(10)].append(row)
    items = [(cik10, grouped[cik10]) for cik10 in sorted(grouped)]
    negative_sign_review = reconstructed_negative_reviews(projection)
    companyfacts_root = BASE_DIR / str(patch_config["inputs"]["companyfacts"])
    evidence_root = BASE_DIR / str(
        patch_config["inputs"]["revenue_statement_evidence"]
    )

    workers = max(1, int(os.environ.get("X_T_V1_1_WORKERS", "8")))
    columns = v1.output_columns(config)
    candidate_path = BASE_DIR / str(
        patch_config["outputs"]["source_rebuild_candidate"]
    )
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = candidate_path.with_suffix(candidate_path.suffix + ".tmp")
    processed_rows = 0
    first_write = True
    buffer: list[dict[str, Any]] = []
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=_initialize_worker,
        initargs=(
            config,
            semantic_config,
            scope,
            period_ends,
            companyfacts_root,
            evidence_root,
            negative_sign_review,
        ),
    ) as executor:
        for company_rows in executor.map(_process_company_worker, items, chunksize=8):
            buffer.extend(company_rows)
            if len(buffer) < 500:
                continue
            chunk = pd.DataFrame(buffer).reindex(columns=columns)
            chunk.to_csv(
                temporary_path,
                mode="w" if first_write else "a",
                header=first_write,
                index=False,
                encoding="utf-8",
                lineterminator="\n",
                float_format="%.17g",
            )
            processed_rows += len(chunk)
            first_write = False
            buffer = []
    if buffer:
        chunk = pd.DataFrame(buffer).reindex(columns=columns)
        chunk.to_csv(
            temporary_path,
            mode="w" if first_write else "a",
            header=first_write,
            index=False,
            encoding="utf-8",
            lineterminator="\n",
            float_format="%.17g",
        )
        processed_rows += len(chunk)
    if processed_rows != expected_rows:
        raise RuntimeError(
            f"Expected {expected_rows:,} rebuilt rows, got {processed_rows:,}"
        )
    validate_train_artifact_path(
        temporary_path, config, expected_rows=expected_rows
    )
    temporary_path.replace(candidate_path)
    output_path = BASE_DIR / str(patch_config["outputs"]["raw_train_artifact"])
    correction = materialize_fail_closed_correction(
        projection_path, candidate_path, output_path, config
    )
    validate_train_artifact_path(output_path, config, expected_rows=expected_rows)

    manifest = {
        "artifact_id": "x_t_pit",
        "artifact_version": "1.1.0",
        "status": patch["status"],
        "scope": "train_cv_2011_2020_only",
        "built_at_utc": datetime.now(tz=ZoneInfo("UTC")).isoformat(),
        "data_access_policy": str(patch["access_policy"]),
        "protected_feature_years_opened": False,
        "models_trained": False,
        "historical_v1_modified": False,
        "base_v1_artifact": str(patch["base_frozen_artifact"]),
        "base_v1_artifact_sha256": sha256(base_artifact),
        "train_projection": str(projection_path.relative_to(BASE_DIR)),
        "train_projection_sha256": sha256(projection_path),
        "raw_train_artifact": str(output_path.relative_to(BASE_DIR)),
        "raw_train_artifact_rows": processed_rows,
        "raw_train_artifact_columns": len(columns),
        "raw_train_artifact_sha256": sha256(output_path),
        "source_rebuild_candidate": str(candidate_path.relative_to(BASE_DIR)),
        "source_rebuild_candidate_sha256": sha256(candidate_path),
        "fail_closed_correction": correction,
        "config": str(config_path.relative_to(BASE_DIR)),
        "config_sha256": sha256(config_path),
        "construction_code": "src/data/x_t_pit_v1_1.py",
        "construction_code_sha256": sha256(BASE_DIR / "src/data/x_t_pit_v1_1.py"),
        "resolver_code": "src/data/primitive_resolver_v1_1.py",
        "resolver_code_sha256": sha256(
            BASE_DIR / "src/data/primitive_resolver_v1_1.py"
        ),
        "frozen_v1_formula_code": "src/data/x_t_pit.py",
        "frozen_v1_formula_code_sha256": sha256(BASE_DIR / "src/data/x_t_pit.py"),
    }
    manifest_path = BASE_DIR / str(patch_config["outputs"]["build_manifest"])
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest
