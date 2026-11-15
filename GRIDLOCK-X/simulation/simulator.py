"""A small second-by-second intersection simulator (pure Python, no SUMO needed).

Model:
  * vehicles arrive randomly (Poisson) at each movement and wait in a queue
  * during green, a movement discharges at its saturation flow (car-units / s)
  * a vehicle can only leave if its EXIT road has space; exit roads drain slowly
  * events: ambulances (jump to the front of a queue) and exit-road blockages
The simulator does not know which controller is driving, so the comparison is fair.
"""
from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

from config import TrafficConfig
from traffic import APPROACHES, MOVEMENT_KEYS, MovementInput
from simulation.scenarios import Scenario

EXIT_OF = {"N_straight": "S", "S_straight": "N", "E_straight": "W", "W_straight": "E",
           "N_right": "W", "S_right": "E", "E_right": "N", "W_right": "S"}
SAT_FLOW = {"straight": 0.5, "right": 0.35}      # car-units per second of green
EXIT_DRAIN = 0.6                                  # car-units per second leaving an exit
MAX_CREDIT = 3.0
IDLE_FUEL_L_PER_PCE_HOUR = 0.8                    # estimate: fuel burned while idling
CO2_KG_PER_LITRE = 2.31


@dataclass
class Vehicle:
    vtype: str
    arrived: int
    pce: float


@dataclass
class RunMetrics:
    controller: str
    scenario: str
    seed: int
    arrived: int
    departed: int
    avg_delay_s: float
    max_wait_s: float
    ambulance_delay_s: Optional[float]
    wasted_green_blocked_s: int      # green seconds where the exit road was full
    wasted_green_empty_s: int        # green seconds with nobody to serve
    fuel_l: float
    co2_kg: float
    decisions: int

    def as_dict(self) -> dict:
        return asdict(self)


def _poisson(rng: random.Random, lam: float) -> int:
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


class Simulator:
    def __init__(self, scenario: Scenario, controller, cfg: Optional[TrafficConfig] = None,
                 seed: int = 1):
        self.sc, self.ctrl = scenario, controller
        self.cfg = cfg or TrafficConfig()
        self.seed = seed
        self.rng = random.Random(seed)
        self.t = 0
        self.queues: Dict[str, deque] = {k: deque() for k in MOVEMENT_KEYS}
        self.exit_load = {a: 0.0 for a in APPROACHES}
        self.credit = {k: 0.0 for k in MOVEMENT_KEYS}
        self.types = list(scenario.mix)
        self.weights = [scenario.mix[t] for t in self.types]
        self.arrived = self.departed = 0
        self.delay_sum = 0.0
        self.max_wait = 0.0
        self.amb_delays: List[float] = []
        self.wasted_blocked = self.wasted_empty = 0
        self.pce_delay_s = 0.0
        self.log: List[dict] = []
        self.last_decision = None
        if hasattr(controller, "reset"):
            controller.reset()

    # ---- observations ------------------------------------------------------
    @property
    def finished(self) -> bool:
        return self.t >= self.sc.duration_s

    def snapshot(self) -> Dict[str, MovementInput]:
        state = {}
        for k, q in self.queues.items():
            counts: Dict[str, int] = {}
            amb_wait = None
            for v in q:
                counts[v.vtype] = counts.get(v.vtype, 0) + 1
                if v.vtype == "ambulance":
                    amb_wait = max(amb_wait or 0, self.t - v.arrived)
            state[k] = MovementInput(
                counts=counts,
                wait_s=float(self.t - q[0].arrived) if q else 0.0,
                downstream_occ=min(1.0, self.exit_load[EXIT_OF[k]] / self.cfg.exit_capacity_pce),
                emergency=amb_wait is not None,
                emergency_wait_s=float(amb_wait or 0))
        return state

    def queue_pce(self) -> Dict[str, float]:
        return {k: sum(v.pce for v in q) for k, q in self.queues.items()}

    # ---- one second -------------------------------------------------------
    def _drain_rate(self, exit_name: str) -> float:
        for ev in self.sc.events:
            if (ev["type"] == "exit_blockage" and ev["exit"] == exit_name
                    and ev["start"] <= self.t < ev["end"]):
                return ev.get("drain", 0.0)
        return EXIT_DRAIN

    def _arrivals(self):
        for k, rate in self.sc.rates.items():
            for _ in range(_poisson(self.rng, rate)):
                vtype = self.rng.choices(self.types, self.weights)[0]
                self.queues[k].append(Vehicle(vtype, self.t, self.cfg.pce.get(vtype, 1.0)))
                self.arrived += 1
        for ev in self.sc.events:
            if ev["type"] == "ambulance" and ev["t"] == self.t:
                self.queues[ev["movement"]].appendleft(Vehicle("ambulance", self.t, 1.0))
                self.arrived += 1

    def _discharge(self, served):
        if served and all(not self.queues[k] for k in served):
            self.wasted_empty += 1
        for k in served:
            q = self.queues[k]
            self.credit[k] = min(self.credit[k] + SAT_FLOW[k.split("_")[1]], MAX_CREDIT)
            ex = EXIT_OF[k]
            while q:
                v = q[0]
                if v.vtype != "ambulance" and self.exit_load[ex] + v.pce > self.cfg.exit_capacity_pce:
                    self.wasted_blocked += 1          # green, but the exit road is full
                    break
                if self.credit[k] < v.pce:
                    break
                q.popleft()
                self.credit[k] -= v.pce
                self.exit_load[ex] += v.pce
                self.departed += 1
                wait = self.t - v.arrived
                self.delay_sum += wait
                self.max_wait = max(self.max_wait, wait)
                if v.vtype == "ambulance":
                    self.amb_delays.append(wait)

    def _tick(self, served):
        self._arrivals()
        self._discharge(served)
        for ex in self.exit_load:
            self.exit_load[ex] = max(0.0, self.exit_load[ex] - self._drain_rate(ex))
        for q in self.queues.values():
            if q:
                self.pce_delay_s += sum(v.pce for v in q)
                self.max_wait = max(self.max_wait, self.t - q[0].arrived)
        self.t += 1

    def _run_seconds(self, n: int, served):
        for _ in range(int(n)):
            if self.finished:
                return
            self._tick(served)

    # ---- one controller decision -------------------------------------------
    def step_decision(self):
        """Ask the controller what to do, then run its green + clearance."""
        decision = self.ctrl.decide(self.snapshot())
        self.last_decision = decision
        self.log.append({"t": self.t, "action": decision.action,
                         "candidate": decision.candidate, "green_s": decision.green_s,
                         "served": ", ".join(decision.served), "reason": decision.reason})
        if decision.candidate is None or decision.green_s <= 0:
            self._run_seconds(2, [])                   # everything red, look again soon
        else:
            self.credit = {k: 0.0 for k in MOVEMENT_KEYS}
            self._run_seconds(decision.green_s, decision.served)
            self._run_seconds(decision.amber_s + decision.all_red_s, [])
        return decision

    def run(self) -> RunMetrics:
        while not self.finished:
            self.step_decision()
        return self.metrics()

    def metrics(self) -> RunMetrics:
        remaining_wait, amb = 0.0, list(self.amb_delays)
        for q in self.queues.values():
            for v in q:
                w = self.t - v.arrived
                remaining_wait += w
                if v.vtype == "ambulance":
                    amb.append(w)
        total = max(1, self.arrived)
        fuel = self.pce_delay_s / 3600.0 * IDLE_FUEL_L_PER_PCE_HOUR
        return RunMetrics(
            controller=self.ctrl.name, scenario=self.sc.name, seed=self.seed,
            arrived=self.arrived, departed=self.departed,
            avg_delay_s=(self.delay_sum + remaining_wait) / total,
            max_wait_s=self.max_wait,
            ambulance_delay_s=(sum(amb) / len(amb)) if amb else None,
            wasted_green_blocked_s=self.wasted_blocked,
            wasted_green_empty_s=self.wasted_empty,
            fuel_l=fuel, co2_kg=fuel * CO2_KG_PER_LITRE, decisions=len(self.log))
