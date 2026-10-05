"""Placement for the Venta board (125B / 1590N1)."""
import math
from circuit2 import COMPONENTS
from pcb_core import get_fp, to_global

# board coordinates (mm), enclosure centre at (100,100); face top edge y=40.35
BOARD = (75.0, 60.0, 125.0, 114.0)  # x0, y0, x1, y1
SHAFTS = {"RV4": (86.5, 64.0), "RV1": (113.5, 64.0), "RV3": (86.5, 90.2), "RV2": (113.5, 90.2)}

FIXED = {
    "RV4": (86.5, 64.0, 0), "RV1": (113.5, 64.0, 0), "RV3": (86.5, 90.2, 0), "RV2": (113.5, 90.2, 0),
    "J3": (96.8, 62.6, 0), "J4": (103.2, 62.6, 0),  # clear of the pot courtyards
    "J2": (79.0, 111.0, 0), "J5": (85.0, 111.0, 0), "J7": (91.0, 111.0, 0), "J6": (97.0, 111.0, 0), "J1": (121.0, 111.0, 0),
    "U1": (84.0, 72.0, 0), "U2": (100.0, 72.0, 0), "U3": (116.0, 72.0, 0),
}

COMP = {c[1]: c for c in COMPONENTS}


def pad_list(ref, x, y, rot):
    kind, _, val, pins, fpname, side, lcsc, note = COMP[ref]
    fp = get_fp(fpname)
    out = []
    for p in fp.pads:
        gx, gy = to_global(p.x, p.y, x, y, rot, side)
        pin = p.num
        if kind in ("D", "DS"):
            net = pins["K" if pin == "1" else "A"]
        else:
            net = pins.get(pin)
        out.append((ref, pin, net, gx, gy, p))
    return out


def courtyard(ref, x, y, rot):
    """bounding box of courtyard (global)."""
    kind, _, val, pins, fpname, side, lcsc, note = COMP[ref]
    fp = get_fp(fpname)
    xs, ys = [], []
    for k, layer, d, w in fp.gfx:
        if layer.endswith("CrtYd") and k == "fp_line":
            for (px, py) in ((d[0], d[1]), (d[2], d[3])):
                gx, gy = to_global(px, py, x, y, rot, side)
                xs.append(gx); ys.append(gy)
    if not xs:
        for p in fp.pads:
            gx, gy = to_global(p.x, p.y, x, y, rot, side)
            xs += [gx - p.w / 2 - .25, gx + p.w / 2 + .25]; ys += [gy - p.h / 2 - .25, gy + p.h / 2 + .25]
    return min(xs), min(ys), max(xs), max(ys)


def auto_place(order=None, fixed=None, seed_slots=None):
    fixed = dict(FIXED if fixed is None else fixed)
    placed = dict(fixed)
    # obstacles on bottom side: B-side courtyards of fixed SMD + all THT pads (+1 mm)
    boxes = []
    for ref, (x, y, r) in placed.items():
        side = COMP[ref][5]
        if side == "B":
            boxes.append(courtyard(ref, x, y, r))
        for (_, _, _, gx, gy, p) in pad_list(ref, x, y, r):
            if p.typ == "thru_hole":
                boxes.append((gx - p.w / 2 - 0.6, gy - p.h / 2 - 0.6, gx + p.w / 2 + 0.6, gy + p.h / 2 + 0.6))
    # net -> list of fixed pad positions
    netpos = {}
    for ref, (x, y, r) in placed.items():
        for (_, _, net, gx, gy, p) in pad_list(ref, x, y, r):
            netpos.setdefault(net, []).append((gx, gy))
    todo = [c[1] for c in COMPONENTS if c[1] not in placed]
    # place parts with most fixed connections first
    def score(ref):
        return -sum(len(netpos.get(n, [])) for n in set(COMP[ref][3].values()))
    todo.sort(key=score)
    x0, y0, x1, y1 = BOARD
    for ref in todo:
        nets = set(COMP[ref][3].values()) - {"GND", "VCC"}
        pts = [p for n in nets for p in netpos.get(n, [])] or [p for n in COMP[ref][3].values() for p in netpos.get(n, [])]
        if pts:
            tx = sum(p[0] for p in pts) / len(pts); ty = sum(p[1] for p in pts) / len(pts)
        else:
            tx, ty = 100, 90
        best = None
        for yy in [y0 + 1.5 + 0.5 * k for k in range(int((y1 - y0 - 3) / 0.5) + 1)]:
            for xx in [x0 + 2.5 + 0.5 * k for k in range(int((x1 - x0 - 5) / 0.5) + 1)]:
                for rot in (0, 180):
                    bb = courtyard(ref, xx, yy, rot)
                    if bb[0] < x0 + 0.6 or bb[1] < y0 + 0.6 or bb[2] > x1 - 0.6 or bb[3] > y1 - 0.6:
                        continue
                    if any(not (bb[2] + 0.35 <= b[0] or b[2] + 0.35 <= bb[0] or bb[3] + 0.35 <= b[1] or b[3] + 0.35 <= bb[1]) for b in boxes):
                        continue
                    # cost: wire length from each pad to its net's existing pads
                    cost = 0
                    for (_, _, net, gx, gy, p) in pad_list(ref, xx, yy, rot):
                        ps = netpos.get(net, [])
                        if ps:
                            cost += min(math.hypot(gx - a, gy - b) for a, b in ps) * (0.3 if net in ("GND", "VCC") else 1)
                        else:
                            cost += 0.2 * math.hypot(gx - tx, gy - ty)
                    if best is None or cost < best[0]:
                        best = (cost, xx, yy, rot)
        assert best, "no room for " + ref
        _, xx, yy, rot = best
        placed[ref] = (xx, yy, rot)
        boxes.append(courtyard(ref, xx, yy, rot))
        for (_, _, net, gx, gy, p) in pad_list(ref, xx, yy, rot):
            netpos.setdefault(net, []).append((gx, gy))
    return placed
