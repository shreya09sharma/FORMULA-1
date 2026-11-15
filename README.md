# 🚦 GRIDLOCK-X
### A Traffic Signal That Knows When NOT to Turn Green

**Intelligent Adaptive Traffic Management | VIHAAN X – DTU**

GRIDLOCK-X is an intelligent, adaptive traffic management system designed to improve urban traffic flow, reduce unnecessary waiting, prioritize emergency vehicles, and prevent traffic congestion caused by blocked intersections.

Unlike traditional fixed-time traffic signals, GRIDLOCK-X makes traffic signal decisions based on traffic demand, queue conditions, emergency priority, and downstream congestion.

---

## 📌 Problem Statement

Traditional traffic signals operate using predefined timing schedules, regardless of actual traffic conditions.

This creates several problems:

- Unnecessary waiting at intersections even when other roads are empty.
- Delays for emergency vehicles such as ambulances.
- Repeated prioritization of high-traffic roads while low-traffic roads remain waiting.
- Traffic congestion caused by vehicles entering already-blocked roads.
- Lack of transparency regarding why a particular signal receives green.

GRIDLOCK-X addresses these challenges through adaptive and explainable traffic signal decision-making.

---

## 💡 Our Solution

GRIDLOCK-X dynamically evaluates traffic conditions and selects the most appropriate signal phase.

The system combines adaptive traffic control, emergency vehicle prioritization, fairness mechanisms, downstream congestion awareness, and decision logging.

The project is implemented as a simulation-based prototype using Python and SUMO, supported by an interactive dashboard for monitoring and visualization.

---

## ✨ Key Features

### 1. Adaptive Signal Control
- Dynamically adjusts green signal duration according to traffic demand.
- Prioritizes approaches with significant waiting queues.
- Avoids blindly following fixed signal timers.

### 2. Green Corridor – Emergency Priority
- Detects emergency conditions within the simulation.
- Prioritizes emergency vehicle movement.
- Reduces unnecessary signal waiting for emergency vehicles.

### 3. Queue Justice – Fair Traffic Allocation
- Prevents low-traffic approaches from being ignored indefinitely.
- Considers waiting time alongside traffic demand.
- Promotes fairer signal allocation.

### 4. Spillback Shield – Downstream Congestion Awareness
- Considers downstream blockage before allowing vehicles to move.
- Avoids sending traffic into already-congested road sections.
- Helps reduce intersection blockage.

### 5. Signal Black Box – Explainable Decisions
- Records traffic signal decisions.
- Displays the reasons behind selected signal phases.
- Improves transparency and traceability.

### 6. What-If Arena – Traffic Strategy Comparison
- Compares fixed-time traffic control with adaptive GRIDLOCK-X control.
- Supports simulation-based performance evaluation.
- Helps analyze traffic management strategies.

### 7. Interactive Traffic Dashboard
- Displays traffic simulation information.
- Visualizes signal decisions and traffic conditions.
- Provides an interface for running and monitoring scenarios.

---

## 🛠️ Technology Stack

| Technology | Purpose |
|---|---|
| Python | Traffic management logic and simulation |
| SUMO | Microscopic traffic simulation |
| TraCI | Python-SUMO communication and control |
| Streamlit | Interactive dashboard |
| Git & GitHub | Version control and project hosting |
| Pytest | Automated testing |

---

## 🏗️ System Architecture

```text
       Traffic Scenario
             |
             v
      SUMO Simulation
             |
             v
       TraCI Interface
             |
             v
    GRIDLOCK-X Controller
             |
     +-------+-------+
     |       |       |
     v       v       v
 Adaptive  Emergency  Fairness &
 Control   Priority   Spillback
     |       |       |
     +-------+-------+
             |
             v
     Signal Decision Engine
             |
       +-----+------+
       |            |
       v            v
   SUMO Signals   Decision Logs
       |            |
       +-----+------+
             |
             v
    Streamlit Dashboard
             |
             v
      Metrics & Analysis
```

---

## ⚙️ Installation & Setup

### Prerequisites

- Python 3.10 or compatible version
- Eclipse SUMO
- Git
- Visual Studio Code (recommended)

### Step 1: Clone the repository

```bash
git clone https://github.com/YOUR-USERNAME/GRIDLOCK-X.git
cd GRIDLOCK-X
```

### Step 2: Create a virtual environment

```bash
python -m venv venv
```

Activate it:

**Windows PowerShell**

```powershell
.\venv\Scripts\Activate.ps1
```

### Step 3: Install dependencies

```bash
pip install -r requirements.txt
```

Ensure SUMO is installed and its tools are accessible.

---

## ▶️ Running the Project

### Run the traffic simulation

```bash
python main.py simulate ambulance
```

### Run automated tests

```bash
python -m pytest -q
```

### Launch the dashboard

```bash
python -m streamlit run dashboard/app.py
```

Open:

```text
http://localhost:8501
```

> Note: SUMO-integrated execution commands depend on the project version and available CLI options.

---

## 📊 Simulation Results

The following results were obtained from one GRIDLOCK-X ambulance scenario run using seed 1.

| Metric | Result |
|---|---:|
| Vehicles Arrived | 370 |
| Vehicles Departed | 321 |
| Average Delay | 53.62 seconds |
| Maximum Wait | 209 seconds |
| Ambulance Delay | 13.67 seconds |
| Signal Decisions | 27 |
| Wasted Green – Empty | 21 seconds |
| Wasted Green – Blocked | 0 seconds |

**Important:** These are simulation results from one scenario run, not real-world deployment results or proven improvements over fixed-time signals.

---

## 🧪 Testing

GRIDLOCK-X includes automated tests to verify important components of the traffic management system.

Latest verified test execution:

```text
31 passed in 0.47s
```

Tests can be executed using:

```bash
python -m pytest -q
```

---

## 🌍 Real-World Impact

GRIDLOCK-X aims to contribute toward:

- More responsive traffic signal management.
- Reduced unnecessary waiting at intersections.
- Faster emergency vehicle passage.
- Fairer traffic distribution.
- Better utilization of road capacity.
- Reduced congestion caused by downstream blockage.

The current implementation is a simulation-based prototype intended for further testing and development.

---

## 🚀 Future Scope

- Camera-based vehicle detection using OpenCV and YOLO.
- Real-time traffic density estimation.
- Automatic ambulance detection.
- GPS-based emergency vehicle tracking.
- Integration with real traffic signal hardware.
- Multi-intersection coordination and green corridor optimization.
- Deployment pilots at selected intersections.
- More extensive comparisons against fixed-time and existing adaptive traffic controllers.

---

## 🎯 Project Vision

**A green signal should be earned by traffic demand, not blindly granted by a timer.**

GRIDLOCK-X envisions smarter traffic signals that make decisions based on actual road conditions, emergency needs, fairness, and safety.

### GRIDLOCK-X
**Smarter Signals. Fairer Roads. Faster Emergency Response.**

---

## 👩‍💻 Project Contributors

- Shreya Sharma

---

## 📄 License

This project is developed as an academic and hackathon prototype.

A formal open-source license can be added when the project is ready for public distribution.
