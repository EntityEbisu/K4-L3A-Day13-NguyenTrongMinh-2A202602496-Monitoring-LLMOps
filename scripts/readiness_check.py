"""Kiểm tra mức độ sẵn sàng cho CP2 và CP3 bằng output thật, không hard-code.

Cách dùng:

    python scripts/readiness_check.py

Chạy tất cả validator và báo cáo trạng thái từng hạng mục. CP3 phụ thuộc
``config/challenge.json`` do Lab Coach phát, nên mục đó báo CHỜ thay vì PASS
khi file chưa tồn tại — đây là trạng thái đúng, không phải lỗi.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(args: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        [PY, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    return result.returncode, result.stdout


def main() -> int:
    print("=" * 66)
    print("KIỂM TRA SẴN SÀNG CP2 / CP3")
    print("=" * 66)

    checks: list[tuple[str, bool, str]] = []

    rc, out = run(["-m", "pytest", "-q"])
    summary = [line for line in out.splitlines() if "passed" in line or "failed" in line]
    checks.append(("pytest", rc == 0, summary[-1].strip() if summary else "no summary"))

    _, out = run(["scripts/validate_logs.py"])
    score = [line for line in out.splitlines() if "Estimated Score" in line]
    checks.append(
        (
            "validate_logs",
            "100/100" in (score[0] if score else ""),
            score[0].strip() if score else "no score",
        )
    )

    _, out = run(["scripts/validate_dashboard.py"])
    checks.append(
        (
            "validate_dashboard",
            "6/6" in out,
            next((line.strip() for line in out.splitlines() if "HỢP LỆ" in line), "no output"),
        )
    )

    rc, out = run(["scripts/verify_trace_join.py"])
    checks.append(
        (
            "verify_trace_join",
            rc == 0,
            next((line.strip() for line in out.splitlines() if "Khớp" in line), "no match line"),
        )
    )

    _, out = run(["scripts/prompt_rollout.py", "show"])
    checks.append(
        (
            "prompt v1+v2",
            "v1" in out and "v2" in out,
            " | ".join(line.strip() for line in out.splitlines() if "->" in line),
        )
    )

    challenge = REPO_ROOT / "config" / "challenge.json"
    checks.append(
        (
            "config/challenge.json",
            challenge.exists(),
            "present" if challenge.exists() else "CHƯA CÓ — chờ Lab Coach release",
        )
    )

    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60
    ).stdout.split()
    leaked = [f for f in tracked if f in (".env", "config/challenge.json")]
    checks.append(
        ("no secret tracked", not leaked, "clean" if not leaked else f"TRACKED: {leaked}")
    )

    print()
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else '----'}] {name:24s} {detail}")

    not_yet = {"config/challenge.json"}
    cp2_ok = all(ok for name, ok, _ in checks if name not in not_yet)
    print()
    print("=" * 66)
    print(f"CP2 (tracing/prompt/dashboard/SLO/alert): {'HOÀN TẤT' if cp2_ok else 'CÒN THIẾU'}")
    print(
        "CP3 (challenge chính thức): "
        + ("SẴN SÀNG" if challenge.exists() else "CHỜ config/challenge.json từ Lab Coach")
    )
    print("=" * 66)
    return 0 if cp2_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
