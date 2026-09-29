from __future__ import annotations

import time

from .incidents import STATE
from .pii import summarize_text
from .tracing import get_langfuse_client, observe

CORPUS = {
    "refund": ["Refunds are available within 7 days with proof of purchase."],
    "monitoring": ["Metrics detect incidents, logs identify affected requests, traces localize the root cause."],
    "policy": ["Do not expose PII in logs. Use sanitized summaries only."],
}

FALLBACK_DOCS = ["No domain document matched. Use general fallback answer."]


@observe(name="retrieval", as_type="retriever", capture_input=False, capture_output=False)
def retrieve(message: str) -> list[str]:
    """Truy xuất tài liệu giả lập; tạo child observation loại ``retriever``.

    Không gọi dịch vụ thật: corpus là dict tĩnh và độ trễ chỉ do ``time.sleep``.
    """
    client = get_langfuse_client()
    started = time.perf_counter()

    if STATE["tool_fail"]:
        client.update_current_span(
            level="ERROR",
            status_message="retrieval failed",
            metadata={"error_type": "RuntimeError"},
        )
        raise RuntimeError("Vector store timeout")

    if STATE["rag_slow"]:
        time.sleep(2.5)

    lowered = message.lower()
    docs = FALLBACK_DOCS
    for key, corpus_docs in CORPUS.items():
        if key in lowered:
            docs = corpus_docs
            break

    client.update_current_span(
        metadata={
            "doc_count": len(docs),
            "retrieval_ms": round((time.perf_counter() - started) * 1000),
            "query_preview": summarize_text(message),
        }
    )
    return docs
