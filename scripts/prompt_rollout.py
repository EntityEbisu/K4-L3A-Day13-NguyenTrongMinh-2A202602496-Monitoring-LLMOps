"""Tạo prompt v1/v2 và diễn luyện đổi/rollback label `production` trên Langfuse.

Cách dùng (chạy từ thư mục gốc repo):

    python scripts/prompt_rollout.py create     # tạo v1 (baseline+production) và v2 (candidate)
    python scripts/prompt_rollout.py promote    # đưa label production sang v2
    python scripts/prompt_rollout.py rollback   # đưa label production về v1
    python scripts/prompt_rollout.py show       # in trạng thái hiện tại

Script dùng key trong ``.env`` và SDK ``langfuse.create_prompt`` / ``update_prompt``.
Không hard-code version: mọi số version in ra đều đọc từ Langfuse lúc chạy.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio
from app.prompt_management import DEFAULT_PROMPT_TEMPLATE

V1_BODY = DEFAULT_PROMPT_TEMPLATE
V2_BODY = (
    "Feature={{feature}}\n"
    "Docs={{docs}}\n"
    "Question={{message}}\n"
    "Answer in at most three short sentences. Cite the document you used."
)


def _client():
    from dotenv import load_dotenv
    from langfuse import Langfuse

    load_dotenv(REPO_ROOT / ".env")
    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        raise SystemExit(
            "Thiếu LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY trong .env; không thể tạo prompt."
        )
    return Langfuse()


def _name() -> str:
    return os.getenv("LANGFUSE_PROMPT_NAME", "day13-chat")


def _resolve_label(client, label: str):
    """Trả về version mà label đang trỏ tới (đọc trực tiếp từ Langfuse)."""
    return client.get_prompt(_name(), label=label, type="text").version


def show() -> None:
    client = _client()
    name = _name()
    meta = list(client.api.prompts.list(name=name, limit=50).data or [])
    if not meta:
        print(f"Chưa có prompt nào tên {name!r}.")
        return
    print(f"--- Prompt {name} ---")
    for entry in meta:
        print(f"  versions có sẵn: {list(entry.versions)}")
    for label in ("baseline", "candidate", "production"):
        try:
            print(f"  {label:<11} -> v{_resolve_label(client, label)}")
        except Exception as exc:
            print(f"  {label:<11} -> chưa gán ({type(exc).__name__})")


def create() -> None:
    client = _client()
    name = _name()

    v1 = client.create_prompt(
        name=name,
        prompt=V1_BODY,
        labels=["baseline", "production"],
        type="text",
        commit_message="v1: baseline prompt",
    )
    print(f"Đã tạo {name} v{v1.version} với labels baseline, production")

    v2 = client.create_prompt(
        name=name,
        prompt=V2_BODY,
        labels=["candidate"],
        type="text",
        commit_message="v2: ngan gon cau tra loi va trich dan tai lieu",
    )
    print(f"Đã tạo {name} v{v2.version} với label candidate")
    print("V1 =", repr(v1.version), "| V2 =", repr(v2.version))


def _move_production(target_version: int) -> None:
    client = _client()
    name = _name()
    client.update_prompt(name=name, version=target_version, new_labels=["production"])
    print(f"Đã gán label production cho {name} v{target_version}")
    show()


def promote() -> None:
    """Đưa production sang v2 (bản candidate)."""
    target = _resolve_label(_client(), "candidate")
    _move_production(target)


def rollback() -> None:
    """Đưa production về v1 (bản baseline) — thao tác rollback."""
    target = _resolve_label(_client(), "baseline")
    _move_production(target)


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Prompt versioning cho lab Day 13")
    parser.add_argument("action", choices=["create", "promote", "rollback", "show"])
    args = parser.parse_args()
    {"create": create, "promote": promote, "rollback": rollback, "show": show}[args.action]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
