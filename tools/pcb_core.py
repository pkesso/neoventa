"""Footprint loading and geometry helpers for the Venta board."""
import re, math, os

FPDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fplib")


def sexpr(s, keep_quotes=False):
    """Parse an S-expression into nested lists. keep_quotes keeps string tokens quoted, so dump() can write them back."""
    tok = re.findall(r'"(?:\\.|[^"\\])*"|\(|\)|[^\s()"]+', s)
    st = [[]]
    for t in tok:
        if t == "(":
            st.append([])
        elif t == ")":
            x = st.pop(); st[-1].append(x)
        else:
            st[-1].append(t[1:-1] if t.startswith('"') and not keep_quotes else t)
    return st[0][0]


def dump(node):
    """Inverse of sexpr(..., keep_quotes=True), on one line."""
    return "(" + " ".join(dump(x) if isinstance(x, list) else x for x in node) + ")"


def kids(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]


def kid(node, key):
    k = kids(node, key)
    return k[0] if k else None


class Pad:
    def __init__(self, num, typ, shape, x, y, w, h, drill=None, rratio=None, layers=()):
        self.num, self.typ, self.shape = num, typ, shape
        self.x, self.y, self.w, self.h = x, y, w, h
        self.drill, self.rratio, self.layers = drill, rratio, list(layers)


class Footprint:
    def __init__(self, name):
        self.name = name  # "Lib:Name"
        self.pads, self.gfx = [], []  # gfx: (kind, layer, data, width)
        self.attr = "smd"
        self.ref_at = (0, -1.65)
        self.val_at = (0, 1.65)
        self.raw = None  # library footprint as parsed with keep_quotes=True (None for generated footprints)


def arc_points(s, m, e, n=8):
    """n+1 points along the circular arc from s through m to e."""
    (ax, ay), (bx, by), (cx, cy) = s, m, e
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return [s, e]
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    r = math.dist((ux, uy), s)
    a0, am, a1 = (math.atan2(p[1] - uy, p[0] - ux) for p in (s, m, e))
    sweep = (a1 - a0) % (2 * math.pi)
    if (am - a0) % (2 * math.pi) > sweep:  # the arc goes the other way round
        sweep -= 2 * math.pi
    return [(ux + r * math.cos(a0 + sweep * i / n), uy + r * math.sin(a0 + sweep * i / n)) for i in range(n + 1)]


def load_lib_fp(libname):
    lib, name = libname.split(":")
    text = open(f"{FPDIR}/{lib}__{name}.kicad_mod", encoding="utf-8").read()
    t = sexpr(text)
    fp = Footprint(libname)
    fp.raw = sexpr(text, keep_quotes=True)
    a = kid(t, "attr")
    fp.attr = a[1] if a else "through_hole"
    # reference/value positions: (property "Reference" ...) since KiCad 8, (fp_text reference ...) before
    for txt in kids(t, "property") + kids(t, "fp_text"):
        at = kid(txt, "at")
        if txt[1] in ("Reference", "reference"):
            fp.ref_at = (float(at[1]), float(at[2]))
        elif txt[1] in ("Value", "value"):
            fp.val_at = (float(at[1]), float(at[2]))
    for g in t:
        if not isinstance(g, list):
            continue
        if g[0] in ("fp_line", "fp_circle", "fp_arc", "fp_rect", "fp_poly"):
            layer = kid(g, "layer")[1]
            w = kid(g, "width") or kid(kid(g, "stroke") or [], "width")
            w = float(w[1]) if w else 0.12
            pt = lambda key: [float(v) for v in kid(g, key)[1:3]]
            if g[0] == "fp_line":
                fp.gfx.append(("fp_line", layer, pt("start") + pt("end"), w))
            elif g[0] == "fp_circle":
                fp.gfx.append(("fp_circle", layer, pt("center") + pt("end"), w))
                if layer.endswith("CrtYd"):  # courtyard() works on line end points: add the bounding square
                    cx, cy = pt("center"); r = math.dist(pt("center"), pt("end"))
                    for x1, y1, x2, y2 in [(-r, -r, r, -r), (r, -r, r, r), (r, r, -r, r), (-r, r, -r, -r)]:
                        fp.gfx.append(("fp_line", layer, [cx + x1, cy + y1, cx + x2, cy + y2], w))
            elif g[0] == "fp_rect":
                (x1, y1), (x2, y2) = pt("start"), pt("end")
                for d in [(x1, y1, x2, y1), (x2, y1, x2, y2), (x2, y2, x1, y2), (x1, y2, x1, y1)]:
                    fp.gfx.append(("fp_line", layer, list(d), w))
            elif g[0] == "fp_poly":
                pts = [(float(p[1]), float(p[2])) for p in kids(kid(g, "pts"), "xy")]
                for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
                    fp.gfx.append(("fp_line", layer, [x1, y1, x2, y2], w))
            elif kid(g, "angle"):  # old arc: start=center, end=start point, angle
                fp.gfx.append(("fp_arc", layer, pt("start") + pt("end") + [float(kid(g, "angle")[1])], w))
            else:  # start/mid/end arc: approximate with segments (library footprints are written from fp.raw)
                pts = arc_points(pt("start"), pt("mid"), pt("end"))
                for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                    fp.gfx.append(("fp_line", layer, [x1, y1, x2, y2], w))
        if g[0] == "pad":
            at = kid(g, "at"); sz = kid(g, "size")
            dr = kid(g, "drill"); rr = kid(g, "roundrect_rratio")
            assert len(at) < 4 or float(at[3]) == 0, "rotated pad in " + libname
            fp.pads.append(Pad(g[1], g[2], g[3], float(at[1]), float(at[2]), float(sz[1]), float(sz[2]),
                               float(dr[1]) if dr else None, float(rr[1]) if rr else None, kid(g, "layers")[1:]))
    return fp


POT_R = 8.5  # Alpha 16 mm pot body radius (Ø17)


def pot_fp(dual):
    fp = Footprint("Venta:Pot_Alpha_16mm_RA_" + ("Dual" if dual else "Single"))
    fp.attr = "through_hole"
    rows = [(16.0, ["1", "2", "3"])] + ([(11.0, ["4", "5", "6"])] if dual else [])
    for y, nums in rows:
        for i, n in enumerate(nums):
            fp.pads.append(Pad(n, "thru_hole", "rect" if n in ("1", "4") else "circle", -5 + 5 * i, y, 2.2, 2.2, 1.3,
                               None, ["*.Cu", "*.Mask"]))
    # body outline, Ø17 (Alpha RV16AF-41 / RV16A01F-41 datasheet), shaft at origin; the pot sits on the F side
    # between board and lid. On Fab only: the pot body hides it after assembly, and it hangs over the board edge
    fp.gfx.append(("fp_circle", "F.Fab", [0, 0, POT_R, 0], 0.1))
    fp.gfx.append(("fp_circle", "F.Fab", [0, 0, 3.0, 0], 0.1))  # shaft
    fp.gfx.append(("fp_line", "F.Fab", [-1.5, 0, 1.5, 0], 0.1))
    fp.gfx.append(("fp_line", "F.Fab", [0, -1.5, 0, 1.5], 0.1))
    r = POT_R + 0.25        # body + 0.25 mm courtyard clearance
    ymax = 16 + 1.1 + 0.25  # pin row + pad radius + 0.25 mm courtyard clearance
    for (x1, y1, x2, y2) in [(-r, -r, r, -r), (r, -r, r, ymax), (r, ymax, -r, ymax), (-r, ymax, -r, -r)]:
        fp.gfx.append(("fp_line", "F.CrtYd", [x1, y1, x2, y2], 0.05))
    fp.ref_at = (0, 3.5)
    fp.val_at = (0, 5.2)  # under the reference, inside the body outline
    return fp


def wirepad_fp():
    fp = Footprint("Venta:WirePad")
    fp.attr = "through_hole"
    fp.pads.append(Pad("1", "thru_hole", "circle", 0, 0, 2.2, 2.2, 1.1, None, ["*.Cu", "*.Mask"]))
    for (x1, y1, x2, y2) in [(-1.4, -1.4, 1.4, -1.4), (1.4, -1.4, 1.4, 1.4), (1.4, 1.4, -1.4, 1.4), (-1.4, 1.4, -1.4, -1.4)]:
        fp.gfx.append(("fp_line", "F.CrtYd", [x1, y1, x2, y2], 0.05))
    fp.ref_at = (0, -2.3)
    fp.val_at = (0, 2.3)
    return fp


import functools
@functools.lru_cache(maxsize=None)
def get_fp(name):
    if name == "Venta:Pot_Alpha_16mm_RA_Single":
        return pot_fp(False)
    if name == "Venta:Pot_Alpha_16mm_RA_Dual":
        return pot_fp(True)
    if name == "Venta:WirePad":
        return wirepad_fp()
    return load_lib_fp(name)


def flip_layer(l):
    return {"F.Cu": "B.Cu", "B.Cu": "F.Cu", "F.Mask": "B.Mask", "B.Mask": "F.Mask", "F.Paste": "B.Paste",
            "B.Paste": "F.Paste", "F.SilkS": "B.SilkS", "B.SilkS": "F.SilkS", "F.Fab": "B.Fab", "B.Fab": "F.Fab",
            "F.CrtYd": "B.CrtYd", "B.CrtYd": "F.CrtYd"}.get(l, l)


def to_global(px, py, x, y, rot, side):
    """local footprint coords (library orientation) -> board coords. rot in {0,180}."""
    if side == "B":
        py = -py
    if rot == 180:
        px, py = -px, -py
    elif rot != 0:
        raise ValueError("only 0/180 rotations used")
    return x + px, y + py
