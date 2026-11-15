"""Traffic scenarios for the simulator and the What-If Arena.

rates : vehicles per second arriving at each movement
events: ambulances and exit-road blockages that happen during the run
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

DEFAULT_MIX = {"two_wheeler": 0.35, "auto": 0.15, "car": 0.35, "bus": 0.06, "truck": 0.09}


def _rates(ns_s=0.10, ew_s=0.10, ns_r=0.03, ew_r=0.03) -> Dict[str, float]:
    return {"N_straight": ns_s, "S_straight": ns_s, "E_straight": ew_s, "W_straight": ew_s,
            "N_right": ns_r, "S_right": ns_r, "E_right": ew_r, "W_right": ew_r}


@dataclass
class Scenario:
    name: str
    description: str
    rates: Dict[str, float]
    duration_s: int = 600
    mix: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_MIX))
    events: List[dict] = field(default_factory=list)


SCENARIOS: Dict[str, Scenario] = {s.name: s for s in [
    Scenario("balanced", "Even traffic on all four roads.", _rates()),
    Scenario("rush_ns", "Morning rush: North-South is 2x busier than East-West.",
             _rates(ns_s=0.18, ew_s=0.07, ns_r=0.04, ew_r=0.02)),
    Scenario("starvation_test", "Heavy North-South, very light East-West: can a quiet road still get green?",
             _rates(ns_s=0.19, ew_s=0.015, ns_r=0.04, ew_r=0.006)),
    Scenario("blocked_exit", "East exit road is blocked from 40 s to 450 s (accident ahead).",
             _rates(ns_s=0.12, ew_s=0.14, ns_r=0.03, ew_r=0.03),
             events=[{"type": "exit_blockage", "exit": "E", "start": 40, "end": 450, "drain": 0.0}]),
    Scenario("ambulance", "Busy junction with three ambulances arriving at different roads.",
             _rates(ns_s=0.12, ew_s=0.12, ns_r=0.03, ew_r=0.03),
             events=[{"type": "ambulance", "t": 120, "movement": "E_straight"},
                     {"type": "ambulance", "t": 300, "movement": "S_straight"},
                     {"type": "ambulance", "t": 460, "movement": "W_right"}]),
    Scenario("mixed_india", "Bus/truck heavy mixed traffic with many two-wheelers and autos.",
             _rates(ns_s=0.12, ew_s=0.09, ns_r=0.03, ew_r=0.03),
             mix={"two_wheeler": 0.40, "auto": 0.20, "car": 0.20, "bus": 0.10, "truck": 0.10}),
]}
