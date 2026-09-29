from __future__ import annotations

from app import mock_llm, mock_rag
from app.tracing import observe


class RecordingClient:
    """Client giả ghi lại span/generation được cập nhật."""

    def __init__(self) -> None:
        self.span_updates: list[dict] = []
        self.generation_updates: list[dict] = []

    def update_current_span(self, **kwargs) -> None:
        self.span_updates.append(kwargs)

    def update_current_generation(self, **kwargs) -> None:
        self.generation_updates.append(kwargs)


def test_observe_decorator_is_the_langfuse_v4_one():
    assert observe.__module__.startswith("langfuse")


def test_retrieve_is_wrapped_by_observe():
    """@observe giữ __wrapped__ trỏ về hàm gốc."""
    assert hasattr(mock_rag.retrieve, "__wrapped__"), "retrieve() chưa được @observe"


def test_generate_is_wrapped_by_observe():
    assert hasattr(mock_llm.FakeLLM.generate, "__wrapped__"), (
        "FakeLLM.generate() chưa được @observe"
    )


def test_retrieve_records_a_span_with_doc_count(monkeypatch):
    client = RecordingClient()
    monkeypatch.setattr(mock_rag, "get_langfuse_client", lambda: client)

    docs = mock_rag.retrieve("How does monitoring work?")

    assert docs, "retrieve phải trả về tài liệu"
    assert client.span_updates, "retrieval phải cập nhật span"
    metadata = client.span_updates[-1].get("metadata", {})
    assert metadata["doc_count"] == len(docs)
    assert "retrieval_ms" in metadata


def test_retrieve_marks_span_level_error_when_tool_fails(monkeypatch):
    from app import incidents

    client = RecordingClient()
    monkeypatch.setattr(mock_rag, "get_langfuse_client", lambda: client)
    monkeypatch.setitem(incidents.STATE, "tool_fail", True)
    try:
        try:
            mock_rag.retrieve("monitoring")
        except RuntimeError:
            pass
        else:
            raise AssertionError("retrieve phải ném RuntimeError khi tool_fail")
    finally:
        incidents.STATE["tool_fail"] = False

    assert client.span_updates, "lỗi retrieval vẫn phải ghi span"
    assert client.span_updates[-1].get("level") == "ERROR"


def test_generate_records_usage_and_cost_on_a_generation(monkeypatch):
    client = RecordingClient()
    monkeypatch.setattr(mock_llm, "get_langfuse_client", lambda: client)

    response = mock_llm.FakeLLM().generate("Feature=qa\nDocs=refund\nQuestion=policy?")

    assert client.generation_updates, "LLM call phải cập nhật generation"
    update = client.generation_updates[-1]
    assert update["model"] == response.model
    assert update["usage_details"] == {
        "input": response.usage.input_tokens,
        "output": response.usage.output_tokens,
    }
    assert set(update["cost_details"]) == {"input", "output"}


def test_generation_trace_payload_is_scrubbed(monkeypatch):
    client = RecordingClient()
    monkeypatch.setattr(mock_llm, "get_langfuse_client", lambda: client)
    pii_prompt = "Question: email a@vinuni.edu.vn, phone 0901234567"

    mock_llm.FakeLLM().generate(pii_prompt)

    update = client.generation_updates[-1]
    blob = str(update["input"]) + str(update["output"])
    assert "a@vinuni.edu.vn" not in blob
    assert "0901234567" not in blob
    assert "[REDACTED_" in blob
