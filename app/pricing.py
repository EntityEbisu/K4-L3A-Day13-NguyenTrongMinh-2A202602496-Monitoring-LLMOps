from __future__ import annotations

INPUT_COST_PER_MILLION_TOKENS = 3.0
OUTPUT_COST_PER_MILLION_TOKENS = 15.0


def estimate_cost(tokens_in: int, tokens_out: int) -> dict[str, float]:
    """Giá mô phỏng theo model, tách input/output để ghi vào trace.

    Dùng chung cho ``app/agent.py`` và ``app/mock_llm.py`` để cost trong log và
    cost trong trace không lệch nhau.
    """
    input_cost = (tokens_in / 1_000_000) * INPUT_COST_PER_MILLION_TOKENS
    output_cost = (tokens_out / 1_000_000) * OUTPUT_COST_PER_MILLION_TOKENS
    return {
        "input": round(input_cost, 6),
        "output": round(output_cost, 6),
        "total": round(input_cost + output_cost, 6),
    }
