"""Generate thesis-ready methodology diagrams from frozen aggregate metadata.

The module is reporting-only. It reads configuration, documentation metadata
and two compact aggregate CSV tables. It does not deserialize row-level
protected data, fit models, generate predictions or recompute model results.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable, Mapping, Sequence

_MPL_CACHE = Path(tempfile.gettempdir()) / "qnn_thesis_methodology_figures_mpl"
_MPL_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MPL_CACHE))
os.environ.setdefault("XDG_CACHE_HOME", str(_MPL_CACHE / "xdg"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402
import numpy as np  # noqa: E402
import yaml  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs/thesis_methodology_figures_v1_0_0.yaml"
DEFAULT_OUTPUT = ROOT / "reports/thesis_methodology_figures_v1_0_0"
REPORT_ID = "thesis_methodology_figures_v1_0_0"

NAVY = "#193B66"
BLUE = "#3E7CB1"
LIGHT_BLUE = "#EAF2F8"
TEAL = "#2B7A78"
LIGHT_TEAL = "#E5F3F1"
AMBER = "#D89A32"
LIGHT_AMBER = "#FFF3D9"
RED = "#B3424A"
LIGHT_RED = "#FBEAEC"
PURPLE = "#68558A"
LIGHT_PURPLE = "#EFEAF7"
INK = "#16283D"
MID_GREY = "#687583"
LIGHT_GREY = "#EEF1F4"
GRID = "#D7DEE6"
WHITE = "#FFFFFF"

matplotlib.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.titlesize": 15,
        "axes.titleweight": "bold",
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.color": MID_GREY,
        "ytick.color": MID_GREY,
        "svg.hashsalt": REPORT_ID,
    }
)


class MethodologyFigureError(RuntimeError):
    """Raised when a frozen reporting invariant is violated."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MethodologyFigureError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_yaml(path: Path) -> dict[str, Any]:
    _require(path.is_file() and not path.is_symlink(), f"Missing YAML: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), f"Expected YAML mapping: {path}")
    return payload


def _read_csv(path: Path) -> list[dict[str, str]]:
    _require(path.is_file() and not path.is_symlink(), f"Missing CSV: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    _require(bool(rows), f"Empty CSV: {path}")
    return rows


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    _require(bool(rows), f"Refusing to write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(str(key))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _source_path(config: Mapping[str, Any], key: str) -> Path:
    relative = str(config["sources"][key])
    path = (ROOT / relative).resolve()
    _require(path.is_relative_to(ROOT), f"Source escapes repository: {relative}")
    _require(path.is_file() and not path.is_symlink(), f"Missing source: {relative}")
    return path


def _source_provenance(
    config: Mapping[str, Any], config_path: Path
) -> list[dict[str, Any]]:
    paths = [config_path.resolve(), Path(__file__).resolve()]
    paths.extend(_source_path(config, key) for key in config["sources"])
    unique = sorted(set(paths), key=lambda path: str(path.relative_to(ROOT)))
    return [
        {
            "source_path": str(path.relative_to(ROOT)),
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
            "content_scope": (
                "aggregate_or_method_metadata_only"
                if path != Path(__file__).resolve()
                else "report_generator"
            ),
            "protected_row_level_content": False,
        }
        for path in unique
    ]


def _validate_sources(config: Mapping[str, Any]) -> dict[str, Any]:
    expected = config["expected_values"]
    pipeline = _load_yaml(_source_path(config, "supervised_pipeline"))
    historical = _load_yaml(_source_path(config, "historical_pipeline_method"))
    access = _load_yaml(_source_path(config, "access_policy"))
    selection = _read_csv(_source_path(config, "selection_flow"))
    periods = _read_csv(_source_path(config, "period_boundaries"))

    scope = pipeline["authoritative_scope"]
    _require(scope["feature_years"] == [2011, 2020], "Unexpected train years.")
    _require(
        scope["protected_feature_years"] == [2021, 2022, 2023, 2024],
        "Unexpected protected years.",
    )
    _require(scope["protected_values_opened"] is False, "Protected values marked open.")
    sample = pipeline["supervised_sample"]
    _require(
        int(sample["train_n"]) == int(expected["supervised_sample_n"]),
        "Supervised sample count changed.",
    )

    method = historical["supervised_ml_pipeline"]
    temporal = historical["temporal_cv"]
    preprocessing = historical["preprocessing"]["main_variant"]
    _require(method["status"] == "frozen", "Historical pipeline is not frozen.")
    _require(temporal["validation_window_years"] == 1, "CV window changed.")
    _require(temporal["label_embargo_years"] == 1, "Embargo changed.")
    _require(
        temporal["future_year_in_training_allowed"] is False, "Future training allowed."
    )
    _require(
        temporal["target_availability_rule"]
        == "target_available_at <= min(prediction_timestamp_in_validation_fold)",
        "Target cutoff rule changed.",
    )
    _require(preprocessing["fit_scope"] == "train_partition_only", "Fit scope changed.")
    _require(
        preprocessing["cv_fit_scope"] == "fold_train_partition_only",
        "Fold preprocessing scope changed.",
    )
    _require(
        preprocessing["validation_operation"] == "transform_only",
        "Validation fit detected.",
    )

    access_periods = access["periods"]
    _require(
        access_periods["spent_development_2021_2022"]["status"]
        == "design_exposed_spent_development_period",
        "Spent-development status changed.",
    )
    _require(
        access_periods["temporal_holdout_2023_2024"]["fully_unseen_holdout"] is False,
        "Unsupported fully-unseen holdout status.",
    )

    selection_by_stage = {row["etap"]: row for row in selection}
    selection_expectations = {
        "Aktualny raw X_t train-only": int(expected["train_pool_n"]),
        "Po wymogu split=train i membership=eligible": int(expected["train_pool_n"]),
        "Po wymogu dostępnego targetu": int(expected["target_available_n"]),
        "Po wymogu zaakceptowanego X_t status": int(expected["supervised_sample_n"]),
    }
    for stage, count in selection_expectations.items():
        _require(stage in selection_by_stage, f"Missing selection stage: {stage}")
        _require(
            int(selection_by_stage[stage]["n"]) == count, f"Count changed: {stage}"
        )

    period_by_role = {row["period_role"]: row for row in periods}
    _require(
        set(period_by_role) == {"development", "spent_development", "holdout"},
        "Period roles changed.",
    )
    _require(
        period_by_role["development"]["years"] == "2015-2020 OOF",
        "Development years changed.",
    )
    _require(
        period_by_role["spent_development"]["years"] == "2021-2022",
        "Spent years changed.",
    )
    _require(
        period_by_role["holdout"]["years"] == "2023-2024", "Holdout years changed."
    )
    _require(
        all(row["fully_unseen_claim_allowed"] == "False" for row in periods),
        "A fully-unseen claim unexpectedly became allowed.",
    )
    return {
        "pipeline": pipeline,
        "historical": historical,
        "access": access,
        "selection": selection,
        "periods": periods,
    }


def _pipeline_rows() -> list[dict[str, Any]]:
    return [
        {
            "order": 1,
            "stage": "Filing-first universe PIT",
            "content": "Historyczne membership i dokładny anchor accession",
            "leakage_risk": "Survivorship/current-snapshot bias; późniejszy filing",
            "safeguard": "Zamrożone historyczne membership; immutable hash; bez ponownego rankowania filingów",
            "source_path": "configs/supervised_ml_pipeline_v1.yaml",
        },
        {
            "order": 2,
            "stage": "Cechy X_t",
            "content": "Cechy t wyłącznie z exact anchor 10-K za t",
            "leakage_risk": "Fallback do 10-K/A, kolejnego 10-K lub informacji t+1",
            "safeguard": "Brak fallbacku; point-in-time timestamp; późniejszy filing i t+1 niedozwolone",
            "source_path": "docs/06_1_point_in_time_x_t_feature_pipeline_audit_and_policy.md",
        },
        {
            "order": 3,
            "stage": "Target PIT-B",
            "content": "Etykieta t+1 z jawnym target_available_at",
            "leakage_risk": "Użycie etykiety zanim była dostępna",
            "safeguard": "target_available_at nie później niż cutoff predykcji walidacyjnej",
            "source_path": "configs/supervised_ml_pipeline_v1.yaml",
        },
        {
            "order": 4,
            "stage": "Próba supervised",
            "content": "eligible + target available + zaakceptowany x_t_status",
            "leakage_risk": "Dryf membership lub selekcja według wyniku",
            "safeguard": "Zamrożona reguła i SHA-256 dokładnego zbioru identyfikatorów",
            "source_path": "configs/supervised_ml_pipeline_v1_2_0.yaml",
        },
        {
            "order": 5,
            "stage": "Temporal CV",
            "content": "6 expanding-window foldów; walidacja 2015–2020",
            "leakage_risk": "Przyszłe lata lub niedostępne targety w train",
            "safeguard": "Roczny embargo + temporal order + cutoff target_available_at",
            "source_path": "configs/supervised_ml_pipeline_v1.yaml",
        },
        {
            "order": 6,
            "stage": "Preprocessing i fit",
            "content": "Winsoryzacja, imputacja, scaling i model osobno w foldzie",
            "leakage_risk": "Statystyki validation w preprocessing lub treningu",
            "safeguard": "Fit wyłącznie na fold-train; validation tylko transform/predict",
            "source_path": "configs/supervised_ml_pipeline_v1.yaml",
        },
        {
            "order": 7,
            "stage": "OOF i wybór",
            "content": "Pooled OOF AP 2015–2020; seed-averaged raw scores",
            "leakage_risk": "Wybór po wyniku okresów chronionych",
            "safeguard": "Ranking zamknięty na development; chronione wyniki nie aktywują zmian",
            "source_path": "configs/model_stage_v1.yaml",
        },
        {
            "order": 8,
            "stage": "Okresy chronione",
            "content": "2021–2022 spent; 2023–2024 temporal holdout",
            "leakage_risk": "Tuning po otwarciu lub twierdzenie fully unseen",
            "safeguard": "Wersjonowane gates, hash predykcji przed label gate, no-tune/no-reselection",
            "source_path": "configs/data_access_policy_v1_1_0.yaml",
        },
    ]


def _timeline_rows(period_source: Sequence[Mapping[str, str]]) -> list[dict[str, Any]]:
    source_by_role = {row["period_role"]: row for row in period_source}
    return [
        {
            "order": 1,
            "period_role": "training_history",
            "years": "2011-2014",
            "start_year": 2011,
            "end_year": 2014,
            "display_label": "Historia treningowa",
            "allowed_use": "Początkowe okna train\ndla temporal CV",
            "prohibited_claim": "Nie jest osobnym okresem\nraportowania wyników",
            "exposure_disclosure": "Brak walidacji OOF w tych latach",
            "source_path": "configs/supervised_ml_pipeline_v1.yaml",
        },
        {
            "order": 2,
            "period_role": "development",
            "years": "2015-2020",
            "start_year": 2015,
            "end_year": 2020,
            "display_label": "Development OOF",
            "allowed_use": "Wybór i ranking modeli;\npooled OOF",
            "prohibited_claim": "Nie jest niezależnym testem\npost-selection",
            "exposure_disclosure": source_by_role["development"][
                "mandatory_disclosure"
            ],
            "source_path": "reports/primary_thesis_reporting_v1_0_0/tables/03_period_boundaries.csv",
        },
        {
            "order": 3,
            "period_role": "spent_development",
            "years": "2021-2022",
            "start_year": 2021,
            "end_year": 2022,
            "display_label": "Spent development",
            "allowed_use": "Secondary evidence;\nbez zmian metody",
            "prohibited_claim": "Nie jest independent\nvalidation",
            "exposure_disclosure": source_by_role["spent_development"][
                "mandatory_disclosure"
            ],
            "source_path": "reports/primary_thesis_reporting_v1_0_0/tables/03_period_boundaries.csv",
        },
        {
            "order": 4,
            "period_role": "holdout",
            "years": "2023-2024",
            "start_year": 2023,
            "end_year": 2024,
            "display_label": "Temporal holdout",
            "allowed_use": "Zamrożona ocena czasowa;\nbez zmian metody",
            "prohibited_claim": "Nie jest fully unseen",
            "exposure_disclosure": source_by_role["holdout"]["mandatory_disclosure"],
            "source_path": "reports/primary_thesis_reporting_v1_0_0/tables/03_period_boundaries.csv",
        },
    ]


def _waterfall_rows(expected: Mapping[str, Any]) -> list[dict[str, Any]]:
    pool = int(expected["train_pool_n"])
    target = int(expected["target_available_n"])
    final = int(expected["supervised_sample_n"])
    return [
        {
            "order": 1,
            "stage": "Pula train 2011–2020",
            "bar_type": "total_start",
            "delta_n": pool,
            "n_after_stage": pool,
            "retention_vs_train_pct": 100.0,
            "source_path": "reports/classical_eda_for_thesis/tables/01_selection_flow.csv",
        },
        {
            "order": 2,
            "stage": "Usunięte: target PIT-B niedostępny",
            "bar_type": "decrease",
            "delta_n": target - pool,
            "n_after_stage": target,
            "retention_vs_train_pct": 100.0 * target / pool,
            "source_path": "reports/classical_eda_for_thesis/tables/01_selection_flow.csv",
        },
        {
            "order": 3,
            "stage": "Usunięte: niedopuszczony x_t_status",
            "bar_type": "decrease",
            "delta_n": final - target,
            "n_after_stage": final,
            "retention_vs_train_pct": 100.0 * final / pool,
            "source_path": "reports/classical_eda_for_thesis/tables/01_selection_flow.csv",
        },
        {
            "order": 4,
            "stage": "Finalna próba supervised",
            "bar_type": "total_end",
            "delta_n": final,
            "n_after_stage": final,
            "retention_vs_train_pct": 100.0 * final / pool,
            "source_path": "reports/classical_eda_for_thesis/tables/01_selection_flow.csv",
        },
    ]


def _box(
    axis: plt.Axes,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    body: str,
    *,
    face: str,
    edge: str,
    number: int | None = None,
    title_size: float = 10.5,
    body_size: float = 8.6,
) -> None:
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.015,rounding_size=0.05",
        linewidth=1.3,
        edgecolor=edge,
        facecolor=face,
        zorder=2,
    )
    axis.add_patch(patch)
    if number is not None:
        circle = plt.Circle((x + 0.18, y + height - 0.18), 0.12, color=edge, zorder=3)
        axis.add_patch(circle)
        axis.text(
            x + 0.18,
            y + height - 0.18,
            str(number),
            color=WHITE,
            ha="center",
            va="center",
            fontsize=8,
            fontweight="bold",
            zorder=4,
        )
        title_x = x + 0.36
    else:
        title_x = x + 0.16
    axis.text(
        title_x,
        y + height - 0.14,
        title,
        ha="left",
        va="top",
        fontsize=title_size,
        fontweight="bold",
        color=edge,
        zorder=4,
    )
    axis.text(
        x + 0.16,
        y + height - 0.48,
        body,
        ha="left",
        va="top",
        fontsize=body_size,
        color=INK,
        linespacing=1.32,
        zorder=4,
    )


def _arrow(
    axis: plt.Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    color: str = MID_GREY,
) -> None:
    axis.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=12,
            linewidth=1.25,
            color=color,
            shrinkA=2,
            shrinkB=2,
            zorder=1,
        )
    )


def _save_figure(fig: plt.Figure, base: Path) -> None:
    base.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        base.with_suffix(".png"),
        dpi=200,
        bbox_inches="tight",
        facecolor=WHITE,
        metadata={"Software": REPORT_ID},
    )
    fig.savefig(
        base.with_suffix(".svg"),
        bbox_inches="tight",
        facecolor=WHITE,
        metadata={"Date": None, "Creator": REPORT_ID},
    )
    plt.close(fig)


def _plot_pipeline(output_base: Path) -> None:
    fig, axis = plt.subplots(figsize=(16, 9))
    axis.set_xlim(0, 16)
    axis.set_ylim(0, 9)
    axis.axis("off")
    fig.patch.set_facecolor(WHITE)

    axis.text(
        0.45,
        8.62,
        "Pipeline badawczy i zabezpieczenia przed leakage",
        fontsize=18,
        fontweight="bold",
        color=NAVY,
    )
    axis.text(
        0.45,
        8.28,
        "Każda strzałka oznacza przepływ zamrożonych artefaktów; statystyki uczące nie przepływają wstecz z walidacji ani okresów chronionych.",
        fontsize=10.2,
        color=MID_GREY,
    )

    axis.text(
        0.48,
        7.75,
        "WARSTWA DANYCH POINT-IN-TIME",
        fontsize=9.2,
        fontweight="bold",
        color=BLUE,
    )
    top_y, top_h, top_w = 5.93, 1.5, 3.35
    xs = [0.45, 4.35, 8.25, 12.15]
    _box(
        axis,
        xs[0],
        top_y,
        top_w,
        top_h,
        "Universe filing-first",
        "Historyczne membership\n+ exact anchor accession",
        face=LIGHT_BLUE,
        edge=BLUE,
        number=1,
    )
    _box(
        axis,
        xs[1],
        top_y,
        top_w,
        top_h,
        "Cechy Xₜ",
        "Tylko filing t i informacje\n dostępne w timestampie t",
        face=LIGHT_BLUE,
        edge=BLUE,
        number=2,
    )
    _box(
        axis,
        xs[2],
        top_y,
        top_w,
        top_h,
        "Target PIT-B",
        "Etykieta t+1 z jawnym\n target_available_at",
        face=LIGHT_PURPLE,
        edge=PURPLE,
        number=3,
    )
    _box(
        axis,
        xs[3],
        top_y,
        top_w,
        top_h,
        "Próba supervised",
        "eligible + target available\n+ zaakceptowany x_t_status",
        face=LIGHT_TEAL,
        edge=TEAL,
        number=4,
    )
    for first, second in zip(xs[:-1], xs[1:]):
        _arrow(axis, (first + top_w, top_y + top_h / 2), (second, top_y + top_h / 2))

    axis.text(
        0.48,
        5.42,
        "WARSTWA MODELOWANIA I OCENY",
        fontsize=9.2,
        fontweight="bold",
        color=NAVY,
    )
    lower_y, lower_h = 3.58, 1.5
    _box(
        axis,
        xs[0],
        lower_y,
        top_w,
        lower_h,
        "Temporal CV",
        "6 expanding-window foldów\n+ roczny embargo",
        face=LIGHT_BLUE,
        edge=NAVY,
        number=5,
    )
    _box(
        axis,
        xs[1],
        lower_y,
        top_w,
        lower_h,
        "Preprocessing + fit",
        "Nowa instancja na fold-train;\nwalidacja = transform/predict",
        face=LIGHT_BLUE,
        edge=NAVY,
        number=6,
    )
    _box(
        axis,
        xs[2],
        lower_y,
        top_w,
        lower_h,
        "OOF 2015–2020",
        "Pooled OOF AP; ranking tylko\nna development",
        face=LIGHT_TEAL,
        edge=TEAL,
        number=7,
    )
    _box(
        axis,
        xs[3],
        lower_y,
        top_w,
        lower_h,
        "Okresy chronione",
        "Wersjonowane gates; no-tune;\nrole raportowane osobno",
        face=LIGHT_AMBER,
        edge=AMBER,
        number=8,
    )
    for first, second in zip(xs[:-1], xs[1:]):
        _arrow(
            axis,
            (first + top_w, lower_y + lower_h / 2),
            (second, lower_y + lower_h / 2),
        )
    _arrow(
        axis,
        (xs[3] + top_w / 2, top_y),
        (xs[0] + top_w / 2, lower_y + lower_h),
        color=TEAL,
    )

    axis.text(
        0.48, 3.03, "KLUCZOWE BARIERY", fontsize=9.2, fontweight="bold", color=RED
    )
    safeguards = [
        ("A", "Brak późniejszych filingów\ni informacji t+1 w Xₜ"),
        ("B", "target_available_at ≤\ncutoff walidacji"),
        ("C", "Fit preprocessingu wyłącznie\nna fold-train"),
        ("D", "SHA-256 membership, configów\ni artefaktów"),
        ("E", "Protected results nie mogą\naktywować tuningu ani reselekcji"),
    ]
    guard_xs = np.linspace(0.45, 13.0, len(safeguards))
    guard_w = 2.55
    for x, (letter, text) in zip(guard_xs, safeguards):
        patch = FancyBboxPatch(
            (x, 1.35),
            guard_w,
            1.18,
            boxstyle="round,pad=0.015,rounding_size=0.05",
            linewidth=1.0,
            edgecolor=RED,
            facecolor=LIGHT_RED,
        )
        axis.add_patch(patch)
        axis.text(
            x + 0.18,
            2.30,
            letter,
            ha="center",
            va="center",
            color=WHITE,
            fontsize=8.5,
            fontweight="bold",
            bbox={"boxstyle": "circle,pad=0.28", "facecolor": RED, "edgecolor": RED},
        )
        axis.text(
            x + 0.43,
            2.30,
            "SAFEGUARD",
            ha="left",
            va="center",
            color=RED,
            fontsize=8.4,
            fontweight="bold",
        )
        axis.text(
            x + 0.15,
            1.93,
            text,
            ha="left",
            va="top",
            color=INK,
            fontsize=8.2,
            linespacing=1.28,
        )

    axis.text(
        0.45,
        0.55,
        "Granica interpretacji: wyniki są warunkowe względem filing-first membership, dostępnego targetu PIT-B i dopuszczonego x_t_status; economic_group_id pozostaje metadanym klastrowym, nie predyktorem.",
        fontsize=9.2,
        color=MID_GREY,
    )
    _save_figure(fig, output_base)


def _plot_timeline(rows: Sequence[Mapping[str, Any]], output_base: Path) -> None:
    colors = {
        "training_history": (LIGHT_GREY, MID_GREY),
        "development": (LIGHT_BLUE, BLUE),
        "spent_development": (LIGHT_AMBER, AMBER),
        "holdout": (LIGHT_PURPLE, PURPLE),
    }
    fig, axis = plt.subplots(figsize=(16, 8.5))
    axis.set_xlim(2010.55, 2024.85)
    axis.set_ylim(0, 8.4)
    axis.axis("off")
    fig.patch.set_facecolor(WHITE)

    axis.text(
        2010.65,
        8.05,
        "Oś czasu: development, spent development i temporal holdout",
        fontsize=18,
        fontweight="bold",
        color=NAVY,
    )
    axis.text(
        2010.65,
        7.70,
        "Role okresów są rozłączne i nie tworzą jednego pooled estimandu.",
        fontsize=10.2,
        color=MID_GREY,
    )

    bar_y, bar_h = 5.65, 1.05
    for row in rows:
        start, end = int(row["start_year"]), int(row["end_year"])
        face, edge = colors[str(row["period_role"])]
        rect = Rectangle(
            (start - 0.46, bar_y),
            end - start + 0.92,
            bar_h,
            facecolor=face,
            edgecolor=edge,
            linewidth=1.5,
        )
        axis.add_patch(rect)
        center = (start + end) / 2
        axis.text(
            center,
            bar_y + 0.68,
            str(row["display_label"]),
            ha="center",
            va="center",
            color=edge,
            fontsize=10.5,
            fontweight="bold",
        )
        axis.text(
            center,
            bar_y + 0.28,
            str(row["years"]),
            ha="center",
            va="center",
            color=INK,
            fontsize=9.2,
        )

    for year in range(2011, 2025):
        axis.text(
            year, 5.34, str(year), ha="center", va="top", fontsize=8.5, color=MID_GREY
        )
        axis.plot([year, year], [5.55, 5.65], color=MID_GREY, linewidth=0.8)

    axis.plot([2020.5, 2020.5], [5.05, 7.15], color=RED, linestyle="--", linewidth=1.4)
    axis.text(
        2020.5,
        7.24,
        "Freeze selekcji i metodologii",
        ha="center",
        va="bottom",
        fontsize=9.3,
        color=RED,
        fontweight="bold",
    )
    axis.annotate(
        "protected results → brak tuningu / reselekcji",
        xy=(2020.55, 5.10),
        xytext=(2022.65, 4.77),
        arrowprops={"arrowstyle": "-|>", "color": RED, "lw": 1.1},
        ha="center",
        va="top",
        fontsize=8.7,
        color=RED,
    )

    card_y, card_h = 1.35, 2.65
    widths = [3.55, 5.10, 2.35, 2.35]
    starts = [2010.68, 2014.48, 2019.83, 2022.35]
    for row, x, width in zip(rows, starts, widths):
        face, edge = colors[str(row["period_role"])]
        patch = FancyBboxPatch(
            (x, card_y),
            width,
            card_h,
            boxstyle="round,pad=0.02,rounding_size=0.06",
            facecolor=face,
            edgecolor=edge,
            linewidth=1.2,
        )
        axis.add_patch(patch)
        axis.text(
            x + 0.16,
            card_y + card_h - 0.18,
            str(row["display_label"]),
            ha="left",
            va="top",
            fontsize=10,
            fontweight="bold",
            color=edge,
        )
        axis.text(
            x + 0.16,
            card_y + card_h - 0.58,
            "DOZWOLONA ROLA",
            ha="left",
            va="top",
            fontsize=7.5,
            fontweight="bold",
            color=MID_GREY,
        )
        axis.text(
            x + 0.16,
            card_y + card_h - 0.82,
            str(row["allowed_use"]),
            ha="left",
            va="top",
            fontsize=8.2,
            color=INK,
            wrap=True,
        )
        prohibited_header = (
            "NIEDOZWOLONE" if width < 3.0 else "NIEDOZWOLONE TWIERDZENIE"
        )
        axis.text(
            x + 0.16,
            card_y + 1.10,
            prohibited_header,
            ha="left",
            va="top",
            fontsize=7.5,
            fontweight="bold",
            color=MID_GREY,
        )
        axis.text(
            x + 0.16,
            card_y + 0.83,
            str(row["prohibited_claim"]),
            ha="left",
            va="top",
            fontsize=8.2,
            color=RED,
            fontweight="bold",
            wrap=True,
        )

    axis.text(
        2010.68,
        0.62,
        "2021–2022: wcześniej ujawnione agregaty projektu próby/cech/targetu.  2023–2024: prior aggregate oraz label exposure są ujawnione; okres nie jest fully unseen.",
        fontsize=9.1,
        color=MID_GREY,
    )
    _save_figure(fig, output_base)


def _plot_waterfall(rows: Sequence[Mapping[str, Any]], output_base: Path) -> None:
    pool = int(rows[0]["n_after_stage"])
    target = int(rows[1]["n_after_stage"])
    final = int(rows[2]["n_after_stage"])
    x = np.arange(4)
    heights = [pool, pool - target, target - final, final]
    bottoms = [0, target, final, 0]
    colors = [NAVY, RED, AMBER, TEAL]
    labels = [
        "Pula train\n2011–2020",
        "Brak targetu\nPIT-B",
        "Niedopuszczony\nx_t_status",
        "Finalna próba\nsupervised",
    ]

    fig, axis = plt.subplots(figsize=(13.5, 8.2))
    fig.patch.set_facecolor(WHITE)
    axis.bar(
        x,
        heights,
        bottom=bottoms,
        width=0.64,
        color=colors,
        edgecolor=WHITE,
        linewidth=1.0,
        zorder=3,
    )
    axis.set_ylim(0, 53000)
    axis.set_xlim(-0.65, 4.25)
    axis.set_xticks(x, labels)
    axis.tick_params(axis="x", length=0, labelsize=10)
    axis.set_ylabel("Liczba obserwacji emitent–rok", fontsize=10.5)
    axis.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.spines["bottom"].set_color(GRID)
    axis.set_title(
        "Waterfall selekcji głównej próby modelowej",
        loc="left",
        pad=24,
        color=NAVY,
        fontsize=18,
    )
    axis.text(
        -0.64,
        51500,
        "Train 2011–2020: dominującym filtrem jest dostępność porównywalnego targetu PIT-B.",
        fontsize=10.2,
        color=MID_GREY,
    )

    axis.plot(
        [x[0] + 0.32, x[1] - 0.32],
        [pool, pool],
        color=MID_GREY,
        linewidth=1.0,
        linestyle=":",
    )
    axis.plot(
        [x[1] + 0.32, x[2] - 0.32],
        [target, target],
        color=MID_GREY,
        linewidth=1.0,
        linestyle=":",
    )
    axis.plot(
        [x[2] + 0.32, x[3] - 0.32],
        [final, final],
        color=MID_GREY,
        linewidth=1.0,
        linestyle=":",
    )

    axis.text(
        x[0],
        pool + 1150,
        f"{pool:,}".replace(",", " "),
        ha="center",
        va="bottom",
        fontsize=12,
        fontweight="bold",
        color=NAVY,
    )
    axis.text(
        x[1],
        target + (pool - target) / 2,
        f"−{pool - target:,}".replace(",", " "),
        ha="center",
        va="center",
        fontsize=12,
        fontweight="bold",
        color=WHITE,
    )
    axis.annotate(
        f"−{target - final}\n(0,24% puli)",
        xy=(x[2], final + (target - final) / 2),
        xytext=(x[2] + 0.18, 26000),
        arrowprops={"arrowstyle": "-|>", "color": AMBER, "lw": 1.3},
        ha="left",
        va="center",
        fontsize=10,
        fontweight="bold",
        color=AMBER,
    )
    axis.text(
        x[3],
        final + 1150,
        f"{final:,}".replace(",", " "),
        ha="center",
        va="bottom",
        fontsize=12,
        fontweight="bold",
        color=TEAL,
    )

    axis.text(
        x[1],
        target - 900,
        f"pozostaje {target:,}  |  {100 * target / pool:.2f}%".replace(
            ",", " "
        ).replace(".", ","),
        ha="center",
        va="top",
        fontsize=9,
        color=MID_GREY,
    )
    axis.text(
        x[3],
        final - 900,
        f"retencja {100 * final / pool:.2f}%".replace(".", ","),
        ha="center",
        va="top",
        fontsize=9.5,
        color=WHITE,
        fontweight="bold",
    )

    note = FancyBboxPatch(
        (3.55, 34500),
        0.52,
        12300,
        transform=axis.transData,
        boxstyle="round,pad=0.02,rounding_size=0.03",
        facecolor=LIGHT_BLUE,
        edgecolor=BLUE,
        linewidth=1.1,
    )
    axis.add_patch(note)
    axis.text(
        3.81,
        45200,
        "WAŻNY MIANOWNIK",
        ha="center",
        va="top",
        fontsize=8.1,
        fontweight="bold",
        color=BLUE,
    )
    axis.text(
        3.81,
        42400,
        "41,03%",
        ha="center",
        va="top",
        fontsize=14,
        fontweight="bold",
        color=NAVY,
    )
    axis.text(
        3.81, 39200, "19 671 / 47 938", ha="center", va="top", fontsize=8.4, color=INK
    )
    axis.text(
        3.81,
        36300,
        "próba modelowa\n≠ full universe",
        ha="center",
        va="top",
        fontsize=8.1,
        color=MID_GREY,
    )

    axis.text(
        -0.62,
        -5200,
        "Uwaga: coverage pełnego filing-first universe 2011–2024 wynosi osobno 26 602 / 64 901 = 40,99%. Nie należy mieszać tych dwóch populacji bazowych.",
        fontsize=9.1,
        color=MID_GREY,
        transform=axis.transData,
    )
    _save_figure(fig, output_base)


def _readme() -> str:
    return """# Figury metodologiczne do pracy — v1.0.0

Status: **COMPLETE — REPORTING ONLY**

Pakiet zawiera trzy wersjonowane grafiki w formatach PNG i SVG:

1. pipeline badawczy i zabezpieczenia przed leakage;
2. oś czasu ról development / spent development / temporal holdout;
3. waterfall selekcji głównej próby modelowej.

Grafiki powstały z zamrożonych konfiguracji i kompaktowych tabel agregatowych.
Nie otwarto danych wierszowych okresów chronionych, nie dopasowano modeli i nie
przeliczono wyników predykcyjnych.

## Zalecane użycie

- SVG: finalny skład DOCX/PDF, jeśli edytor zachowuje grafikę wektorową.
- PNG: wersja kompatybilna, 200 dpi.
- Tabele CSV: audyt liczb, etykiet i źródeł użytych na wykresach.

Waterfall dotyczy próby modelowej train 2011–2020: `47 938 → 19 784 → 19 671`.
Nie należy utożsamiać jego mianownika z pełnym filing-first universe 2011–2024,
dla którego target availability wynosi `26 602 / 64 901 = 40,99%`.
"""


def _manifest(
    output_dir: Path, provenance: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    files = sorted(
        path
        for path in output_dir.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    )
    return {
        "schema_version": 1,
        "id": REPORT_ID,
        "version": "1.0.0",
        "status": "PASS",
        "analysis_role": "REPORTING_ONLY_FROM_FROZEN_AGGREGATE_METADATA",
        "protected_row_level_content_read": False,
        "model_fit_performed": False,
        "prediction_generation_performed": False,
        "figures": 3,
        "figure_formats": ["png", "svg"],
        "source_count": len(provenance),
        "output_files_excluding_manifest": [
            {
                "path": str(path.relative_to(output_dir)),
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for path in files
        ],
    }


def generate(output_dir: Path, config_path: Path) -> dict[str, Any]:
    config = _load_yaml(config_path)
    _require(config["report"]["id"] == REPORT_ID, "Unexpected report id.")
    _require(
        config["report"]["protected_row_level_content_read"] is False, "Unsafe scope."
    )
    validated = _validate_sources(config)
    expected = config["expected_values"]
    pipeline_rows = _pipeline_rows()
    timeline_rows = _timeline_rows(validated["periods"])
    waterfall_rows = _waterfall_rows(expected)
    _require(
        int(waterfall_rows[-1]["n_after_stage"])
        == int(expected["supervised_sample_n"]),
        "Waterfall does not close.",
    )

    if output_dir.exists():
        shutil.rmtree(output_dir)
    (output_dir / "figures").mkdir(parents=True)
    (output_dir / "tables").mkdir(parents=True)

    _plot_pipeline(output_dir / "figures/01_pipeline_and_leakage_safeguards")
    _plot_timeline(timeline_rows, output_dir / "figures/02_period_timeline")
    _plot_waterfall(
        waterfall_rows, output_dir / "figures/03_sample_selection_waterfall"
    )

    _write_csv(
        output_dir / "tables/01_pipeline_stages_and_safeguards.csv", pipeline_rows
    )
    _write_csv(output_dir / "tables/02_period_timeline.csv", timeline_rows)
    _write_csv(output_dir / "tables/03_sample_selection_waterfall.csv", waterfall_rows)
    provenance = _source_provenance(config, config_path)
    _write_csv(output_dir / "tables/04_source_provenance.csv", provenance)
    (output_dir / "README.md").write_text(_readme(), encoding="utf-8")
    manifest = _manifest(output_dir, provenance)
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def verify(output_dir: Path, config_path: Path) -> dict[str, Any]:
    _require((output_dir / "manifest.json").is_file(), "Missing committed manifest.")
    committed = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(
        prefix="thesis_methodology_figures_verify_"
    ) as temporary:
        regenerated_dir = Path(temporary) / "report"
        regenerated = generate(regenerated_dir, config_path)
        committed_files = {
            item["path"]: item["sha256"]
            for item in committed["output_files_excluding_manifest"]
        }
        regenerated_files = {
            item["path"]: item["sha256"]
            for item in regenerated["output_files_excluding_manifest"]
        }
        _require(
            committed_files == regenerated_files, "Regenerated file hashes differ."
        )
        stable_keys = {
            key: committed[key]
            for key in committed
            if key != "output_files_excluding_manifest"
        }
        regenerated_stable = {
            key: regenerated[key]
            for key in regenerated
            if key != "output_files_excluding_manifest"
        }
        _require(stable_keys == regenerated_stable, "Manifest metadata differs.")
    return committed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("generate", "verify"):
        child = subparsers.add_parser(command)
        child.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
        child.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    if args.command == "generate":
        manifest = generate(args.output.resolve(), args.config.resolve())
    else:
        manifest = verify(args.output.resolve(), args.config.resolve())
    print(
        json.dumps(
            {
                "id": manifest["id"],
                "status": manifest["status"],
                "figures": manifest["figures"],
                "protected_row_level_content_read": manifest[
                    "protected_row_level_content_read"
                ],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
