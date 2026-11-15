"""GRIDLOCK-X decision engine (pure Python, no I/O inside the logic).

Pipeline (strict order):
  1. Analyse every movement (weighted queue, wait, downstream occupancy)
  2. Emergency check            -> overrides everything
  3. Eligibility gate           -> movements with a full exit road are skipped
  4. Score eligible candidates  -> queue + waiting time + fairness bonus
  5. Pick the best candidate
  6. Compute the green time     -> clamped, limited by exit-road space
  7. Build the explanation      -> "Why green?" / "Why not the others?"

A *movement* is one stream of traffic, e.g. "N_straight" or "E_right".
A *candidate* is what can get green together:
  mode "phase"  -> 4 turn-aware phases (NS straight, EW straight, NS right, EW right)
  mode "single" -> 4 approaches, one at a time (North, South, East, West)
India drives on the left, so left turns are free-flowing and are counted
inside "straight". Right turns cross oncoming traffic and get their own phase.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from config import TrafficConfig

APPROACHES = ("N", "S", "E", "W")
APPROACH_NAMES = {"N": "North", "S": "South", "E": "East", "W": "West"}
MOVEMENT_KEYS = tuple(f"{a}_{k}" for a in APPROACHES for k in ("straight", "right"))

CANDIDATE_SETS: Dict[str, Dict[str, List[str]]] = {
    "phase": {
        "NS_straight": ["N_straight", "S_straight"],
        "EW_straight": ["E_straight", "W_straight"],
        "NS_right": ["N_right", "S_right"],
        "EW_right": ["E_right", "W_right"],
    },
    "single": {
        "North": ["N_straight", "N_right"],
        "South": ["S_straight", "S_right"],
        "East": ["E_straight", "E_right"],
        "West": ["W_straight", "W_right"],
    },
}


def movement_label(key: str) -> str:
    approach, kind = key.split("_")
    return f"{APPROACH_NAMES[approach]} {kind}"


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #
@dataclass
class MovementInput:
    """What sensors (YOLO / SUMO / simulator) tell us about one movement."""
    counts: Dict[str, int] = field(default_factory=dict)  # vehicles by type
    wait_s: float = 0.0              # how long the first vehicle has waited
    downstream_occ: float = 0.0      # 0..1, how full the exit road is
    emergency: bool = False          # ambulance / fire engine present
    emergency_wait_s: float = 0.0    # how long it has been waiting (tie-break)


@dataclass
class MovementAnalysis:
    key: str
    label: str
    vehicles: int
    queue_pce: float
    queue_people: float
    wait_s: float
    downstream_occ: float
    blocked: bool
    emergency: bool
    emergency_wait_s: float
    status: str = "EMPTY"


@dataclass
class CandidateScore:
    name: str
    movements: List[str]
    served: List[str]
    blocked: List[str]
    queue_pce: float
    queue_score: float
    wait_s: float
    wait_score: float
    fairness_bonus: float
    total: float
    eligible: bool
    note: str = ""


@dataclass
class Decision:
    action: str                      # NORMAL / EMERGENCY / FALLBACK_LEAST_BLOCKED /
                                     # ALL_BLOCKED_HOLD / IDLE (baselines: FIXED / ADAPTIVE)
    mode: str = "phase"
    candidate: Optional[str] = None
    served: List[str] = field(default_factory=list)
    green_s: int = 0
    amber_s: int = 0
    all_red_s: int = 0
    reason: str = ""
    why_not: Dict[str, str] = field(default_factory=dict)
    scores: List[CandidateScore] = field(default_factory=list)
    movements: Dict[str, MovementAnalysis] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: Optional[int] = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# --------------------------------------------------------------------------- #
# Step 1: analyse
# --------------------------------------------------------------------------- #
def analyse_state(state: Dict[str, MovementInput], cfg: TrafficConfig,
                  warnings: List[str]) -> Dict[str, MovementAnalysis]:
    """Validate the input and turn raw counts into weighted numbers."""
    unknown = set(state) - set(MOVEMENT_KEYS)
    if unknown:
        raise ValueError(f"unknown movement(s): {sorted(unknown)}; valid: {MOVEMENT_KEYS}")
    out: Dict[str, MovementAnalysis] = {}
    for key in MOVEMENT_KEYS:
        inp = state.get(key, MovementInput())
        pce = people = 0.0
        total = 0
        for vtype, n in inp.counts.items():
            n = int(n)
            if n < 0:
                raise ValueError(f"{key}: negative count for '{vtype}'")
            if vtype not in cfg.pce:
                warnings.append(f"{key}: unknown vehicle type '{vtype}' treated as 1 car-unit")
            pce += n * cfg.pce.get(vtype, 1.0)
            people += n * cfg.people.get(vtype, 1.8)
            total += n
        if inp.wait_s < 0:
            raise ValueError(f"{key}: wait_s cannot be negative")
        occ = float(inp.downstream_occ)
        if not 0.0 <= occ <= 1.0:
            warnings.append(f"{key}: downstream_occ {occ} outside 0..1, clamped")
            occ = min(1.0, max(0.0, occ))
        out[key] = MovementAnalysis(
            key=key, label=movement_label(key), vehicles=total,
            queue_pce=pce, queue_people=people, wait_s=float(inp.wait_s),
            downstream_occ=occ, blocked=occ >= cfg.block_threshold,
            emergency=bool(inp.emergency),
            emergency_wait_s=float(inp.emergency_wait_s),
        )
    return out


def state_from_approach_counts(counts: Dict[str, Dict[str, int]],
                               waits: Optional[Dict[str, float]] = None,
                               downstream: Optional[Dict[str, float]] = None,
                               emergency: Optional[Dict[str, bool]] = None
                               ) -> Dict[str, MovementInput]:
    """Convenience for perception: 4 approach counts -> straight movements.

    counts = {"N": {"car": 10, "bus": 1}, "S": {...}, ...}
    """
    waits, downstream, emergency = waits or {}, downstream or {}, emergency or {}
    state = {}
    for approach, per_type in counts.items():
        state[f"{approach}_straight"] = MovementInput(
            counts=dict(per_type), wait_s=waits.get(approach, 0.0),
            downstream_occ=downstream.get(approach, 0.0),
            emergency=emergency.get(approach, False))
    return state


# --------------------------------------------------------------------------- #
# Helpers: scoring and timing
# --------------------------------------------------------------------------- #
def _scoring_queue(m: MovementAnalysis, cfg: TrafficConfig) -> float:
    if cfg.priority_basis == "people":
        return m.queue_people / cfg.people_per_pce
    return m.queue_pce


def fairness_bonus(wait_s: float, cfg: TrafficConfig) -> float:
    """Grows with waiting time after a threshold, capped so it cannot dominate."""
    extra = wait_s - cfg.fairness_after_s
    if extra <= 0:
        return 0.0
    return min(cfg.fairness_cap, cfg.fairness_rate * extra)


def compute_green(heaviest_pce: float, spare_pce: Optional[float],
                  cfg: TrafficConfig) -> int:
    """Green time from the heaviest served queue, limited by exit-road space."""
    green = cfg.startup_s + heaviest_pce * cfg.headway_s_per_pce
    if spare_pce is not None:
        green = min(green, cfg.startup_s + spare_pce * cfg.headway_s_per_pce)
    green = max(cfg.min_green_s, min(cfg.max_green_s, green))
    return int(round(green))


def _spare_pce(m: MovementAnalysis, cfg: TrafficConfig) -> float:
    return (1.0 - m.downstream_occ) * cfg.exit_capacity_pce


def _score_candidates(cands: Dict[str, List[str]],
                      analysis: Dict[str, MovementAnalysis],
                      cfg: TrafficConfig) -> List[CandidateScore]:
    scores = []
    for name, keys in cands.items():
        waiting = [k for k in keys if analysis[k].vehicles > 0]
        served = [k for k in waiting if not analysis[k].blocked]
        blocked = [k for k in waiting if analysis[k].blocked]
        note = ""
        if not waiting:
            note = "no vehicles waiting"
        elif not served:
            note = "every waiting movement is blocked downstream"
        q = sum(_scoring_queue(analysis[k], cfg) for k in served)
        w = max((analysis[k].wait_s for k in served), default=0.0)
        q_score = cfg.w_queue * min(q, cfg.queue_cap)
        w_score = cfg.w_wait * min(w, cfg.wait_cap)
        bonus = fairness_bonus(w, cfg) if served else 0.0
        scores.append(CandidateScore(
            name=name, movements=list(keys), served=served, blocked=blocked,
            queue_pce=q, queue_score=q_score, wait_s=w, wait_score=w_score,
            fairness_bonus=bonus, total=q_score + w_score + bonus,
            eligible=bool(served), note=note))
    return scores


def _finalise_statuses(analysis, served, held_status="WAITING"):
    for k, m in analysis.items():
        if k in served:
            m.status = "GREEN"
        elif m.vehicles == 0 and not m.emergency:
            m.status = "EMPTY"
        elif held_status == "HELD_FOR_EMERGENCY":
            m.status = "HELD_FOR_EMERGENCY"
        elif m.blocked:
            m.status = "BLOCKED_DOWNSTREAM"
        else:
            m.status = "WAITING"


def _fmt_list(keys):
    return ", ".join(movement_label(k) for k in keys) if keys else "none"


# --------------------------------------------------------------------------- #
# Step 2: emergency
# --------------------------------------------------------------------------- #
def _emergency_decision(cands, analysis, scores, cfg, mode, warnings):
    emergencies = [k for k in MOVEMENT_KEYS if analysis[k].emergency]
    if not emergencies:
        return None
    # tie rule: the ambulance that has waited longest, then fixed movement order
    chosen = max(emergencies,
                 key=lambda k: (analysis[k].emergency_wait_s, -MOVEMENT_KEYS.index(k)))
    cand = next(n for n, keys in cands.items() if chosen in keys)
    served = [k for k in cands[cand]
              if k == chosen or analysis[k].emergency
              or (analysis[k].vehicles > 0 and not analysis[k].blocked)]
    for k in served:
        if analysis[k].emergency and analysis[k].blocked:
            warnings.append(
                f"{movement_label(k)}: exit road {analysis[k].downstream_occ:.0%} full, "
                "emergency vehicle still released - clear the exit road!")
    others = [k for k in emergencies if k not in cands[cand]]
    if others:
        warnings.append(f"Other emergency vehicle(s) queued next: {_fmt_list(others)}")
    _finalise_statuses(analysis, served, "HELD_FOR_EMERGENCY")
    why_not = {s.name: "held red for the emergency vehicle" for s in scores if s.name != cand}
    reason = (f"EMERGENCY: {movement_label(chosen)} has an emergency vehicle"
              f"{f' (waiting {analysis[chosen].emergency_wait_s:.0f} s)' if analysis[chosen].emergency_wait_s else ''}. "
              f"{cand} gets GREEN {cfg.emergency_green_s} s ({_fmt_list(served)}); "
              "all conflicting traffic is held red. Emergency overrides queue, "
              "fairness and downstream checks.")
    return Decision(action="EMERGENCY", mode=mode, candidate=cand, served=served,
                    green_s=cfg.emergency_green_s, amber_s=cfg.amber_s,
                    all_red_s=cfg.all_red_s, reason=reason, why_not=why_not,
                    scores=scores, movements=analysis, warnings=warnings)


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #
def decide(state: Dict[str, MovementInput], cfg: Optional[TrafficConfig] = None,
           mode: Optional[str] = None) -> Decision:
    """Decide which candidate gets green, for how long, and why."""
    cfg = cfg or TrafficConfig()
    cfg.validate()
    mode = mode or cfg.mode
    if mode not in CANDIDATE_SETS:
        raise ValueError(f"unknown mode '{mode}'")
    cands = CANDIDATE_SETS[mode]
    warnings: List[str] = []
    analysis = analyse_state(state, cfg, warnings)
    scores = _score_candidates(cands, analysis, cfg)

    # 2. emergency overrides everything
    emergency = _emergency_decision(cands, analysis, scores, cfg, mode, warnings)
    if emergency:
        return emergency

    # 3-5. eligibility gate, score, pick
    eligible = [s for s in scores if s.eligible]
    if eligible:
        best = max(eligible, key=lambda s: s.total)          # first one wins ties
        return _normal_decision(best, eligible, scores, analysis, cfg, mode, warnings)

    # fallback when nothing is eligible
    return _fallback_decision(cands, analysis, scores, cfg, mode, warnings)


def _normal_decision(best, eligible, scores, analysis, cfg, mode, warnings):
    served = best.served
    heaviest = max(analysis[k].queue_pce for k in served)
    spare = min(_spare_pce(analysis[k], cfg) for k in served)
    green = compute_green(heaviest, spare, cfg)
    _finalise_statuses(analysis, served)

    # would the fairness bonus have changed the result?
    no_bonus = max(eligible, key=lambda s: s.total - s.fairness_bonus)
    fairness_changed = no_bonus.name != best.name

    why_not = {}
    for s in scores:
        if s.name == best.name:
            continue
        if not s.eligible:
            extra = ""
            if s.blocked:
                extra = " (" + ", ".join(
                    f"{movement_label(k)} exit {analysis[k].downstream_occ:.0%} full"
                    for k in s.blocked) + ")"
            why_not[s.name] = f"skipped: {s.note}{extra}"
        else:
            why_not[s.name] = (f"lower score ({s.total:.1f} vs {best.total:.1f}); "
                               f"queue {s.queue_pce:.1f}, wait {s.wait_s:.0f} s")

    reason = (f"{best.name} selected (GREEN {green} s) serving {_fmt_list(served)}. "
              f"Queue {best.queue_pce:.1f} car-units -> {best.queue_score:.1f}, "
              f"longest wait {best.wait_s:.0f} s -> {best.wait_score:.1f}, "
              f"fairness bonus +{best.fairness_bonus:.1f}, total {best.total:.1f}.")
    if best.blocked:
        reason += (" Held back (exit road too full): "
                   + ", ".join(f"{movement_label(k)} {analysis[k].downstream_occ:.0%}"
                               for k in best.blocked) + ".")
    skipped = [s for s in scores if not s.eligible and s.blocked]
    if skipped:
        reason += " Skipped for blocked exit: " + ", ".join(s.name for s in skipped) + "."
    if fairness_changed:
        reason += (f" Fairness bonus changed the decision: {no_bonus.name} would have "
                   "won on queue and waiting time alone.")
    return Decision(action="NORMAL", mode=mode, candidate=best.name, served=served,
                    green_s=green, amber_s=cfg.amber_s, all_red_s=cfg.all_red_s,
                    reason=reason, why_not=why_not, scores=scores,
                    movements=analysis, warnings=warnings)


def _fallback_decision(cands, analysis, scores, cfg, mode, warnings):
    waiting = [m for m in analysis.values() if m.vehicles > 0]
    why_not = {s.name: f"not served: {s.note}" for s in scores}
    if not waiting:
        _finalise_statuses(analysis, [])
        return Decision(action="IDLE", mode=mode, reason="No vehicles waiting - all red, nothing to serve.",
                        why_not=why_not, scores=scores, movements=analysis, warnings=warnings)
    least = min(waiting, key=lambda m: m.downstream_occ)
    if least.downstream_occ >= cfg.full_threshold:
        _finalise_statuses(analysis, [])
        warnings.append("Every exit road is completely full - holding all red to avoid gridlock.")
        return Decision(action="ALL_BLOCKED_HOLD", mode=mode,
                        reason=("All waiting movements have completely full exit roads "
                                f"(best is {least.downstream_occ:.0%}). Holding all red "
                                "instead of releasing vehicles into a jam."),
                        why_not=why_not, scores=scores, movements=analysis, warnings=warnings)
    cand = next(n for n, keys in cands.items() if least.key in keys)
    _finalise_statuses(analysis, [least.key])
    warnings.append("All exits are above the block threshold - serving the least-blocked movement briefly.")
    return Decision(action="FALLBACK_LEAST_BLOCKED", mode=mode, candidate=cand,
                    served=[least.key], green_s=cfg.min_green_s, amber_s=cfg.amber_s,
                    all_red_s=cfg.all_red_s,
                    reason=(f"Every exit is blocked. {least.label} has the emptiest exit "
                            f"({least.downstream_occ:.0%}), so it gets a short GREEN "
                            f"{cfg.min_green_s} s to avoid deadlock."),
                    why_not=why_not, scores=scores, movements=analysis, warnings=warnings)


# --------------------------------------------------------------------------- #
# Pretty printing (used by main.py and tests, never inside the logic)
# --------------------------------------------------------------------------- #
def format_decision(d: Decision) -> str:
    lines = [f"Action   : {d.action}  ({d.mode} mode)",
             f"Green    : {d.candidate or 'none'}  for {d.green_s} s "
             f"(+{d.amber_s} s amber, {d.all_red_s} s all-red)",
             f"Serving  : {_fmt_list(d.served)}",
             f"Reason   : {d.reason}"]
    for name, why in d.why_not.items():
        lines.append(f"  - {name}: {why}")
    for w in d.warnings:
        lines.append(f"  ! {w}")
    return "\n".join(lines)
