"""Run repository unittest modules plus simple pytest-style test functions.

The frozen environments intentionally do not contain pytest.  Two historical
test modules use plain ``test_*`` functions; their only fixture is ``tmp_path``.
This runner preserves those tests without changing historical files or adding
packages to an environment lock.
"""

from __future__ import annotations

import importlib.util
import inspect
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import ModuleType
from typing import Callable


ROOT = Path(__file__).resolve().parents[2]


class CompatRunnerError(RuntimeError):
    """Raised when a target or function signature is outside the contract."""


def _load_module(relative: str, ordinal: int) -> ModuleType:
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT / "tests") or not path.name.startswith("test_"):
        raise CompatRunnerError(f"Refusing non-test target: {relative}")
    if not path.is_file() or path.is_symlink():
        raise CompatRunnerError(f"Missing regular test target: {relative}")
    spec = importlib.util.spec_from_file_location(f"qnn_guarded_test_{ordinal}", path)
    if spec is None or spec.loader is None:
        raise CompatRunnerError(f"Cannot load test target: {relative}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _function_case(function: Callable[..., object]) -> unittest.FunctionTestCase:
    parameters = list(inspect.signature(function).parameters.values())
    if not parameters:
        return unittest.FunctionTestCase(function, description=function.__name__)
    if len(parameters) == 1 and parameters[0].name == "tmp_path":
        def call_with_tmp_path() -> None:
            with tempfile.TemporaryDirectory(prefix="qnn-function-test-") as directory:
                function(Path(directory))

        return unittest.FunctionTestCase(
            call_with_tmp_path, description=function.__name__
        )
    raise CompatRunnerError(
        f"Unsupported test function signature: {function.__module__}.{function.__name__}"
    )


def suite_for_targets(targets: list[str]) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    for ordinal, relative in enumerate(targets):
        module = _load_module(relative, ordinal)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        functions = [
            value
            for name, value in vars(module).items()
            if name.startswith("test_") and inspect.isfunction(value)
            and value.__module__ == module.__name__
        ]
        for function in sorted(functions, key=lambda item: item.__name__):
            suite.addTest(_function_case(function))
    return suite


def main(argv: list[str] | None = None) -> int:
    if os.environ.get("QNN_TEST_ACCESS_GUARD") != "1":
        print("COMPAT_TEST_RUNNER_REFUSED: QNN_TEST_ACCESS_GUARD is not set", file=sys.stderr)
        return 2
    targets = list(sys.argv[1:] if argv is None else argv)
    if not targets:
        print("COMPAT_TEST_RUNNER_REFUSED: no exact targets", file=sys.stderr)
        return 2
    try:
        suite = suite_for_targets(targets)
    except CompatRunnerError as error:
        print(f"COMPAT_TEST_RUNNER_REFUSED: {error}", file=sys.stderr)
        return 2
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
