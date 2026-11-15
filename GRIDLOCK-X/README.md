# GRIDLOCK-X 🚦

Intelligent traffic signal management for a 4-way intersection - **100% Python**.

> Existing adaptive signals ask *which road needs green*.
> GRIDLOCK-X also asks *whether giving that road green will actually help*.

## What it does
- **Density-based green time** - busier movements get longer green (clamped 8-50 s).
- **Vehicle-type weighting** - bus/truck = 3 car-units, scooter = 0.5, auto = 0.8 (optional "people" basis).
- **Turn-aware phases** - NS straight, EW straight, NS right, EW right. Old one-approach mode kept as `single`.
- **Fairness** - waiting-time bonus (starts at 45 s, capped), so no road starves.
- **Emergency priority** - overrides everything, conflicting traffic is held red.
- **Spillback protection** - a movement whose exit road is >= 85% full is not released.
- **Explanations** - every decision says *why green* and *why not the others*.

## Folder structure
```
GRIDLOCK-X/
├── config.py            all tunable numbers (TrafficConfig)
├── traffic.py           the decision engine (pure functions, no printing inside)
├── main.py              command line entry point
├── conftest.py          lets pytest import from the project root
├── requirements.txt
├── perception/
│   └── detector.py      YOLO counting + simulated counts (works with no camera/GPU)
├── simulation/
│   ├── simulator.py     second-by-second intersection simulator
│   ├── controllers.py   Fixed-time, Adaptive (queue-only), GRIDLOCK-X
│   ├── scenarios.py     6 scenarios (rush, blocked exit, ambulances, mixed India...)
│   └── arena.py         What-If Arena + impact numbers
├── dashboard/
│   └── app.py           Streamlit dashboard
└── tests/               31 tests
```

## Setup (Python 3.9+)
```bash
cd GRIDLOCK-X
python -m venv venv
venv\Scripts\activate          # Windows      (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
```

## Run
```bash
python main.py demo            # emergency, blocked exit, fairness, weighting demos
python main.py arena           # Fixed vs Adaptive vs GRIDLOCK-X on all scenarios
python main.py simulate ambulance
python main.py dashboard       # opens http://localhost:8501
python main.py test            # 31 tests
```

## Dashboard pages
| Page | What judges see |
|---|---|
| Live Simulation | animated junction, "Why green?" panel, live metrics |
| Manual Decision | edit counts / waits / exit-road fullness / emergency, decision changes instantly |
| What-If Arena | Fixed vs Adaptive vs GRIDLOCK-X, delay, fairness, fuel and CO2 estimates |
| Settings | sliders for weights, thresholds, green limits, phase mode |
| Decision Log | every decision + reason, download as CSV |

## Using the engine from your own code
```python
from traffic import decide, MovementInput as M
d = decide({"N_straight": M({"car": 20}, wait_s=30),
            "E_straight": M({"car": 2}, emergency=True)})
print(d.candidate, d.green_s, d.reason)
print(d.to_json())             # for an API or dashboard
```
Movement keys: `N_straight, N_right, S_straight, S_right, E_straight, E_right, W_straight, W_right`
(left turns are free-flowing in left-hand traffic, so they are counted in `straight`).

## Real YOLO camera input (optional)
```bash
pip install ultralytics opencv-python
python perception/detector.py path/to/video.mp4
```
Edit `DEFAULT_LANE_POLYGONS` in `perception/detector.py` to match your camera view.
Without a camera, use `SimulatedCounter` - the demo never depends on YOLO.
Feed counts to the engine with `traffic.state_from_approach_counts(...)`.

## Honest notes
- The simulator is our own simplified model (not SUMO). Fuel/CO2 numbers are estimates from idle time.
- Standard YOLO has no auto-rickshaw class; they appear as `car` until you fine-tune a model.
- Results vary with scenario: GRIDLOCK-X's biggest wins are fairness, emergencies and blocked exits.
  A queue-only controller can be slightly faster on average delay in some scenarios.
