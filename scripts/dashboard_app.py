from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st

from app.observability import dashboard_meta, panel_specs

st.set_page_config(page_title="Day 13 Monitoring & LLMOps", layout="wide")

meta = dashboard_meta()
specs = panel_specs()

st.title(meta["title"])
st.caption(
    f"Source: `data/logs.jsonl` — time range {meta['time_range_minutes']} phút, "
    f"tự refresh mỗi {meta['refresh_seconds']} giây. "
    "Giá trị ngưỡng lấy từ `config/dashboard.yaml` (không hard-code)."
)

columns = st.columns(2)
for position, spec in enumerate(specs):
    with columns[position % 2]:
        with st.container(border=True):
            values = spec["series"]
            if values:
                headline = values[0]
                st.metric(headline["label"], f"{headline['value']:,.4g} {spec['unit']}")
            st.markdown(f"**{spec['title']}**")
            st.dataframe(
                [
                    {"metric": item["label"], "value": item["value"], "unit": spec["unit"]}
                    for item in values
                ],
                use_container_width=True,
                hide_index=True,
            )
            operator = ">=" if spec["operator"] == "gte" else "<="
            st.caption(
                f"Threshold: {spec['aggregation']} {operator} {spec['threshold']} {spec['unit']}"
            )
            st.caption(f"Query: `{spec['query']}`")

st.caption("Mỗi panel có tên, đơn vị, time range và threshold như contract.")
