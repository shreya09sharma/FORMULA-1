"""Vehicle counting per approach.

Three ways to get counts, all returning the same shape:
    {"N": {"car": 5, "bus": 1}, "S": {...}, "E": {...}, "W": {...}}

  SimulatedCounter - random plausible counts; needs NO camera, NO GPU
  count_detections - pure Python: detections (class, box) -> counts per lane
  YoloCounter      - real detection with ultralytics YOLO (optional install)

The demo never has to depend on YOLO: if ultralytics is missing, use SimulatedCounter.
"""
from __future__ import annotations

import json
import random
from typing import Dict, List, Optional, Sequence, Tuple

# COCO class name -> GRIDLOCK-X vehicle type (YOLO has no auto-rickshaw class)
COCO_TO_TYPE = {"car": "car", "motorcycle": "two_wheeler", "bicycle": "two_wheeler",
                "bus": "bus", "truck": "truck"}

Point = Tuple[float, float]

# Normalised (0..1) lane regions for a top-down / overhead frame.
# CALIBRATE these for your own camera view.
DEFAULT_LANE_POLYGONS: Dict[str, List[Point]] = {
    "N": [(0.35, 0.0), (0.65, 0.0), (0.65, 0.45), (0.35, 0.45)],
    "S": [(0.35, 0.55), (0.65, 0.55), (0.65, 1.0), (0.35, 1.0)],
    "E": [(0.55, 0.35), (1.0, 0.35), (1.0, 0.65), (0.55, 0.65)],
    "W": [(0.0, 0.35), (0.45, 0.35), (0.45, 0.65), (0.0, 0.65)],
}


def point_in_polygon(x: float, y: float, polygon: Sequence[Point]) -> bool:
    """Ray-casting test (pure Python, no OpenCV needed)."""
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            if x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
    return inside


def count_detections(detections: Sequence[Tuple[str, float, float, float, float]],
                     frame_w: int, frame_h: int,
                     lane_polygons: Optional[Dict[str, List[Point]]] = None
                     ) -> Dict[str, Dict[str, int]]:
    """detections = [(class_name, x1, y1, x2, y2), ...] in pixels."""
    polygons = lane_polygons or DEFAULT_LANE_POLYGONS
    counts: Dict[str, Dict[str, int]] = {a: {} for a in polygons}
    for cls, x1, y1, x2, y2 in detections:
        vtype = COCO_TO_TYPE.get(cls)
        if vtype is None:
            continue
        cx, cy = (x1 + x2) / 2 / frame_w, (y1 + y2) / 2 / frame_h
        for approach, poly in polygons.items():
            if point_in_polygon(cx, cy, poly):
                counts[approach][vtype] = counts[approach].get(vtype, 0) + 1
                break
    return counts


class SimulatedCounter:
    """Fake perception so the whole system runs without a camera."""

    def __init__(self, seed: Optional[int] = None, busy: Sequence[str] = ()):
        self.rng = random.Random(seed)
        self.busy = set(busy)

    def read(self) -> Dict[str, Dict[str, int]]:
        out = {}
        for a in ("N", "S", "E", "W"):
            scale = 2.5 if a in self.busy else 1.0
            out[a] = {"car": int(self.rng.randint(1, 8) * scale),
                      "two_wheeler": int(self.rng.randint(0, 8) * scale),
                      "auto": self.rng.randint(0, 3),
                      "bus": self.rng.randint(0, 1),
                      "truck": self.rng.randint(0, 1)}
        return out


class YoloCounter:
    """Real detection. Install with: pip install ultralytics opencv-python"""

    def __init__(self, weights: str = "yolov8n.pt", conf: float = 0.35,
                 lane_polygons: Optional[Dict[str, List[Point]]] = None):
        try:
            from ultralytics import YOLO          # imported lazily on purpose
        except ImportError as exc:
            raise RuntimeError("ultralytics is not installed - use SimulatedCounter "
                               "or run: pip install ultralytics opencv-python") from exc
        self.model = YOLO(weights)
        self.conf = conf
        self.polygons = lane_polygons or DEFAULT_LANE_POLYGONS

    def count_frame(self, frame) -> Dict[str, Dict[str, int]]:
        h, w = frame.shape[:2]
        result = self.model(frame, conf=self.conf, verbose=False)[0]
        names = result.names
        dets = []
        for box in result.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            dets.append((names[int(box.cls[0])], x1, y1, x2, y2))
        return count_detections(dets, w, h, self.polygons)


def run_video(path: str, every_n_frames: int = 15, max_reads: Optional[int] = None):
    """Print counts as JSON lines for a video file (needs opencv + ultralytics)."""
    import cv2
    counter = YoloCounter()
    cap = cv2.VideoCapture(path)
    i = reads = 0
    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break
        if i % every_n_frames == 0:
            print(json.dumps(counter.count_frame(frame)))
            reads += 1
            if max_reads and reads >= max_reads:
                break
        i += 1
    cap.release()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        run_video(sys.argv[1])
    else:
        print(json.dumps(SimulatedCounter(seed=1).read(), indent=2))
