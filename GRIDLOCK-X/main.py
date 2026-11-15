"""GRIDLOCK-X command line.

  python main.py demo                 engine demo (emergency, blocked exit, fairness)
  python main.py simulate [scenario]  run one scenario with GRIDLOCK-X and print the log
  python main.py arena                Fixed vs Adaptive vs GRIDLOCK-X on every scenario
  python main.py decide state.json    one decision from a JSON file (use - for stdin)
  python main.py dashboard            open the Streamlit dashboard
  python main.py test                 run all tests
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from config import TrafficConfig
from traffic import MovementInput as M, decide, format_decision

ROOT = Path(__file__).resolve().parent


def cmd_demo(_args):
    print("=== 1. EMERGENCY: ambulance on East, big queue on North ===")
    print(format_decision(decide({"N_straight": M({"car": 30}, wait_s=60),
                                  "E_straight": M({"car": 2}, emergency=True)})))
    print("\n=== 2. DOWNSTREAM BLOCKAGE: North exit road 95% full ===")
    print(format_decision(decide({"N_straight": M({"car": 40}, downstream_occ=0.95),
                                  "E_straight": M({"car": 4}, wait_s=20)})))
    print("\n=== 3. FAIRNESS: quiet East right-turn has waited 150 s ===")
    print(format_decision(decide({"N_straight": M({"car": 30}, wait_s=20),
                                  "E_right": M({"car": 2}, wait_s=150)})))
    print("\n=== 4. VEHICLE WEIGHTING: 5 buses vs 10 scooters (single mode) ===")
    print(format_decision(decide({"N_straight": M({"bus": 5}), "E_straight": M({"two_wheeler": 10})},
                                 mode="single")))


def cmd_simulate(args):
    from simulation.controllers import CONTROLLERS
    from simulation.scenarios import SCENARIOS
    from simulation.simulator import Simulator
    cfg = TrafficConfig()
    sim = Simulator(SCENARIOS[args.scenario], CONTROLLERS[args.controller](cfg), cfg, seed=args.seed)
    metrics = sim.run()
    for row in sim.log[:args.rows]:
        print(f"t={row['t']:>4}s  {row['action']:<10} {str(row['candidate']):<12} "
              f"green {row['green_s']:>2}s  {row['reason'][:90]}")
    print("\n" + json.dumps(metrics.as_dict(), indent=2))


def cmd_arena(args):
    from simulation.arena import impact_vs_fixed, run_arena
    rows = run_arena(seeds=tuple(range(1, args.seeds + 1)))
    print(f"{'scenario':<16}{'controller':<24}{'delay s':>8}{'max wait':>9}{'amb s':>7}"
          f"{'thru':>6}{'blocked-green s':>16}")
    for r in rows:
        amb = "-" if r["ambulance_delay_s"] is None else f"{r['ambulance_delay_s']:.0f}"
        print(f"{r['scenario']:<16}{r['controller']:<24}{r['avg_delay_s']:>8.1f}"
              f"{r['max_wait_s']:>9.0f}{amb:>7}{r['throughput']:>6.0f}"
              f"{r['wasted_green_blocked_s']:>16.0f}")
    print("\nImpact vs Fixed-time (fuel/CO2 are estimates):")
    for i in impact_vs_fixed(rows):
        if i["controller"] == "GRIDLOCK-X":
            print(f"  {i['scenario']:<16} delay {i['delay_reduction_pct']:>5.1f}% lower, "
                  f"fuel saved {i['fuel_saved_l']:.2f} L, CO2 saved {i['co2_saved_kg']:.2f} kg")


def _to_state(raw):
    return {k: M(**v) for k, v in raw.items()}


def cmd_decide(args):
    raw = json.load(sys.stdin if args.file == "-" else open(args.file))
    print(decide(_to_state(raw), TrafficConfig(), args.mode).to_json())


def cmd_dashboard(_args):
    subprocess.run([sys.executable, "-m", "streamlit", "run",
                    str(ROOT / "dashboard" / "app.py")], check=False)


def cmd_test(_args):
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=ROOT))


def main():
    p = argparse.ArgumentParser(description="GRIDLOCK-X traffic controller")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo").set_defaults(fn=cmd_demo)
    s = sub.add_parser("simulate")
    s.add_argument("scenario", nargs="?", default="ambulance")
    s.add_argument("--controller", default="GRIDLOCK-X")
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--rows", type=int, default=15)
    s.set_defaults(fn=cmd_simulate)
    a = sub.add_parser("arena")
    a.add_argument("--seeds", type=int, default=3)
    a.set_defaults(fn=cmd_arena)
    d = sub.add_parser("decide")
    d.add_argument("file")
    d.add_argument("--mode", default="phase", choices=["phase", "single"])
    d.set_defaults(fn=cmd_decide)
    sub.add_parser("dashboard").set_defaults(fn=cmd_dashboard)
    sub.add_parser("test").set_defaults(fn=cmd_test)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
