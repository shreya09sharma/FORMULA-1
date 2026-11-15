"""GRIDLOCK-X configuration.

Every tunable number lives in ONE place: the TrafficConfig dataclass.
The What-If Arena, the Settings page and the tests all create their own
TrafficConfig objects, so the same engine can run with different settings.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field, asdict

VEHICLE_TYPES = ("two_wheeler", "auto", "car", "bus", "truck", "ambulance")

# PCE = passenger-car equivalent = how much ROAD SPACE a vehicle uses.
DEFAULT_PCE = {
    "two_wheeler": 0.5,
    "auto": 0.8,
    "car": 1.0,
    "bus": 3.0,
    "truck": 3.0,
    "ambulance": 1.0,
}

# Rough number of PEOPLE carried (used only when priority_basis == "people").
DEFAULT_PEOPLE = {
    "two_wheeler": 1.3,
    "auto": 2.5,
    "car": 1.8,
    "bus": 35.0,
    "truck": 1.5,
    "ambulance": 2.0,
}


@dataclass
class TrafficConfig:
    # ---- vehicle-type weighting -------------------------------------------
    pce: dict = field(default_factory=lambda: dict(DEFAULT_PCE))
    people: dict = field(default_factory=lambda: dict(DEFAULT_PEOPLE))
    priority_basis: str = "space"      # "space" (PCE) or "people"
    people_per_pce: float = 1.8        # converts people -> car-units for scoring

    # ---- scoring ------------------------------------------------------------
    w_queue: float = 2.0               # points per car-unit waiting
    queue_cap: float = 60.0            # car-units counted at most
    w_wait: float = 0.5                # points per second of waiting
    wait_cap: float = 120.0            # seconds counted at most
    fairness_after_s: float = 45.0     # fairness bonus starts after this wait
    fairness_rate: float = 1.5         # bonus points per extra second
    fairness_cap: float = 60.0         # bonus never exceeds this

    # ---- downstream (spillback) protection ---------------------------------
    block_threshold: float = 0.85      # exit road this full -> movement is gated
    full_threshold: float = 0.99       # exit road this full -> nothing can leave
    exit_capacity_pce: float = 40.0    # car-units an exit road can hold

    # ---- green timing --------------------------------------------------------
    min_green_s: int = 8
    max_green_s: int = 50
    startup_s: float = 4.0
    headway_s_per_pce: float = 2.0     # seconds to discharge one car-unit
    amber_s: int = 3
    all_red_s: int = 1
    emergency_green_s: int = 15

    # ---- structure -------------------------------------------------------------
    mode: str = "phase"                # "phase" (turn-aware) or "single" (one approach)

    def validate(self) -> None:
        if self.priority_basis not in ("space", "people"):
            raise ValueError("priority_basis must be 'space' or 'people'")
        if self.mode not in ("phase", "single"):
            raise ValueError("mode must be 'phase' or 'single'")
        if not 0 < self.block_threshold <= self.full_threshold <= 1.0:
            raise ValueError("need 0 < block_threshold <= full_threshold <= 1")
        if not 0 < self.min_green_s <= self.max_green_s:
            raise ValueError("need 0 < min_green_s <= max_green_s")
        if self.exit_capacity_pce <= 0 or self.people_per_pce <= 0:
            raise ValueError("capacities must be positive")

    def with_changes(self, **changes) -> "TrafficConfig":
        """Return a modified COPY (the original is never changed)."""
        new = copy.deepcopy(self)
        for key, value in changes.items():
            if not hasattr(new, key):
                raise AttributeError(f"unknown config field: {key}")
            setattr(new, key, value)
        new.validate()
        return new

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_CONFIG = TrafficConfig()
