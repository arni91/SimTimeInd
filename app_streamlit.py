# app_streamlit.py
from __future__ import annotations

import bisect
import streamlit as st
import plotly.graph_objects as go

from sim_core import (
    SimConfig, Simulator,
    BELT_SPEED_MPM, TOTE_LEN_M, BOX_MAX_M,
)

st.set_page_config(page_title="SimTimedInd — 2D Viewer", layout="wide")


def build_view_ranges(results, view: str):
    last_x = results.station_xs[-1]
    belt_end = results.belt_end_m
    if view == "tail":
        view_start = max(0.0, last_x - 18.0)
        view_end = belt_end
    else:
        view_start = 0.0
        view_end = belt_end
    return view_start, view_end


@st.cache_data(show_spinner=True)
def run_sim_cached(stations: int, duration_s: float, seed: int, start_stagger_s: float, allow_squeeze: bool):
    cfg = SimConfig(
        stations=stations,
        duration_s=duration_s,
        seed=seed,
        start_stagger_s=start_stagger_s,
        allow_squeeze=allow_squeeze,
    )
    sim = Simulator(cfg)
    return sim.run()


def render_frame(results, t: float, view: str, theme: str):
    v_mps = (BELT_SPEED_MPM / 60.0)
    view_start, view_end = build_view_ranges(results, view)

    # --- THEME / COLORS ---
    if theme == "dark":
        bg = "#0E1117"
        belt_color = "white"
        station_color = "white"
        text_color = "white"
        axis_color = "white"
    else:
        bg = "white"
        belt_color = "black"
        station_color = "black"
        text_color = "black"
        axis_color = "black"

    # items active time window
    travel_time = (results.belt_end_m + max(TOTE_LEN_M, BOX_MAX_M)) / max(1e-9, v_mps)
    t0 = max(0.0, t - travel_time - 2.0)

    ts = [ev["t"] for ev in results.events]
    i0 = bisect.bisect_left(ts, t0)
    i1 = bisect.bisect_right(ts, t)

    fig = go.Figure()
    fig.update_layout(
        height=440,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor=bg,
        plot_bgcolor=bg,
        font=dict(color=text_color),
        xaxis=dict(
            range=[view_start, view_end],
            title="x (m)",
            color=axis_color,
            showgrid=False,
            zeroline=False,
        ),
        yaxis=dict(range=[-1.2, 1.25], visible=False),
        showlegend=False,
    )

    # belt line
    fig.add_shape(
        type="line",
        x0=view_start, x1=view_end,
        y0=0.0, y1=0.0,
        line=dict(width=8, color=belt_color),
    )

    # stations (posts) + labels like Tk: 2 rows per pair + wait offset
    for idx, stn in enumerate(results.stations):
        x = stn.x
        if not (view_start <= x <= view_end):
            continue

        within_pair = idx % 2  # 0 or 1

        # blocked?
        blocked = False
        start_a = None
        for a, b in stn.blocked_intervals:
            if a <= t <= b:
                blocked = True
                start_a = a
                break

        col = "red" if blocked else station_color

        # post
        fig.add_shape(
            type="line",
            x0=x, x1=x,
            y0=-0.55, y1=0.55,
            line=dict(width=3, color=col),
        )

        # station id in 2 rows (pair)
        y_sid = 0.95 - within_pair * 0.14
        fig.add_annotation(
            x=x, y=y_sid,
            text=stn.sid,
            showarrow=False,
            font=dict(color=col, size=13),
        )

        # wait label in 2 rows + horizontal offset (avoid overlap)
        if blocked and start_a is not None:
            wait_s = t - start_a
            dx = -0.8 if within_pair == 0 else +0.8  # meters
            y_wait = -0.95 - within_pair * 0.16
            fig.add_annotation(
                x=x + dx, y=y_wait,
                text=f"wait={wait_s:.1f}s",
                showarrow=False,
                font=dict(color="red", size=12),
                bgcolor=bg,
            )

    # items (rectangles)
    for ev in results.events[i0:i1]:
        dt = t - ev["t"]
        front = ev["x"] + v_mps * dt
        rear = front - ev["length"]

        if rear > results.belt_end_m:
            continue
        if front < view_start or rear > view_end:
            continue

        fill = "dodgerblue" if ev["kind"] == "box" else "orange"
        fig.add_shape(
            type="rect",
            x0=rear, x1=front,
            y0=-0.18, y1=0.18,
            line=dict(width=0),
            fillcolor=fill,
            opacity=1.0
        )

    return fig


st.title("SimTimedInd — 2D Web Viewer 🧪📦")

with st.sidebar:
    st.subheader("Simulation inputs")
    stations = st.number_input("Stations", min_value=2, max_value=40, value=22, step=1)
    duration_s = st.number_input("Duration (s)", min_value=60, max_value=7200, value=3600, step=60)
    start_stagger_s = st.number_input("Start stagger window (s)", min_value=0, max_value=120, value=20, step=5)
    seed = st.number_input("Seed", min_value=0, max_value=10_000, value=42, step=1)
    allow_squeeze = st.checkbox("Allow squeeze (gap -> 0mm)", value=True)
    view = st.selectbox("View", ["full", "tail"], index=1)
    theme = st.selectbox("Theme", ["light", "dark"], index=0)

    run_btn = st.button("Run / Recompute", type="primary")

if "results" not in st.session_state:
    st.session_state.results = None

if run_btn or st.session_state.results is None:
    st.session_state.results = run_sim_cached(
        int(stations),
        float(duration_s),
        int(seed),
        float(start_stagger_s),
        bool(allow_squeeze),
    )

results = st.session_state.results

# summary
colA, colB, colC, colD = st.columns(4)
thr_h = (results.inserted_total / results.cfg.duration_s) * 3600.0
squeeze_rate = (results.squeeze_used / results.inserted_total) if results.inserted_total else 0.0

colA.metric("Stations", f"{results.cfg.stations}")
colB.metric("Inserted total", f"{results.inserted_total}")
colC.metric("Throughput", f"{thr_h:.0f} items/h")
colD.metric("Squeeze rate", f"{squeeze_rate*100:.1f}%")

# time scrubber
t = st.slider("Time (s)", min_value=0.0, max_value=float(results.cfg.duration_s), value=0.0, step=0.5)
fig = render_frame(results, float(t), view=view, theme=theme)
st.plotly_chart(fig, width="stretch")

with st.expander("Per-station quick stats"):
    rows = []
    for stn in results.stations:
        blocked_time = sum((b - a) for a, b in stn.blocked_intervals)
        rows.append({
            "sid": stn.sid,
            "x_m": round(stn.x, 3),
            "ins_total": stn.inserted_boxes + stn.inserted_totes,
            "boxes": stn.inserted_boxes,
            "totes": stn.inserted_totes,
            "squeeze": stn.squeeze_used,
            "blocked_time_s": round(blocked_time, 1),
            "blocked_events": len(stn.blocked_intervals),
        })
    st.dataframe(rows, width="stretch")