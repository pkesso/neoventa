"""Exact-geometry DRC: clearance between different nets, edge clearance, net connectivity."""
import math, pickle, sys, itertools
from place import BOARD, pad_list, COMP
from route import TRACK, VIA_D

CLEAR = 0.2
EDGE = 0.3


def seg_seg(a, b, c, d):
    def ps(p, a, b):
        ax, ay = a; bx, by = b; px, py = p
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
        return math.hypot(px - ax - t * dx, py - ay - t * dy)
    def inter(a, b, c, d):
        def o(p, q, r):
            return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        o1, o2, o3, o4 = o(a, b, c), o(a, b, d), o(c, d, a), o(c, d, b)
        return (o1 * o2 < 0) and (o3 * o4 < 0)
    if inter(a, b, c, d):
        return 0.0
    return min(ps(a, c, d), ps(b, c, d), ps(c, a, b), ps(d, a, b))


class Shape:
    # kind 'cap' (segment with radius), 'rect' (cx,cy,hw,hh), 'circ' treated as cap with zero length
    def __init__(self, kind, layers, net, data, tag):
        self.kind, self.layers, self.net, self.data, self.tag = kind, set(layers), net, data, tag

    def bbox(self):
        if self.kind == "cap":
            (a, b, r) = self.data
            return min(a[0], b[0]) - r, min(a[1], b[1]) - r, max(a[0], b[0]) + r, max(a[1], b[1]) + r
        cx, cy, hw, hh = self.data
        return cx - hw, cy - hh, cx + hw, cy + hh


def rect_edges(cx, cy, hw, hh):
    p = [(cx - hw, cy - hh), (cx + hw, cy - hh), (cx + hw, cy + hh), (cx - hw, cy + hh)]
    return [(p[i], p[(i + 1) % 4]) for i in range(4)]


def dist(s, t):
    if s.kind == "rect" and t.kind == "cap":
        s, t = t, s
    if s.kind == "cap" and t.kind == "cap":
        (a, b, r1), (c, d, r2) = s.data, t.data
        return seg_seg(a, b, c, d) - r1 - r2
    if s.kind == "cap" and t.kind == "rect":
        (a, b, r) = s.data
        cx, cy, hw, hh = t.data
        for p in (a, b):
            if abs(p[0] - cx) <= hw and abs(p[1] - cy) <= hh:
                return -r
        return min(seg_seg(a, b, e0, e1) for e0, e1 in rect_edges(cx, cy, hw, hh)) - r
    # rect-rect
    (c1x, c1y, w1, h1), (c2x, c2y, w2, h2) = s.data, t.data
    dx = max(0, abs(c1x - c2x) - w1 - w2); dy = max(0, abs(c1y - c2y) - h1 - h2)
    return math.hypot(dx, dy)


def build(placed, tracks, vias):
    shapes = []
    for ref, (x, y, r) in placed.items():
        side = COMP[ref][5]
        for (rf, pin, net, gx, gy, p) in pad_list(ref, x, y, r):
            layers = ["F.Cu", "B.Cu"] if p.typ == "thru_hole" else (["B.Cu"] if side == "B" else ["F.Cu"])
            if p.shape == "circle":
                shapes.append(Shape("cap", layers, net, ((gx, gy), (gx, gy), p.w / 2), f"{rf}.{pin}"))
            else:
                shapes.append(Shape("rect", layers, net, (gx, gy, p.w / 2, p.h / 2), f"{rf}.{pin}"))
    for layer, net, pts in tracks:
        for a, b in zip(pts, pts[1:]):
            shapes.append(Shape("cap", [layer], net, (a, b, TRACK / 2), f"trk {net}"))
    for x, y, net in vias:
        shapes.append(Shape("cap", ["F.Cu", "B.Cu"], net, ((x, y), (x, y), VIA_D / 2), f"via {net}"))
    return shapes


def run(placed, tracks, vias, verbose=True):
    shapes = build(placed, tracks, vias)
    errs = []
    x0, y0, x1, y1 = BOARD
    for s in shapes:
        b = s.bbox()
        if b[0] < x0 + EDGE or b[1] < y0 + EDGE or b[2] > x1 - EDGE or b[3] > y1 - EDGE:
            errs.append(("edge", s.tag, round(min(b[0] - x0, b[1] - y0, x1 - b[2], y1 - b[3]), 3)))
    # clearance + connectivity
    parent = list(range(len(shapes)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    bbs = [s.bbox() for s in shapes]
    for i, j in itertools.combinations(range(len(shapes)), 2):
        s, t = shapes[i], shapes[j]
        if not (s.layers & t.layers):
            continue
        a, b = bbs[i], bbs[j]
        if a[2] + CLEAR < b[0] or b[2] + CLEAR < a[0] or a[3] + CLEAR < b[1] or b[3] + CLEAR < a[1]:
            continue
        d = dist(s, t)
        if s.net == t.net:
            if d <= 1e-6:
                parent[find(i)] = find(j)
        elif d < CLEAR - 1e-6:
            errs.append(("clearance", s.tag, t.tag, round(d, 3)))
    groups = {}
    for i, s in enumerate(shapes):
        if s.net:
            groups.setdefault(s.net, set()).add(find(i))
    for net, g in groups.items():
        if len(g) > 1:
            errs.append(("unconnected", net, len(g)))
    if verbose:
        print(f"{len(shapes)} shapes, {len(errs)} problems")
        for e in errs[:40]:
            print(" ", e)
    return errs


if __name__ == "__main__":
    placed, tracks, vias, failed = pickle.load(open(sys.argv[1] if len(sys.argv) > 1 else "routed.pkl", "rb"))
    run(placed, tracks, vias)
