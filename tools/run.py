"""Единый драйвер целей PredictorLab (Makefile — тонкая обёртка над этим файлом).

Использование: python tools/run.py <target>
Цели: check, unit, property, integration, ml, llm, security, frontend, e2e, bench,
      lint, typecheck, format, security-scan
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def sh(cmd: list[str], cwd: Path = ROOT, timeout: int = 1800) -> int:
    print(f"$ {' '.join(cmd)}  (cwd={cwd})")
    result = subprocess.run(cmd, cwd=cwd, timeout=timeout)
    return result.returncode


def pytest_group(group: str, marker: str, extra: list[str] | None = None) -> int:
    cmd = [
        PY,
        "-m",
        "pytest",
        f"tests/{group}",
        "-q",
        "--cov=backend/app/core",
        "--cov-report=term-missing:skip-covered",
        "--cov-fail-under=0",
        "-p",
        "no:cacheprovider",
        "--no-header",
    ]
    if extra:
        cmd.extend(extra)
    return sh(cmd)


def __common() -> list[str]:
    return ["--no-header"]


def lint() -> int:
    code = sh([PY, "-m", "ruff", "check", "backend", "tests", "tools", "bench", "mcp/src", "demo-data"])
    if code == 0:
        code = sh([PY, "-m", "ruff", "format", "--check", "backend", "tests", "tools", "bench", "mcp/src", "demo-data"])
    return code


def format_code() -> int:
    sh([PY, "-m", "ruff", "check", "--fix", "backend", "tests", "tools", "bench", "mcp/src", "demo-data"])
    return sh([PY, "-m", "ruff", "format", "backend", "tests", "tools", "bench", "mcp/src", "demo-data"])


def typecheck() -> int:
    return sh([PY, "-m", "mypy", "backend/app"], timeout=900)


def _npm_cmd(args: list[str]) -> list[str]:
    npm = shutil.which("npm") or shutil.which("npm.cmd") or "npm"
    if sys.platform == "win32" and not npm.endswith(".cmd"):
        return ["cmd", "/c", npm, *args]
    return [npm, *args]


def frontend_checks() -> int:
    fe = ROOT / "frontend"
    code = sh(_npm_cmd(["run", "lint"]), cwd=fe, timeout=600)
    if code == 0:
        code = sh(_npm_cmd(["exec", "tsc", "--", "--noEmit", "-p", "tsconfig.json"]), cwd=fe, timeout=600)
    if code == 0:
        code = sh(_npm_cmd(["test"]), cwd=fe, timeout=900)
    return code


def security_scan() -> int:
    code = sh([PY, "-m", "bandit", "-q", "-r", "backend/app", "-ll", "--exclude", "backend/app/core/training/runner.py:nothing"], timeout=600)
    if code == 0:
        code = sh([PY, "-m", "pip_audit", "--skip-editable", "-l"], timeout=900)
    return code


def check() -> int:
    steps = [
        ("LINT", lint),
        ("TYPECHECK", typecheck),
        ("UNIT", lambda: pytest_group("unit", "unit")),
        ("PROPERTY", lambda: pytest_group("property", "property")),
        ("INTEGRATION", lambda: pytest_group("integration", "integration")),
        ("LLM", lambda: pytest_group("llm", "llm")),
        ("SECURITY", lambda: pytest_group("security", "security")),
        ("FRONTEND", frontend_checks),
    ]
    failed: list[str] = []
    for name, fn in steps:
        print(f"\n===== {name} =====")
        code = fn()
        if code != 0:
            failed.append(name)
            print(f"!!!!! {name} FAILED (код {code})")
            break
    if failed:
        print(f"\nmake check: FAIL ({', '.join(failed)})")
        return 1
    print("\nmake check: OK (lint, typecheck, unit, property, integration, llm, security, frontend)")
    return 0


def e2e() -> int:
    code = sh([PY, "-m", "pytest", "tests/e2e", "-m", "e2e", "-q", "-p", "no:cacheprovider", "--timeout", "2400", "--no-header"], timeout=2700)
    return code


def bench() -> int:
    return sh([PY, "-u", "bench/run.py"], timeout=3600)


def coverage_report() -> int:
    return sh(
        [
            PY,
            "-m",
            "pytest",
            "tests/unit",
            "tests/property",
            "tests/integration",
            "tests/ml",
            "tests/llm",
            "tests/security",
            "-q",
            "--cov=backend/app/core",
            "--cov-report=term-missing",
            "--cov-report=html",
            "-p",
            "no:cacheprovider",
            "--no-header",
        ],
        timeout=2700,
    )


TARGETS = {
    "check": check,
    "lint": lint,
    "format": format_code,
    "typecheck": typecheck,
    "unit": lambda: pytest_group("unit", "unit"),
    "property": lambda: pytest_group("property", "property"),
    "integration": lambda: pytest_group("integration", "integration"),
    "ml": lambda: pytest_group("ml", "ml", ["--timeout", "900"]),
    "llm": lambda: pytest_group("llm", "llm"),
    "security": lambda: pytest_group("security", "security"),
    "security-scan": security_scan,
    "frontend": frontend_checks,
    "e2e": e2e,
    "test-e2e": e2e,
    "bench": bench,
    "coverage": coverage_report,
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in TARGETS:
        print("Цели: " + ", ".join(TARGETS))
        return 2
    return TARGETS[sys.argv[1]]()


if __name__ == "__main__":
    sys.exit(main())
