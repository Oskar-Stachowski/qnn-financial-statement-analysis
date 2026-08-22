"""Reproducible environment identity and import-only smoke verification."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
from typing import Any

from src.modeling.model_execution_contract import canonical_sha256, load_contract


DISTRIBUTIONS: dict[str, dict[str, str]] = {
    "classical": {
        "numpy": "numpy",
        "scipy": "scipy",
        "pandas": "pandas",
        "scikit-learn": "scikit-learn",
        "xgboost": "xgboost",
        "shap": "shap",
        "joblib": "joblib",
        "threadpoolctl": "threadpoolctl",
    },
    "qnn_mlp": {
        "numpy": "numpy",
        "scipy": "scipy",
        "pandas": "pandas",
        "scikit-learn": "scikit-learn",
        "torch": "torch",
        "PennyLane": "PennyLane",
        "pennylane-lightning": "pennylane-lightning",
        "captum": "captum",
    },
}

IMPORTS: dict[str, tuple[str, ...]] = {
    "classical": (
        "numpy",
        "scipy",
        "pandas",
        "sklearn",
        "xgboost",
        "shap",
        "joblib",
        "threadpoolctl",
    ),
    "qnn_mlp": (
        "numpy",
        "scipy",
        "pandas",
        "sklearn",
        "torch",
        "pennylane",
        "pennylane_lightning",
        "captum",
    ),
}

LOCK_PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([^ \\\n]+)")


def canonical_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def locked_versions(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [index for index, line in enumerate(lines) if LOCK_PIN.match(line)]
    pins: dict[str, str] = {}
    for position, start in enumerate(starts):
        match = LOCK_PIN.match(lines[start])
        if match is None:  # pragma: no cover - guarded by starts
            raise ValueError("Internal lock parser inconsistency.")
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        stanza = "\n".join(lines[start:end])
        if "--hash=sha256:" not in stanza:
            raise ValueError(f"Unhashed locked requirement: {match.group(1)}")
        name = canonical_distribution_name(match.group(1))
        if name in pins:
            raise ValueError(f"Duplicate locked requirement: {name}")
        pins[name] = match.group(2)
    if not pins:
        raise ValueError(f"Lockfile has no pinned distributions: {path}")
    return pins


def installed_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for distribution in importlib.metadata.distributions():
        raw_name = distribution.metadata.get("Name")
        if not raw_name:
            continue
        name = canonical_distribution_name(str(raw_name))
        if name in versions and versions[name] != distribution.version:
            raise ValueError(f"Multiple installed versions for distribution: {name}")
        versions[name] = distribution.version
    return versions


def total_memory_bytes() -> int | None:
    if sys.platform == "darwin":
        try:
            return int(
                subprocess.check_output(
                    ["sysctl", "-n", "hw.memsize"], text=True, stderr=subprocess.DEVNULL
                ).strip()
            )
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        pages = int(os.sysconf("SC_PHYS_PAGES"))
        return page_size * pages
    except (AttributeError, OSError, ValueError):
        return None


def environment_report(
    role: str,
    *,
    smoke_imports: bool = False,
    lockfile: Path | None = None,
    contract_path: Path | None = None,
) -> dict[str, Any]:
    if role not in DISTRIBUTIONS:
        raise ValueError(f"Unknown environment role: {role}")
    contract = load_contract(contract_path) if contract_path is not None else load_contract()
    policy = contract["software_environment_identity"]
    expected = policy[f"{role}_expected"]
    expected_packages = {key: str(value) for key, value in expected["packages"].items()}
    actual_packages: dict[str, str] = {}
    missing: list[str] = []
    for contract_name, distribution in DISTRIBUTIONS[role].items():
        try:
            actual_packages[contract_name] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            missing.append(distribution)
    import_errors: dict[str, str] = {}
    if smoke_imports:
        for module in IMPORTS[role]:
            try:
                importlib.import_module(module)
            except Exception as error:  # pragma: no cover - environment-specific report
                import_errors[module] = f"{type(error).__name__}: {error}"

    lock_verification: dict[str, Any] = {
        "required": lockfile is not None,
        "status": "NOT_REQUESTED",
    }
    lock_matches = True
    if lockfile is not None:
        resolved_lock = lockfile.resolve()
        pins = locked_versions(resolved_lock)
        installed = installed_versions()
        # pip is the venv bootstrap installer and is intentionally outside both
        # experiment lockfiles. Every package importable by experiment code is
        # required to match the complete compiled lock exactly.
        compared_installed = {
            name: version for name, version in installed.items() if name != "pip"
        }
        missing_locked = sorted(set(pins) - set(compared_installed))
        unexpected_installed = sorted(set(compared_installed) - set(pins))
        version_mismatches = {
            name: {"locked": pins[name], "installed": compared_installed[name]}
            for name in sorted(set(pins) & set(compared_installed))
            if pins[name] != compared_installed[name]
        }
        lock_matches = not (
            missing_locked or unexpected_installed or version_mismatches
        )
        lock_verification = {
            "required": True,
            "status": "EXACT_MATCH" if lock_matches else "MISMATCH",
            "lockfile": str(resolved_lock),
            "lockfile_sha256": hashlib.sha256(resolved_lock.read_bytes()).hexdigest(),
            "locked_distribution_count": len(pins),
            "installed_distribution_count_excluding_pip": len(compared_installed),
            "missing_locked_distributions": missing_locked,
            "unexpected_installed_distributions": unexpected_installed,
            "version_mismatches": version_mismatches,
        }

    thread_policy = {
        key: int(value) for key, value in policy["thread_environment"].items()
    }
    environment_threads = {
        key: os.environ.get(key)
        for key in (
            "OMP_NUM_THREADS",
            "MKL_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS",
            "NUMEXPR_NUM_THREADS",
        )
    }
    thread_environment_matches = all(
        environment_threads[key] == str(thread_policy[key]) for key in environment_threads
    )
    backend: dict[str, Any] = {}
    if role == "classical" and not missing:
        try:
            from threadpoolctl import threadpool_info

            backend["threadpool_info"] = threadpool_info()
        except Exception as error:  # pragma: no cover
            backend["threadpool_error"] = type(error).__name__
    if role == "qnn_mlp" and "torch" in actual_packages:
        try:
            import torch

            torch.set_num_threads(1)
            if torch.get_num_interop_threads() != 1:
                torch.set_num_interop_threads(1)
            torch.use_deterministic_algorithms(True)
            if hasattr(torch.backends, "cudnn"):
                torch.backends.cudnn.benchmark = False
                torch.backends.cudnn.deterministic = True
            backend.update(
                {
                    "torch_num_threads": torch.get_num_threads(),
                    "torch_num_interop_threads": torch.get_num_interop_threads(),
                    "torch_deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
                    "mps_available": bool(
                        hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
                    ),
                    "cuda_available": bool(torch.cuda.is_available()),
                }
            )
        except Exception as error:  # pragma: no cover
            backend["torch_backend_error"] = type(error).__name__

    device_identity: dict[str, Any] | str
    if role == "qnn_mlp":
        device_identity = contract["qnn_executable_identity"]["device_identity"]
    else:
        device_identity = "cpu"
    runtime_identity = {
        "contract_version": str(contract["execution_contract"]["version"]),
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "package_versions": actual_packages,
        "thread_environment": environment_threads,
        "os_name": platform.system(),
        "os_release": platform.release(),
        "machine_architecture": platform.machine(),
        "device_identity": device_identity,
    }
    expected_python = str(expected["python"])
    versions_match = actual_packages == expected_packages
    ready = (
        not missing
        and not import_errors
        and platform.python_version() == expected_python
        and versions_match
        and thread_environment_matches
        and lock_matches
    )
    return {
        "schema_version": 1,
        "role": role,
        "status": "READY" if ready else "NOT_READY",
        "runtime_identity": runtime_identity,
        "software_environment_sha256": canonical_sha256(runtime_identity),
        "expected_python": expected_python,
        "expected_packages": expected_packages,
        "missing_distributions": missing,
        "import_errors": import_errors,
        "python_matches": platform.python_version() == expected_python,
        "package_versions_match": versions_match,
        "thread_environment_matches": thread_environment_matches,
        "lock_verification": lock_verification,
        "host": {
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "logical_cpu_count": os.cpu_count(),
            "ram_bytes": total_memory_bytes(),
        },
        "backend_settings": backend,
        "synthetic_only": True,
        "project_data_opened": False,
        "model_fit_performed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True, choices=tuple(DISTRIBUTIONS))
    parser.add_argument("--smoke-imports", action="store_true")
    parser.add_argument("--lockfile", type=Path)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = environment_report(
        args.role,
        smoke_imports=args.smoke_imports,
        lockfile=args.lockfile,
        contract_path=args.contract,
    )
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    raise SystemExit(0 if report["status"] == "READY" else 2)


if __name__ == "__main__":
    main()
