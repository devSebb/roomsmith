"""2D geometry in the X-Z plane. Pure functions over tuples; no scene knowledge."""

from __future__ import annotations

import math
from typing import Iterable, Sequence

Point = tuple[float, float]  # (x, z)

EPS = 1e-9


def sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1])


def scale(a: Point, k: float) -> Point:
    return (a[0] * k, a[1] * k)


def dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def cross(a: Point, b: Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def length(a: Point) -> float:
    return math.hypot(a[0], a[1])


def distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def normalize(a: Point) -> Point:
    n = length(a)
    if n < EPS:
        return (0.0, 0.0)
    return (a[0] / n, a[1] / n)


def inward_normal(a: Point, b: Point) -> Point:
    """Unit normal pointing into the room for a wall a->b of a canonical outline.

    Canonical outlines have a positive shoelace sum over (x, z); for those the
    interior lies on the side (-dz, dx) of every edge.
    """
    d = normalize(sub(b, a))
    return (-d[1], d[0])


def shoelace(points: Sequence[Point]) -> float:
    """Signed double area over (x, z). Positive for the canonical orientation."""
    s = 0.0
    n = len(points)
    for i in range(n):
        x1, z1 = points[i]
        x2, z2 = points[(i + 1) % n]
        s += x1 * z2 - x2 * z1
    return s


def polygon_area(points: Sequence[Point]) -> float:
    return abs(shoelace(points)) / 2.0


def centroid(points: Sequence[Point]) -> Point:
    """Area centroid; falls back to the vertex mean for degenerate polygons."""
    s = shoelace(points)
    if abs(s) < EPS:
        n = len(points)
        return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n)
    cx = cz = 0.0
    n = len(points)
    for i in range(n):
        x1, z1 = points[i]
        x2, z2 = points[(i + 1) % n]
        f = x1 * z2 - x2 * z1
        cx += (x1 + x2) * f
        cz += (z1 + z2) * f
    return (cx / (3.0 * s), cz / (3.0 * s))


def bounds(points: Iterable[Point]) -> tuple[float, float, float, float]:
    xs, zs = zip(*points)
    return (min(xs), min(zs), max(xs), max(zs))


def point_in_polygon(p: Point, poly: Sequence[Point], tol: float = 1e-6) -> bool:
    """Even-odd test; points within `tol` of an edge count as inside."""
    if point_segment_distance(p, poly[-1], poly[0]) <= tol:
        return True
    n = len(poly)
    inside = False
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        if point_segment_distance(p, a, b) <= tol:
            return True
        if (a[1] > p[1]) != (b[1] > p[1]):
            x = a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if p[0] < x:
                inside = not inside
    return inside


def point_segment_distance(p: Point, a: Point, b: Point) -> float:
    ab = sub(b, a)
    ab2 = dot(ab, ab)
    if ab2 < EPS:
        return distance(p, a)
    t = max(0.0, min(1.0, dot(sub(p, a), ab) / ab2))
    return distance(p, add(a, scale(ab, t)))


def project_on_segment(p: Point, a: Point, b: Point) -> float:
    """Parameter t in [0, 1] of the closest point on a->b to p."""
    ab = sub(b, a)
    ab2 = dot(ab, ab)
    if ab2 < EPS:
        return 0.0
    return max(0.0, min(1.0, dot(sub(p, a), ab) / ab2))


def _orient(a: Point, b: Point, c: Point) -> float:
    return cross(sub(b, a), sub(c, a))


def segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    """Proper or touching intersection of segments ab and cd."""
    o1 = _orient(a, b, c)
    o2 = _orient(a, b, d)
    o3 = _orient(c, d, a)
    o4 = _orient(c, d, b)
    if ((o1 > EPS and o2 < -EPS) or (o1 < -EPS and o2 > EPS)) and (
        (o3 > EPS and o4 < -EPS) or (o3 < -EPS and o4 > EPS)
    ):
        return True

    def on(a: Point, b: Point, p: Point) -> bool:
        return (
            min(a[0], b[0]) - EPS <= p[0] <= max(a[0], b[0]) + EPS
            and min(a[1], b[1]) - EPS <= p[1] <= max(a[1], b[1]) + EPS
        )

    if abs(o1) <= EPS and on(a, b, c):
        return True
    if abs(o2) <= EPS and on(a, b, d):
        return True
    if abs(o3) <= EPS and on(c, d, a):
        return True
    if abs(o4) <= EPS and on(c, d, b):
        return True
    return False


def polygon_is_simple(poly: Sequence[Point]) -> bool:
    """True when no two non-adjacent edges intersect and no edge is degenerate."""
    n = len(poly)
    if n < 3:
        return False
    for i in range(n):
        if distance(poly[i], poly[(i + 1) % n]) < 1e-6:
            return False
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or (i + 1) % n == j:
                continue
            c, d = poly[j], poly[(j + 1) % n]
            if segments_intersect(a, b, c, d):
                return False
    return True


def rotate(p: Point, yaw: float) -> Point:
    """Rotate a local (x, z) offset about +Y by yaw (right-handed)."""
    c, s = math.cos(yaw), math.sin(yaw)
    return (p[0] * c + p[1] * s, -p[0] * s + p[1] * c)


def front_vector(yaw: float) -> Point:
    """Direction an object faces: -Z at yaw 0."""
    return (-math.sin(yaw), -math.cos(yaw))


def right_vector(yaw: float) -> Point:
    """Direction to the object's own right: +X at yaw 0."""
    return (math.cos(yaw), -math.sin(yaw))


def yaw_facing(direction: Point) -> float:
    """Yaw at which front_vector equals `direction`, in (-pi, pi] (so -0.0 inputs
    never produce -pi where +pi is meant)."""
    return normalize_yaw(math.atan2(-direction[0], -direction[1]))


def normalize_yaw(yaw: float) -> float:
    """Wrap into (-pi, pi]."""
    y = math.fmod(yaw + math.pi, 2 * math.pi)
    if y <= 0:
        y += 2 * math.pi
    return y - math.pi


def rect_corners(center: Point, width: float, depth: float, yaw: float) -> list[Point]:
    """Footprint corners of an upright box, counter-clockwise in local space."""
    hw, hd = width / 2.0, depth / 2.0
    local = [(-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)]
    return [add(center, rotate(p, yaw)) for p in local]


def _axes(poly: Sequence[Point]) -> list[Point]:
    axes = []
    n = len(poly)
    for i in range(n):
        e = sub(poly[(i + 1) % n], poly[i])
        if length(e) < EPS:
            continue
        axes.append(normalize((-e[1], e[0])))
    return axes


def _project(poly: Sequence[Point], axis: Point) -> tuple[float, float]:
    vals = [dot(p, axis) for p in poly]
    return (min(vals), max(vals))


def convex_overlap_depth(a: Sequence[Point], b: Sequence[Point]) -> float:
    """Minimum translation distance that would separate two convex polygons.

    0 when they do not overlap (touching counts as 0).
    """
    best = math.inf
    for axis in _axes(a) + _axes(b):
        a0, a1 = _project(a, axis)
        b0, b1 = _project(b, axis)
        overlap = min(a1, b1) - max(a0, b0)
        if overlap <= EPS:
            return 0.0
        best = min(best, overlap)
    return 0.0 if best is math.inf else best


def convex_intersects(a: Sequence[Point], b: Sequence[Point], min_depth: float = 0.0) -> bool:
    return convex_overlap_depth(a, b) > min_depth


def clip_convex(subject: Sequence[Point], clip: Sequence[Point]) -> list[Point]:
    """Sutherland-Hodgman clip of a convex polygon by a convex clip polygon.

    Both are expected in the same winding; clip must have positive shoelace.
    """
    if shoelace(clip) < 0:
        clip = list(reversed(clip))
    output = list(subject)
    n = len(clip)
    for i in range(n):
        a = clip[i]
        b = clip[(i + 1) % n]
        if not output:
            break
        inp = output
        output = []
        edge = sub(b, a)

        def inside(p: Point) -> bool:
            return cross(edge, sub(p, a)) >= -EPS

        s = inp[-1]
        for e in inp:
            if inside(e):
                if not inside(s):
                    output.append(_line_intersection(s, e, a, b))
                output.append(e)
            elif inside(s):
                output.append(_line_intersection(s, e, a, b))
            s = e
    return output


def _line_intersection(p1: Point, p2: Point, p3: Point, p4: Point) -> Point:
    d = cross(sub(p2, p1), sub(p4, p3))
    if abs(d) < EPS:
        return p2
    t = cross(sub(p3, p1), sub(p4, p3)) / d
    return add(p1, scale(sub(p2, p1), t))


def convex_intersection_area(a: Sequence[Point], b: Sequence[Point]) -> float:
    if shoelace(a) < 0:
        a = list(reversed(a))
    poly = clip_convex(a, b)
    if len(poly) < 3:
        return 0.0
    return polygon_area(poly)


def polygon_segment_distance(poly: Sequence[Point], a: Point, b: Point) -> float:
    """Shortest distance between a convex polygon's boundary/interior and a segment."""
    n = len(poly)
    if any(segments_intersect(poly[i], poly[(i + 1) % n], a, b) for i in range(n)):
        return 0.0
    if point_in_polygon(a, poly) or point_in_polygon(b, poly):
        return 0.0
    best = math.inf
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        best = min(best, point_segment_distance(a, p, q), point_segment_distance(b, p, q))
        best = min(best, point_segment_distance(p, a, b), point_segment_distance(q, a, b))
    return best


def polygon_polygon_distance(a: Sequence[Point], b: Sequence[Point]) -> float:
    """Shortest distance between two convex polygons (0 when they touch or overlap)."""
    if convex_overlap_depth(a, b) > 0:
        return 0.0
    best = math.inf
    n = len(b)
    for i in range(n):
        best = min(best, polygon_segment_distance(a, b[i], b[(i + 1) % n]))
    return best


def is_finite(*values: float) -> bool:
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)
