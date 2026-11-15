"""Three controllers with the same interface, so the Arena compares them fairly.

  FixedController     - cycles through the phases on a timer (no sensing)
  AdaptiveController  - picks the biggest queue (no fairness / emergency / spillback)
  GridlockController  - the full GRIDLOCK-X engine
"""
from __future__ import annotations

from typing import Dict, Optional

from config import TrafficConfig
from traffic import (CANDIDATE_SETS, Decision, MovementInput, analyse_state,
                     compute_green, decide)


class GridlockController:
    name = "GRIDLOCK-X"

    def __init__(self, cfg: Optional[TrafficConfig] = None, mode: Optional[str] = None):
        self.cfg = cfg or TrafficConfig()
        self.mode = mode or self.cfg.mode

    def reset(self):
        pass

    def decide(self, state: Dict[str, MovementInput]) -> Decision:
        return decide(state, self.cfg, self.mode)


class FixedController:
    name = "Fixed-time"

    def __init__(self, cfg: Optional[TrafficConfig] = None, mode: Optional[str] = None):
        self.cfg = cfg or TrafficConfig()
        self.mode = mode or self.cfg.mode
        self.names = list(CANDIDATE_SETS[self.mode])
        self.i = -1

    def reset(self):
        self.i = -1

    def _green_for(self, name: str) -> int:
        if name.endswith("straight"):
            return 30
        if name.endswith("right"):
            return 12
        return 20

    def decide(self, state):
        self.i = (self.i + 1) % len(self.names)
        name = self.names[self.i]
        return Decision(action="FIXED", mode=self.mode, candidate=name,
                        served=list(CANDIDATE_SETS[self.mode][name]),
                        green_s=self._green_for(name), amber_s=self.cfg.amber_s,
                        all_red_s=self.cfg.all_red_s,
                        reason=f"Fixed timer: {name} for {self._green_for(name)} s, "
                               "whether or not anyone is waiting.")


class AdaptiveController:
    name = "Adaptive (queue-only)"

    def __init__(self, cfg: Optional[TrafficConfig] = None, mode: Optional[str] = None):
        self.cfg = cfg or TrafficConfig()
        self.mode = mode or self.cfg.mode
        self.cands = CANDIDATE_SETS[self.mode]

    def reset(self):
        pass

    def decide(self, state):
        analysis = analyse_state(state, self.cfg, [])
        best, best_q = None, -1.0
        for name, keys in self.cands.items():
            q = sum(analysis[k].queue_pce for k in keys)
            if q > best_q:
                best, best_q = name, q
        keys = self.cands[best]
        if best_q <= 0:
            green = self.cfg.min_green_s
        else:
            green = compute_green(max(analysis[k].queue_pce for k in keys), None, self.cfg)
        return Decision(action="ADAPTIVE", mode=self.mode, candidate=best,
                        served=list(keys), green_s=green, amber_s=self.cfg.amber_s,
                        all_red_s=self.cfg.all_red_s,
                        reason=f"Largest queue: {best} ({best_q:.1f} car-units).")


CONTROLLERS = {
    "Fixed-time": FixedController,
    "Adaptive (queue-only)": AdaptiveController,
    "GRIDLOCK-X": GridlockController,
}
