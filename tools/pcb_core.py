"""Footprint loading and geometry helpers for the Venta board."""
import re, math, os

FPDIR = "/home/claude/work/fplib"


def sexpr(s):
    tok = re.findall(r'"(?:\\.|[^"\\])*"|\(|\)|[^\s()"]+', s)
    st = [[]]
    for t in tok:
        if t == "(":
            st.append([])
        elif t == ")":
            x = st.pop(); st[-1].append(x)
        else:
            st[-1].append(t[1:-1] if t.startswith('"') else t)
    return st[0][0]


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


def load_lib_fp(libname):
    lib, name = libname.split(":")
    t = sexpr(open(f"{FPDIR}/{lib}__{name}.kicad_mod").read())
    fp = Footprint(libname)
    a = kid(t, "attr")
    fp.attr = a[1] if a else "through_hole"
    for txt in kids(t, "fp_text"):
        at = kid(txt, "at")
        if txt[1] == "reference":
            fp.ref_at = (float(at[1]), float(at[2]))
        elif txt[1] == "value":
            fp.val_at = (float(at[1]), float(at[2]))
    for g in t:
        if not isinstance(g, list):
            continue
        if g[0] in ("fp_line", "fp_circle", "fp_arc"):
            layer = kid(g, "layer")[1]
            w = kid(g, "width")
            w = float(w[1]) if w else 0.12
            if g[0] == "fp_line":
                d = [float(v) for v in kid(g, "start")[1:3] + kid(g, "end")[1:3]]
            elif g[0] == "fp_circle":
                d = [float(v) for v in kid(g, "center")[1:3] + kid(g, "end")[1:3]]
            else:  # old arc: start=center, end=start point, angle
                c = [float(v) for v in kid(g, "start")[1:3]]
                s = [float(v) for v in kid(g, "end")[1:3]]
                ang = float(kid(g, "angle")[1])
                d = c + s + [ang]
            fp.gfx.append((g[0], layer, d, w))
        if g[0] == "pad":
            at = kid(g, "at"); sz = kid(g, "size")
            dr = kid(g, "drill"); rr = kid(g, "roundrect_rratio")
            assert len(at) < 4 or float(at[3]) == 0, "rotated pad in " + libname
            fp.pads.append(Pad(g[1], g[2], g[3], float(at[1]), float(at[2]), float(sz[1]), float(sz[2]),
                               float(dr[1]) if dr else None, float(rr[1]) if rr else None, kid(g, "layers")[1:]))
    return fp


def pot_fp(dual):
    fp = Footprint("Venta:Pot_Alpha_16mm_RA_" + ("Dual" if dual else "Single"))
    fp.attr = "through_hole"
    rows = [(16.0, ["1", "2", "3"])] + ([(11.0, ["4", "5", "6"])] if dual else [])
    for y, nums in rows:
        for i, n in enumerate(nums):
            fp.pads.append(Pad(n, "thru_hole", "rect" if n in ("1", "4") else "circle", -5 + 5 * i, y, 2.2, 2.2, 1.3,
                               None, ["*.Cu", "*.Mask"]))
    # body outline (front view, pot sits on the F side between board and lid), shaft at origin
    fp.gfx.append(("fp_circle", "F.SilkS", [0, 0, 8.25, 0], 0.15))
    fp.gfx.append(("fp_circle", "F.Fab", [0, 0, 3.0, 0], 0.1))  # shaft
    fp.gfx.append(("fp_line", "F.Fab", [-1.5, 0, 1.5, 0], 0.1))
    fp.gfx.append(("fp_line", "F.Fab", [0, -1.5, 0, 1.5], 0.1))
    ymax = 16 + 1.6
    for (x1, y1, x2, y2) in [(-8.5, -8.5, 8.5, -8.5), (8.5, -8.5, 8.5, ymax), (8.5, ymax, -8.5, ymax), (-8.5, ymax, -8.5, -8.5)]:
        fp.gfx.append(("fp_line", "F.CrtYd", [x1, y1, x2, y2], 0.05))
    fp.ref_at = (0, 3.5)
    fp.val_at = (0, -4)
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
