"""Simulator and Arena tests."""
from config import TrafficConfig
from simulation.arena import impact_vs_fixed, run_arena
from simulation.controllers import CONTROLLERS
from simulation.scenarios import SCENARIOS
from simulation.simulator import Simulator


def run(scn, ctrl, seed=1):
    cfg = TrafficConfig()
    return Simulator(SCENARIOS[scn], CONTROLLERS[ctrl](cfg), cfg, seed=seed).run()


def test_simulation_is_deterministic_for_a_seed():
    a, b = run("balanced", "GRIDLOCK-X", 5), run("balanced", "GRIDLOCK-X", 5)
    assert a.as_dict() == b.as_dict()


def test_all_controllers_run_all_scenarios():
    for scn in SCENARIOS:
        for ctrl in CONTROLLERS:
            m = run(scn, ctrl)
            assert m.arrived > 0 and m.departed <= m.arrived


def test_gridlock_wastes_far_less_green_on_blocked_exit():
    fixed, grid = run("blocked_exit", "Fixed-time"), run("blocked_exit", "GRIDLOCK-X")
    assert grid.wasted_green_blocked_s < 0.25 * fixed.wasted_green_blocked_s


def test_gridlock_gets_ambulances_through_fast():
    grid = run("ambulance", "GRIDLOCK-X")
    adaptive = run("ambulance", "Adaptive (queue-only)")
    assert grid.ambulance_delay_s < adaptive.ambulance_delay_s
    assert grid.ambulance_delay_s <= 25


def test_fairness_limits_worst_wait_when_one_road_is_quiet():
    grid = run("starvation_test", "GRIDLOCK-X")
    adaptive = run("starvation_test", "Adaptive (queue-only)")
    assert grid.max_wait_s < adaptive.max_wait_s


def test_arena_rows_and_impact():
    rows = run_arena(["rush_ns"], seeds=(1,))
    assert {r["controller"] for r in rows} == set(CONTROLLERS)
    impact = impact_vs_fixed(rows)
    grid = next(i for i in impact if i["controller"] == "GRIDLOCK-X")
    assert grid["delay_reduction_pct"] > 0 and grid["fuel_saved_l"] > 0
