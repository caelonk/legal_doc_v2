"""Run every test module and report a single pass/fail.

Run: python backend/tests/run_all.py

Each module is executed in its own subprocess so an import-time failure in one
cannot take the whole suite down silently.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULES = ["test_schemas.py", "test_parser.py", "test_chunker.py", "test_pipeline.py"]


def main() -> int:
    failed: list[str] = []
    total_checks = 0

    for name in MODULES:
        path = HERE / name
        if not path.exists():
            print(f"{name:22s} SKIP (not found)")
            continue
        proc = subprocess.run(
            [sys.executable, str(path)], capture_output=True, text=True, cwd=str(HERE)
        )
        output = proc.stdout + proc.stderr
        passed = output.count("[PASS]")
        total_checks += passed
        if proc.returncode == 0:
            print(f"{name:22s} PASS  ({passed} checks)")
        else:
            failed.append(name)
            print(f"{name:22s} FAIL  (exit {proc.returncode})")
            for line in output.splitlines():
                if "[FAIL]" in line or "Traceback" in line or line.startswith("   - "):
                    print(f"      {line.strip()}")

    print()
    if failed:
        print(f"SUITE FAILED: {', '.join(failed)}")
        return 1
    print(f"SUITE PASSED: {total_checks} checks across {len(MODULES)} modules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
