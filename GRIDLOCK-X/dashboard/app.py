"""GRIDLOCK-X Streamlit dashboard.   Run:  streamlit run dashboard/app.py

Pages: Live Simulation | Manual Decision | What-If Arena | Settings | Decision Log
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import streamlit as st

from config import TrafficConfig
from simulation.arena import impact_vs_fixed, run_arena
from simulation.controllers import CONTROLLERS
from simulation.scenarios import SCENARIOS
from simulation.simulator import Simulator
from traffic import MOVEMENT_KEYS, MovementInput, decide, movement_label

st.set_page_config(page_title="GRIDLOCK-X", page_icon="🚦", layout="wide")

if "cfg" not in st.session_state:
    st.session_state.cfg = TrafficConfig()
cfg: TrafficConfig = st.session_state.cfg

TYPES = ["car", "two_wheeler", "auto", "bus", "truck"]


# --------------------------------------------------------------------------- #
# Shared widgets
# --------------------------------------------------------------------------- #
def junction_svg(queue_pce, served, exit_occ=None):
    """Top-down junction. Green box = movements currently served."""
    def box(x, y, label, keys):
        green = any(k in served for k in keys)
        fill = "#2e9e4f" if green else "#c0392b"
        q = sum(queue_pce.get(k, 0) for k in keys)
        return (f'<rect x="{x}" y="{y}" width="120" height="54" rx="8" fill="{fill}"/>'
                f'<text x="{x + 60}" y="{y + 24}" fill="white" font-size="14" '
                f'text-anchor="middle" font-weight="bold">{label}</text>'
                f'<text x="{x + 60}" y="{y + 44}" fill="white" font-size="12" '
                f'text-anchor="middle">queue {q:.1f} car-units</text>')
    parts = [box(140, 10, "North", ["N_straight", "N_right"]),
             box(140, 236, "South", ["S_straight", "S_right"]),
             box(268, 123, "East", ["E_straight", "E_right"]),
             box(12, 123, "West", ["W_straight", "W_right"])]
    parts.append('<rect x="170" y="100" width="60" height="100" fill="#555"/>')
    parts.append('<rect x="130" y="125" width="140" height="50" fill="#555" opacity="0.6"/>')
    note = ""
    if exit_occ:
        note = "Exit roads: " + "  ".join(f"{a} {v:.0%}" for a, v in exit_occ.items())
    return (f'<svg viewBox="0 0 400 300" width="100%" style="max-width:520px">'
            f'{"".join(parts)}<text x="200" y="292" font-size="12" text-anchor="middle" '
            f'fill="gray">{note}</text></svg>')


def show_decision(d):
    c1, c2, c3 = st.columns(3)
    c1.metric("Action", d.action)
    c2.metric("Green", d.candidate or "none")
    c3.metric("Duration", f"{d.green_s} s")
    st.info(f"**Why green?** {d.reason}")
    for w in d.warnings:
        st.warning(w)
    with st.expander("Why not the others?"):
        for name, why in d.why_not.items():
            st.write(f"**{name}** - {why}")
    st.dataframe(pd.DataFrame([{
        "candidate": s.name, "eligible": s.eligible, "queue (car-units)": round(s.queue_pce, 1),
        "queue score": round(s.queue_score, 1), "wait s": round(s.wait_s),
        "wait score": round(s.wait_score, 1), "fairness bonus": round(s.fairness_bonus, 1),
        "total": round(s.total, 1), "note": s.note} for s in d.scores]),
        width="stretch", hide_index=True)
    st.dataframe(pd.DataFrame([{
        "movement": m.label, "vehicles": m.vehicles, "car-units": round(m.queue_pce, 1),
        "wait s": round(m.wait_s), "exit full": f"{m.downstream_occ:.0%}",
        "status": m.status} for m in d.movements.values()]),
        width="stretch", hide_index=True)


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
def page_live():
    st.header("Live Simulation")
    left, right = st.columns([1, 2])
    with left:
        scn = st.selectbox("Scenario", list(SCENARIOS))
        ctrl = st.selectbox("Controller", list(CONTROLLERS), index=2)
        seed = st.number_input("Seed", 1, 9999, 1)
        st.caption(SCENARIOS[scn].description)
        key = (scn, ctrl, int(seed), repr(cfg))
        if st.session_state.get("sim_key") != key or st.button("Reset"):
            st.session_state.sim = Simulator(SCENARIOS[scn], CONTROLLERS[ctrl](cfg), cfg, int(seed))
            st.session_state.sim_key = key
        sim: Simulator = st.session_state.sim
        b1, b2, b3 = st.columns(3)
        if b1.button("Next decision"):
            sim.step_decision()
        if b2.button("Run 60 s"):
            end = sim.t + 60
            while sim.t < end and not sim.finished:
                sim.step_decision()
        if b3.button("Finish"):
            sim.run()
        st.progress(min(1.0, sim.t / sim.sc.duration_s), text=f"t = {sim.t}s / {sim.sc.duration_s}s")
    with right:
        d = sim.last_decision
        served = d.served if d else []
        occ = {a: sim.exit_load[a] / cfg.exit_capacity_pce for a in sim.exit_load}
        st.markdown(junction_svg(sim.queue_pce(), served, occ), unsafe_allow_html=True)
    if sim.last_decision:
        if sim.last_decision.scores:
            show_decision(sim.last_decision)
        else:
            st.info(sim.last_decision.reason)
    m = sim.metrics()
    st.subheader("Metrics so far")
    c = st.columns(5)
    c[0].metric("Avg delay", f"{m.avg_delay_s:.1f} s")
    c[1].metric("Longest wait", f"{m.max_wait_s:.0f} s")
    c[2].metric("Vehicles through", m.departed)
    c[3].metric("Green wasted (exit full)", f"{m.wasted_green_blocked_s} s")
    c[4].metric("Ambulance delay", "-" if m.ambulance_delay_s is None else f"{m.ambulance_delay_s:.0f} s")
    st.session_state.log = sim.log


def page_manual():
    st.header("Manual Decision")
    st.caption("Edit the table, the engine decides instantly. Exit-road fullness is a percentage.")
    presets = {
        "Baseline": {},
        "Emergency demo": {"E_straight": {"car": 2, "emergency": True}, "N_straight": {"car": 30, "wait_s": 60}},
        "Blocked exit demo": {"N_straight": {"car": 40, "downstream_pct": 95}, "E_straight": {"car": 4, "wait_s": 20}},
        "Fairness demo": {"N_straight": {"car": 30, "wait_s": 20}, "E_right": {"car": 2, "wait_s": 150}},
    }
    name = st.selectbox("Preset", list(presets))
    rows = []
    for k in MOVEMENT_KEYS:
        row = {"movement": k, **{t: 0 for t in TYPES}, "wait_s": 0, "downstream_pct": 0, "emergency": False}
        if name == "Baseline":
            row["car"] = 6 if k.endswith("straight") else 2
            row["wait_s"] = 15
        row.update(presets[name].get(k, {}))
        rows.append(row)
    edited = st.data_editor(pd.DataFrame(rows), hide_index=True, width="stretch",
                            key=f"editor_{name}", disabled=["movement"])
    mode = st.radio("Mode", ["phase", "single"], horizontal=True)
    state = {}
    for _, r in edited.iterrows():
        state[r["movement"]] = MovementInput(
            counts={t: int(r[t]) for t in TYPES if int(r[t]) > 0},
            wait_s=float(r["wait_s"]), downstream_occ=min(1.0, float(r["downstream_pct"]) / 100),
            emergency=bool(r["emergency"]))
    d = decide(state, cfg, mode)
    queue = {k: m.queue_pce for k, m in d.movements.items()}
    st.markdown(junction_svg(queue, d.served), unsafe_allow_html=True)
    show_decision(d)
    with st.expander("Raw JSON (what a Python/API caller receives)"):
        st.code(d.to_json(), language="json")


def page_arena():
    st.header("What-If Arena")
    st.caption("Same traffic, same random seeds: Fixed-time vs Adaptive (queue-only) vs GRIDLOCK-X.")
    chosen = st.multiselect("Scenarios", list(SCENARIOS), default=list(SCENARIOS))
    seeds = st.slider("Runs per scenario (seeds)", 1, 5, 3)
    if st.button("Run the Arena", type="primary") and chosen:
        with st.spinner("Simulating..."):
            st.session_state.arena = run_arena(chosen, tuple(range(1, seeds + 1)), cfg)
    rows = st.session_state.get("arena")
    if not rows:
        st.info("Pick scenarios and press **Run the Arena**.")
        return
    df = pd.DataFrame(rows)
    st.subheader("Average delay per vehicle (s) - lower is better")
    st.bar_chart(df.pivot(index="scenario", columns="controller", values="avg_delay_s"))
    st.subheader("Longest single wait (s) - lower is fairer")
    st.bar_chart(df.pivot(index="scenario", columns="controller", values="max_wait_s"))
    st.subheader("Impact of GRIDLOCK-X vs Fixed-time")
    imp = pd.DataFrame([i for i in impact_vs_fixed(rows) if i["controller"] == "GRIDLOCK-X"])
    if not imp.empty:
        c = st.columns(3)
        c[0].metric("Avg delay reduction", f"{imp['delay_reduction_pct'].mean():.0f}%")
        c[1].metric("Fuel saved (est.)", f"{imp['fuel_saved_l'].sum():.1f} L")
        c[2].metric("CO2 saved (est.)", f"{imp['co2_saved_kg'].sum():.1f} kg")
        st.dataframe(imp.round(2), width="stretch", hide_index=True)
    st.subheader("Full results")
    st.dataframe(df.round(1), width="stretch", hide_index=True)
    st.caption("Fuel/CO2 are estimates from idling time (0.8 L per car-unit-hour, 2.31 kg CO2 per litre).")


def page_settings():
    st.header("Settings")
    st.caption("Change a value and every page uses it immediately. Judges can tune the engine live.")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Scoring")
        w_queue = st.slider("Queue weight", 0.0, 5.0, cfg.w_queue, 0.1)
        w_wait = st.slider("Waiting-time weight", 0.0, 3.0, cfg.w_wait, 0.1)
        fa = st.slider("Fairness starts after (s)", 10, 120, int(cfg.fairness_after_s))
        fr = st.slider("Fairness rate (points / s)", 0.0, 5.0, cfg.fairness_rate, 0.1)
        fc = st.slider("Fairness cap", 0, 150, int(cfg.fairness_cap))
        basis = st.radio("Priority basis", ["space", "people"], index=["space", "people"].index(cfg.priority_basis),
                         horizontal=True, help="'people' favours buses by passengers carried")
    with c2:
        st.subheader("Safety and timing")
        block = st.slider("Block exit road at (% full)", 50, 100, int(cfg.block_threshold * 100))
        mn = st.slider("Minimum green (s)", 5, 20, cfg.min_green_s)
        mx = st.slider("Maximum green (s)", 20, 90, cfg.max_green_s)
        em = st.slider("Emergency green (s)", 8, 40, cfg.emergency_green_s)
        mode = st.radio("Signal mode", ["phase", "single"], index=["phase", "single"].index(cfg.mode),
                        horizontal=True, help="phase = turn-aware, single = one approach at a time")
    try:
        st.session_state.cfg = cfg.with_changes(
            w_queue=w_queue, w_wait=w_wait, fairness_after_s=float(fa), fairness_rate=fr,
            fairness_cap=float(fc), priority_basis=basis, block_threshold=block / 100,
            min_green_s=mn, max_green_s=mx, emergency_green_s=em, mode=mode)
    except ValueError as err:
        st.error(f"Invalid combination: {err}")
    if st.button("Reset to defaults"):
        st.session_state.cfg = TrafficConfig()
        st.rerun()
    with st.expander("Vehicle weights (car-units of road space)"):
        st.json(cfg.pce)


def page_log():
    st.header("Decision Log")
    log = st.session_state.get("log")
    if not log:
        st.info("Run the Live Simulation first - every decision and its reason is recorded here.")
        return
    df = pd.DataFrame(log)
    st.dataframe(df, width="stretch", hide_index=True)
    st.download_button("Download CSV", df.to_csv(index=False), "gridlock_decisions.csv", "text/csv")


PAGES = {"Live Simulation": page_live, "Manual Decision": page_manual,
         "What-If Arena": page_arena, "Settings": page_settings, "Decision Log": page_log}

st.sidebar.title("🚦 GRIDLOCK-X")
st.sidebar.caption("Existing adaptive signals ask which road needs green. "
                   "GRIDLOCK-X also asks whether giving it green will actually help.")
PAGES[st.sidebar.radio("Page", list(PAGES))]()
