"""Chạy cùng một input với label prompt chỉ định và ghi lại correlation_id.

Cách dùng:

    LANGFUSE_PROMPT_LABEL=baseline  python -m uvicorn app.main:app --env-file .env &
    python scripts/prompt_ab_run.py baseline

    LANGFUSE_PROMPT_LABEL=candidate python -m uvicorn app.main:app --env-file .env &
    python scripts/prompt_ab_run.py candidate

Lưu ý quan trọng: app đọc ``LANGFUSE_PROMPT_LABEL`` từ biến môi trường của
tiến trình **server** lúc khởi động, không đọc lúc request. Vì vậy tham số dòng
lệnh của script chỉ dùng để tra version và in bằng chứng; nó KHÔNG đổi được
label mà server đang dùng. Hai giá trị phải khớp.

Đã kiểm chứng: uvicorn KHÔNG ghi đè biến môi trường đã có bằng ``--env-file``,
nên đặt biến shell trước khi khởi động server là cách đúng.

Script tra version thật của label trên Langfuse lúc chạy, nên bằng chứng không
phải tin vào tên script. Correlation ID in ra là của chính request đó, dùng để
mở trace tương ứng trên Langfuse.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import httpx
from dotenv import load_dotenv

MESSAGE = "What is your refund policy?"


def main() -> int:
    if len(sys.argv) < 2:
        print("Thiếu label. Dùng: python scripts/prompt_ab_run.py <label>")
        print("Label phải khớp LANGFUSE_PROMPT_LABEL của tiến trình server.")
        return 2
    label = sys.argv[1]

    load_dotenv(REPO_ROOT / ".env")
    name = os.getenv("LANGFUSE_PROMPT_NAME", "day13-chat")

    from langfuse import Langfuse

    managed = Langfuse().get_prompt(name, label=label, type="text")
    version = managed.version

    response = httpx.post(
        "http://127.0.0.1:8000/chat",
        json={
            "user_id": "ab-user",
            "session_id": "ab-session",
            "feature": "refund",
            "message": MESSAGE,
        },
        timeout=60.0,
    )
    body = response.json()
    print(f"label          : {label}")
    print(f"prompt name    : {name}")
    print(f"version        : v{version}   (đọc từ Langfuse lúc chạy)")
    print(f"correlation_id : {body.get('correlation_id')}")
    print(f"latency_ms     : {body.get('latency_ms')}")
    print(f"tokens         : in={body.get('tokens_in')} out={body.get('tokens_out')}")
    return 0 if response.status_code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
