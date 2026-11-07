import math

from rs_core import geometry as g


def test_shoelace_sign_and_area():
    rect = [(0, 0), (4, 0), (4, 5), (0, 5)]
    assert g.shoelace(rect) > 0
    assert g.polygon_area(rect) == 20
    assert g.shoelace(list(reversed(rect))) < 0


def test_inward_normal_points_inside():
    rect = [(0, 0), (4, 0), (4, 5), (0, 5)]
    for i in range(4):
        a, b = rect[i], rect[(i + 1) % 4]
        n = g.inward_normal(a, b)
        mid = g.add(g.scale(g.add(a, b), 0.5), g.scale(n, 0.1))
        assert g.point_in_polygon(mid, rect)


def test_point_in_polygon_edges_and_outside():
    rect = [(0, 0), (4, 0), (4, 5), (0, 5)]
    assert g.point_in_polygon((2, 2), rect)
    assert g.point_in_polygon((0, 2.5), rect)  # on an edge
    assert not g.point_in_polygon((-0.01, 2.5), rect)
    assert not g.point_in_polygon((4.01, 2.5), rect)


def test_simple_polygon_detection():
    assert g.polygon_is_simple([(0, 0), (4, 0), (4, 5), (0, 5)])
    bow = [(0, 0), (4, 5), (4, 0), (0, 5)]
    assert not g.polygon_is_simple(bow)
    assert not g.polygon_is_simple([(0, 0), (0, 0), (1, 1)])


def test_front_and_right_vectors():
    f = g.front_vector(0.0)
    assert abs(f[0]) < 1e-9 and abs(f[1] + 1) < 1e-9  # faces -Z
    r = g.right_vector(0.0)
    assert abs(r[0] - 1) < 1e-9 and abs(r[1]) < 1e-9
    f = g.front_vector(math.pi)
    assert abs(f[1] - 1) < 1e-9  # faces +Z
    assert abs(g.yaw_facing((0, 1)) - math.pi) < 1e-9
    assert abs(g.yaw_facing((0, -1))) < 1e-9


def test_rect_corners_rotation():
    c = g.rect_corners((0, 0), 2, 1, math.pi / 2)
    xs = sorted(round(p[0], 6) for p in c)
    zs = sorted(round(p[1], 6) for p in c)
    assert xs == [-0.5, -0.5, 0.5, 0.5]
    assert zs == [-1, -1, 1, 1]


def test_overlap_depth():
    a = g.rect_corners((0, 0), 2, 2, 0)
    b = g.rect_corners((1.5, 0), 2, 2, 0)
    assert abs(g.convex_overlap_depth(a, b) - 0.5) < 1e-9
    c = g.rect_corners((2.0, 0), 2, 2, 0)
    assert g.convex_overlap_depth(a, c) == 0  # touching
    d = g.rect_corners((5, 5), 1, 1, 0.3)
    assert g.convex_overlap_depth(a, d) == 0


def test_intersection_area():
    a = g.rect_corners((0, 0), 2, 2, 0)
    b = g.rect_corners((1, 1), 2, 2, 0)
    assert abs(g.convex_intersection_area(a, b) - 1.0) < 1e-9


def test_polygon_segment_distance():
    a = g.rect_corners((0, 0), 2, 2, 0)
    assert abs(g.polygon_segment_distance(a, (3, -1), (3, 1)) - 2.0) < 1e-9
    assert g.polygon_segment_distance(a, (0, -5), (0, 5)) == 0


def test_normalize_yaw():
    assert abs(g.normalize_yaw(3 * math.pi) - math.pi) < 1e-9
    assert abs(g.normalize_yaw(-math.pi / 2) + math.pi / 2) < 1e-9
