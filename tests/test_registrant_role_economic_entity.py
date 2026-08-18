from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = BASE_DIR / "src" / "data" / "24_audit_registrant_role_economic_entity.py"
SPEC = importlib.util.spec_from_file_location("registrant_role_audit", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_source_role_splits_non_xbrl_from_joint_co_registrant() -> None:
    single = pd.Series(
        {
            "joint_filing_flag": False,
            "registrant_role": "co_registrant_or_non_xbrl_registrant",
        }
    )
    joint = pd.Series(
        {
            "joint_filing_flag": True,
            "registrant_role": "co_registrant_or_non_xbrl_registrant",
        }
    )
    assert MODULE.source_role(single) == "single_filer_non_xbrl_registrant"
    assert MODULE.source_role(joint) == "joint_co_registrant"


def test_primary_statement_mapper_keeps_two_distinct_audited_scopes(tmp_path: Path) -> None:
    primary = tmp_path / "primary.htm"
    primary.write_text(
        """
        <html><body>
        Report of Independent Registered Public Accounting Firm to Alpha Corp.
        We have audited the accompanying consolidated balance sheets of Alpha Corp.
        and the consolidated statements of operations and cash flows.
        {filler}
        Report of Independent Registered Public Accounting Firm to Beta LLC.
        We have audited the accompanying consolidated balance sheets of Beta LLC
        and the consolidated statements of income and cash flows.
        </body></html>
        """.format(filler="x" * 2000),
        encoding="utf-8",
    )
    evidence = MODULE.statement_scope_from_primary(
        primary,
        [
            {"cik10": "0000000001", "company_name": "ALPHA CORP"},
            {"cik10": "0000000002", "company_name": "BETA LLC"},
        ],
    )
    assert json.loads(evidence["audit_scope_cik_groups"]) == [
        ["0000000001"],
        ["0000000002"],
    ]


def test_joint_connected_components_prevent_cik_level_split_leakage() -> None:
    joint = pd.DataFrame(
        {
            "accession": ["a", "a", "b", "b", "c", "c"],
            "cik10": ["1", "2", "2", "3", "8", "9"],
        }
    )
    groups = MODULE.connected_joint_groups(joint)
    assert groups["1"] == groups["2"] == groups["3"]
    assert groups["8"] == groups["9"]
    assert groups["1"] != groups["8"]


def test_manual_series_expands_to_accession_decisions() -> None:
    decisions = MODULE.load_manual_decisions()
    ferrellgas = decisions["0001558370-19-008908"]
    assert ferrellgas["series_id"] == "ferrellgas_four_separate_statement_scopes"
    assert set(ferrellgas["statement_entity_ciks"]) == {
        "0000922358",
        "0000922359",
        "0000922360",
        "0001012493",
    }


def test_verified_nonoperating_coissuer_is_not_classified_as_duplicate() -> None:
    row = pd.Series(
        {
            "scope_status": "resolved",
            "scope_reason": "manual_four_distinct_audited_statement_scopes",
            "statement_entity_ciks": "0000000001;0000000002",
            "eligible_ciks": "0000000001;0000000002",
            "non_operating_issuer_ciks": "0000000002",
            "cik10": "0000000002",
        }
    )
    status, action, _ = MODULE.classify_joint_row(row)
    assert status == "separate_reporting_entity_nonoperating_coissuer"
    assert action == "exclude_nonoperating_issuer"
