from perception.detector import SimulatedCounter, count_detections, point_in_polygon


def test_point_in_polygon():
    square = [(0, 0), (1, 0), (1, 1), (0, 1)]
    assert point_in_polygon(0.5, 0.5, square)
    assert not point_in_polygon(1.5, 0.5, square)


def test_detections_are_assigned_to_lanes_and_mapped_to_types():
    dets = [("car", 600, 0, 680, 100),            # top centre -> North
            ("motorcycle", 600, 650, 680, 700),   # bottom centre -> South
            ("bus", 1100, 340, 1250, 400),        # right -> East
            ("person", 600, 50, 620, 100)]        # ignored
    c = count_detections(dets, 1280, 720)
    assert c["N"] == {"car": 1} and c["S"] == {"two_wheeler": 1} and c["E"] == {"bus": 1}
    assert c["W"] == {}


def test_simulated_counter_works_without_camera():
    c = SimulatedCounter(seed=3, busy=["N"]).read()
    assert set(c) == {"N", "S", "E", "W"}
