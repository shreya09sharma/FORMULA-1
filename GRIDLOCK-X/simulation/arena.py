"""What-If Arena: run every controller on the same scenarios and compare."""
from __future__ import annotations

from typing import Iterable, List, Optional

from config import TrafficConfig
from simulation.controllers import CONTROLLERS
from simulation.scenarios import SCENARIOS
from simulation.simulator import Simulator


def run_arena(scenario_names: Optional[Iterable[str]] = None, seeds=(1, 2, 3),
              cfg: Optional[TrafficConfig] = None,
              controllers: Optional[Iterable[str]] = None) -> List[dict]:
    """Return one averaged row per (scenario, controller)."""
    cfg = cfg or TrafficConfig()
    scenario_names = list(scenario_names or SCENARIOS)
    controllers = list(controllers or CONTROLLERS)
    rows = []
    for sname in scenario_names:
        for cname in controllers:
            runs = [Simulator(SCENARIOS[sname], CONTROLLERS[cname](cfg), cfg, seed=s).run()
                    for s in seeds]
            amb = [r.ambulance_delay_s for r in runs if r.ambulance_delay_s is not None]
            n = len(runs)
            rows.append({
                "scenario": sname, "controller": cname,
                "avg_delay_s": sum(r.avg_delay_s for r in runs) / n,
                "max_wait_s": sum(r.max_wait_s for r in runs) / n,
                "ambulance_delay_s": (sum(amb) / len(amb)) if amb else None,
                "throughput": sum(r.departed for r in runs) / n,
                "wasted_green_blocked_s": sum(r.wasted_green_blocked_s for r in runs) / n,
                "wasted_green_empty_s": sum(r.wasted_green_empty_s for r in runs) / n,
                "fuel_l": sum(r.fuel_l for r in runs) / n,
                "co2_kg": sum(r.co2_kg for r in runs) / n,
            })
    return rows


def impact_vs_fixed(rows: List[dict]) -> List[dict]:
    """Improvement of each controller over Fixed-time, per scenario."""
    fixed = {r["scenario"]: r for r in rows if r["controller"] == "Fixed-time"}
    out = []
    for r in rows:
        base = fixed.get(r["scenario"])
        if not base or r["controller"] == "Fixed-time":
            continue
        pct = lambda a, b: (100.0 * (a - b) / a) if a else 0.0
        out.append({
            "scenario": r["scenario"], "controller": r["controller"],
            "delay_reduction_pct": pct(base["avg_delay_s"], r["avg_delay_s"]),
            "fuel_saved_l": base["fuel_l"] - r["fuel_l"],
            "co2_saved_kg": base["co2_kg"] - r["co2_kg"],
            "max_wait_reduction_pct": pct(base["max_wait_s"], r["max_wait_s"]),
        })
    return out
