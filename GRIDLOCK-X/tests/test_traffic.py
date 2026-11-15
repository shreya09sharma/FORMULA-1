"""Engine tests: emergency, blockage, fairness, weighting, phases, edge cases."""
import json

import pytest

from config import TrafficConfig
from traffic import MovementInput as M, decide, state_from_approach_counts


def cars(n):
    return {"car": n}


# ---- vehicle-type weighting --------------------------------------------------
def test_bus_counts_more_road_space_than_scooters():
    d = decide({"N_straight": M(cars(0) | {"bus": 5}), "E_straight": M({"two_wheeler": 10})},
               mode="single")
    assert d.movements["N_straight"].queue_pce == 15.0
    assert d.movements["E_straight"].queue_pce == 5.0
    assert d.candidate == "North"


def test_people_basis_changes_priority():
    state = {"N_straight": M({"bus": 4}), "E_straight": M({"car": 12})}
    space = decide(state, TrafficConfig(priority_basis="space"), "single")
    people = decide(state, TrafficConfig(priority_basis="people"), "single")
    assert space.candidate == "North" or space.candidate == "East"
    # 4 buses carry ~140 people, 12 cars ~22: people basis must favour the buses
    assert people.candidate == "North"
    assert people.scores[0].queue_score > people.scores[2].queue_score


# ---- emergency -----------------------------------------------------------------
def test_emergency_beats_bigger_queue_and_holds_others():
    state = {"N_straight": M(cars(30), wait_s=60),
             "E_straight": M(cars(1), emergency=True)}
    d = decide(state)
    assert d.action == "EMERGENCY"
    assert d.candidate == "EW_straight"
    assert d.movements["N_straight"].status == "HELD_FOR_EMERGENCY"
    assert d.green_s == TrafficConfig().emergency_green_s


def test_emergency_in_right_turn_picks_right_phase():
    d = decide({"S_right": M(cars(1), emergency=True), "N_straight": M(cars(20))})
    assert d.candidate == "NS_right"
    assert "S_right" in d.served
    assert "N_straight" not in d.served


def test_emergency_ignores_blocked_exit_but_warns():
    d = decide({"W_straight": M(cars(2), downstream_occ=0.97, emergency=True)})
    assert d.action == "EMERGENCY" and "W_straight" in d.served
    assert any("exit road" in w for w in d.warnings)


def test_two_emergencies_longest_waiting_first():
    d = decide({"N_straight": M(cars(1), emergency=True, emergency_wait_s=5),
                "E_straight": M(cars(1), emergency=True, emergency_wait_s=40)})
    assert d.candidate == "EW_straight"
    assert any("queued next" in w for w in d.warnings)


# ---- downstream blockage -------------------------------------------------------------
def test_blocked_exit_is_skipped_even_with_huge_queue():
    d = decide({"N_straight": M(cars(40), downstream_occ=0.95),
                "E_straight": M(cars(4))})
    assert d.candidate == "EW_straight"
    assert "blocked" in d.why_not["NS_straight"] or "skipped" in d.why_not["NS_straight"]


def test_blocked_movement_leaves_phase_but_phase_still_runs():
    d = decide({"N_straight": M(cars(20), downstream_occ=0.9),
                "S_straight": M(cars(10), downstream_occ=0.1)})
    assert d.candidate == "NS_straight"
    assert d.served == ["S_straight"]
    assert d.movements["N_straight"].status == "BLOCKED_DOWNSTREAM"


def test_all_blocked_serves_least_blocked_briefly():
    d = decide({"N_straight": M(cars(10), downstream_occ=0.95),
                "E_straight": M(cars(10), downstream_occ=0.90)})
    assert d.action == "FALLBACK_LEAST_BLOCKED"
    assert d.served == ["E_straight"]
    assert d.green_s == TrafficConfig().min_green_s


def test_all_exits_completely_full_holds_red():
    d = decide({"N_straight": M(cars(10), downstream_occ=1.0),
                "E_straight": M(cars(10), downstream_occ=1.0)})
    assert d.action == "ALL_BLOCKED_HOLD"
    assert d.served == [] and d.candidate is None and d.green_s == 0


# ---- fairness --------------------------------------------------------------------------
def test_starved_lane_eventually_beats_busy_lane():
    busy = {"N_straight": M(cars(30), wait_s=20), "E_right": M(cars(2), wait_s=5)}
    assert decide(busy).candidate == "NS_straight"
    starved = {"N_straight": M(cars(30), wait_s=20), "E_right": M(cars(2), wait_s=150)}
    d = decide(starved)
    assert d.candidate == "EW_right"
    assert d.scores[3].fairness_bonus > 0
    assert "Fairness bonus changed the decision" in d.reason


def test_fairness_bonus_is_capped():
    cfg = TrafficConfig()
    d = decide({"E_right": M(cars(1), wait_s=10_000)}, cfg)
    assert d.scores[3].fairness_bonus == cfg.fairness_cap
    assert d.scores[3].wait_score == cfg.w_wait * cfg.wait_cap


# ---- phases / modes --------------------------------------------------------------------------
def test_phase_mode_serves_two_opposing_movements_together():
    d = decide({"N_straight": M(cars(10)), "S_straight": M(cars(12))})
    assert d.candidate == "NS_straight"
    assert set(d.served) == {"N_straight", "S_straight"}


def test_single_mode_serves_one_approach():
    d = decide({"N_straight": M(cars(10)), "S_straight": M(cars(12))}, mode="single")
    assert d.candidate == "South"
    assert d.served == ["S_straight"]


# ---- timing, edge cases, interface -----------------------------------------------------------
def test_green_time_is_clamped():
    cfg = TrafficConfig()
    small = decide({"N_straight": M(cars(1))}, cfg)
    huge = decide({"N_straight": M(cars(500))}, cfg)
    assert small.green_s == cfg.min_green_s
    assert huge.green_s == cfg.max_green_s


def test_green_limited_by_space_in_exit_road():
    free = decide({"N_straight": M(cars(30), downstream_occ=0.0)})
    tight = decide({"N_straight": M(cars(30), downstream_occ=0.80)})
    assert tight.green_s < free.green_s


def test_no_traffic_is_idle():
    d = decide({})
    assert d.action == "IDLE" and d.candidate is None


def test_bad_input_is_rejected_or_clamped():
    with pytest.raises(ValueError):
        decide({"N_straight": M({"car": -1})})
    with pytest.raises(ValueError):
        decide({"UP_straight": M(cars(1))})
    with pytest.raises(ValueError):
        decide({"N_straight": M(cars(1), wait_s=-5)})
    d = decide({"N_straight": M(cars(3), downstream_occ=1.7)})
    assert any("clamped" in w for w in d.warnings)


def test_unknown_vehicle_type_warns_not_crashes():
    d = decide({"N_straight": M({"tractor": 2})})
    assert d.candidate == "NS_straight" and any("tractor" in w for w in d.warnings)


def test_config_validation_and_copy():
    cfg = TrafficConfig()
    cfg2 = cfg.with_changes(min_green_s=12)
    assert cfg.min_green_s == 8 and cfg2.min_green_s == 12
    with pytest.raises(ValueError):
        cfg.with_changes(min_green_s=60, max_green_s=30)


def test_decision_serialises_to_json_for_dashboard_or_api():
    d = decide({"N_straight": M(cars(5))})
    data = json.loads(d.to_json())
    assert data["candidate"] == "NS_straight" and "scores" in data and "reason" in data


def test_perception_adapter_builds_straight_movements():
    state = state_from_approach_counts({"N": {"car": 5}, "E": {"bus": 1}}, emergency={"E": True})
    d = decide(state)
    assert d.action == "EMERGENCY" and d.candidate == "EW_straight"
