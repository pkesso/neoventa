"""Write venta_overdrive.kicad_pcb + project footprint lib, then resave both in KiCad 10 format via kicad-cli."""
import copy, json, math, pickle, uuid, os
from circuit2 import COMPONENTS
from place import COMP, BOARD, SHAFTS, courtyard
from pcb_core import get_fp, flip_layer, to_global, dump
from route import TRACK, VIA_D, VIA_DRILL
from kicad_cli import upgrade
from gen_sch2 import sim_fields

TOOLS = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(TOOLS)  # repository root
NS = uuid.UUID("3b1a7c55-0f7e-4d0c-9a43-6f1b2a9d8e10")
_used = set()


def U(*key):
    """Quoted UUID derived from what the item is, not from where it is written. KiCad sorts items by UUID,
    so a sequential UUID would shift every later item (and reorder the whole file) on any insertion."""
    k = "/".join(map(str, key))
    assert k not in _used, f"duplicate UUID key {k}"
    _used.add(k)
    return '"' + str(uuid.uuid5(NS, k)) + '"'


def q(s):
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'


def f(v):
    return f"{round(v, 4):g}"


placed, tracks, vias, failed = pickle.load(open(os.path.join(TOOLS, "routed.pkl"), "rb"))
assert not failed
syminfo = json.load(open(os.path.join(TOOLS, "symuuid.json")))
nets = sorted({n for c in COMPONENTS for n in c[3].values()})
nets.remove("GND"); nets = ["GND"] + nets
NET = {n: i + 1 for i, n in enumerate(nets)}


def netname(n):
    """Board net name as KiCad derives it from the schematic: local labels on the root sheet get a "/" prefix."""
    return "/" + n

def arc_pts(c, s, ang):
    def rot(p, a):
        a = math.radians(a)
        dx, dy = p[0] - c[0], p[1] - c[1]
        return (c[0] + dx * math.cos(a) - dy * math.sin(a), c[1] + dx * math.sin(a) + dy * math.cos(a))
    return s, rot(s, ang / 2), rot(s, ang)


def gfx_items(fp, side, rot, key):
    out = []
    my = (lambda y: -y) if side == "B" else (lambda y: y)
    for i, (kind, layer, d, w) in enumerate(fp.gfx):
        L = flip_layer(layer) if side == "B" else layer
        st = f"(stroke (width {f(w)}) (type solid))"
        if kind == "fp_line":
            out.append(f"(fp_line (start {f(d[0])} {f(my(d[1]))}) (end {f(d[2])} {f(my(d[3]))}) {st} (layer {q(L)}) (uuid {U(*key, "gfx", i)}))")
        elif kind == "fp_circle":
            out.append(f"(fp_circle (center {f(d[0])} {f(my(d[1]))}) (end {f(d[2])} {f(my(d[3]))}) {st} (fill none) (layer {q(L)}) (uuid {U(*key, "gfx", i)}))")
        else:
            s, m, e = arc_pts((d[0], d[1]), (d[2], d[3]), d[4])
            out.append(f"(fp_arc (start {f(s[0])} {f(my(s[1]))}) (mid {f(m[0])} {f(my(m[1]))}) (end {f(e[0])} {f(my(e[1]))}) {st} (layer {q(L)}) (uuid {U(*key, "gfx", i)}))")
    return out


def pad_layers(p, side):
    if p.typ == "thru_hole":
        return '"*.Cu" "*.Mask"'
    ls = [l for l in p.layers if l.startswith("F.")]
    return " ".join(q(flip_layer(l) if side == "B" else l) for l in ls)


# ---------------------------------------------------------------- silkscreen labels
TEXT, STROKE = 1.0, 0.15  # label size: JLCPCB's minimum for legible silkscreen
CHAR_W = 0.85             # character advance of KiCad's stroke font, in text heights (on the generous side)
PAD_GAP, SILK_GAP, EDGE_GAP = 0.2, 0.15, 0.5
BOARD_TEXTS = [("VENTA OD", 108, 112.2, 1.2, 0.2, "B"), ("VENTA OD  125B", 100, 113, 0.8, 0.15, "F")]
LABELS = {}  # filled by place_labels() in main()


def text_box(s, x, y, h=TEXT, t=STROKE):
    w, hh = len(s) * CHAR_W * h + t, h + t
    return (x - w / 2, y - hh / 2, x + w / 2, y + hh / 2)


def grow(r, d):
    return (r[0] - d, r[1] - d, r[2] + d, r[3] + d)


def boxes_overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def seg_hits_box(x1, y1, x2, y2, r):
    """Liang-Barsky: does the segment cross the box?"""
    t0, t1, dx, dy = 0.0, 1.0, x2 - x1, y2 - y1
    for p, q_ in ((-dx, x1 - r[0]), (dx, r[2] - x1), (-dy, y1 - r[1]), (dy, r[3] - y1)):
        if p == 0:
            if q_ < 0:
                return False
        else:
            t = q_ / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return True


def silk_obstacles():
    """Per board side: pad boxes, silkscreen segments (x1, y1, x2, y2, width) and board text boxes."""
    pads = {"F": [], "B": []}
    segs = {"F": [], "B": []}
    texts = {"F": [], "B": []}
    for ref, (x, y, rot) in placed.items():
        side = COMP[ref][5]
        fp = get_fp(COMP[ref][4])
        for p in fp.pads:
            gx, gy = to_global(p.x, p.y, x, y, rot, side)
            box = (gx - p.w / 2, gy - p.h / 2, gx + p.w / 2, gy + p.h / 2)
            for s_ in ("F", "B") if p.typ == "thru_hole" else (side,):
                pads[s_].append(box)
        for kind, layer, d, w in fp.gfx:
            if not layer.endswith("SilkS"):
                continue
            s_ = layer[0] if side == "F" else flip_layer(layer)[0]
            if kind == "fp_line":
                pts = [(d[0], d[1]), (d[2], d[3])]
            elif kind == "fp_circle":
                r = math.dist(d[:2], d[2:4])
                pts = [(d[0] + r * math.cos(a * math.pi / 8), d[1] + r * math.sin(a * math.pi / 8)) for a in range(17)]
            else:
                continue
            g = [to_global(px, py, x, y, rot, side) for px, py in pts]
            segs[s_] += [(a[0], a[1], b[0], b[1], w) for a, b in zip(g, g[1:])]
    for txt, x, y, h, t, s_ in BOARD_TEXTS:
        texts[s_].append(text_box(txt, x, y, h, t))
    return pads, segs, texts


def place_labels():
    """Global positions of the silkscreen labels {(ref, field): (x, y)}: each label goes to the first spot
    around its footprint that clears pads, silkscreen, other labels and the board edge."""
    pads, segs, texts = silk_obstacles()
    x0, y0, x1, y1 = BOARD
    inside = (x0 + EDGE_GAP, y0 + EDGE_GAP, x1 - EDGE_GAP, y1 - EDGE_GAP)
    out = {}

    def conflicts(box, side):
        if not (box[0] >= inside[0] and box[1] >= inside[1] and box[2] <= inside[2] and box[3] <= inside[3]):
            return 100
        n = sum(boxes_overlap(grow(box, PAD_GAP), b) for b in pads[side])
        n += sum(seg_hits_box(*sg[:4], grow(box, SILK_GAP + sg[4] / 2)) for sg in segs[side])
        n += sum(boxes_overlap(grow(box, SILK_GAP), b) for b in texts[side])
        return n

    for ref in sorted(placed, key=ref_key):
        kind, _, val, pins, fpname, side, lcsc, note = COMP[ref]
        x, y, rot = placed[ref]
        fp = get_fp(fpname)
        fields = [("Reference", ref, fp.ref_at)]
        if kind in ("POT", "POT2", "PAD"):  # their value is on the silkscreen too
            fields.append(("Value", val, fp.val_at))
        cx0, cy0, cx1, cy1 = courtyard(ref, x, y, rot)
        for field, txt, local in fields:
            w, h = (lambda b: (b[2] - b[0], b[3] - b[1]))(text_box(txt, 0, 0))
            if kind in ("POT", "POT2"):  # inside the body outline, as drawn in the footprint
                cands = [to_global(local[0], local[1], x, y, rot, side)]
            else:
                g = 0.25
                above, below = cy0 - g - h / 2, cy1 + g + h / 2
                left, right = cx0 - g - w / 2, cx1 + g + w / 2
                cands = [(x, above), (x, below), (left, y), (right, y),
                         (x - w / 2, above), (x + w / 2, above), (x - w / 2, below), (x + w / 2, below),
                         (left, y - h), (left, y + h), (right, y - h), (right, y + h),
                         (x, above - h), (x, below + h)]
            best = min(cands, key=lambda c: conflicts(text_box(txt, *c), side))  # first of the least conflicting
            out[(ref, field)] = best
            texts[side].append(text_box(txt, *best))
    return out


def ref_key(r):
    return r[0], int("".join(ch for ch in r if ch.isdigit()) or 0)


def label_at(ref, field, x, y, rot):
    """Label position in the footprint's file coordinates (relative, unrotated), upright on the board."""
    gx, gy = LABELS[(ref, field)]
    dx, dy = gx - x, gy - y
    if rot == 180:
        dx, dy = -dx, -dy
    return f"(at {f(dx)} {f(dy)} 0)"


# items of a library footprint that footprint() writes itself
LIB_SKIP = {"version", "generator", "generator_version", "layer", "property"}
COORDS = {"at", "start", "mid", "end", "center", "xy"}
ANGLED = {"pad", "fp_text"}  # their (at x y angle) holds the absolute orientation on the board


def lib_item(item, side, rot, key, pad_net=None):
    """One item of a library footprint (fp.raw) as KiCad stores it on the board: footprint-local coordinates,
    mirrored in Y with F/B layers swapped on the bottom side, absolute pad/text angles, UUIDs from key."""
    item = copy.deepcopy(item)
    bottom = side == "B"
    n = [0]

    def walk(node, parent):
        head = node[0]
        if head in COORDS and bottom:  # negate the text, not a float: library values can have more digits than f()
            y = node[2]
            node[2] = y[1:] if y.startswith("-") else y if float(y) == 0 else "-" + y
        if head == "at" and parent in ANGLED:
            a = float(node[3]) if len(node) > 3 else 0.0
            a = ((-a if bottom else a) + rot) % 360
            del node[3:]
            if a:
                node.append(f(a))
        if head in ("layer", "layers") and bottom:
            node[1:] = [q(flip_layer(t.strip('"'))) for t in node[1:]]
        if head == "uuid":
            n[0] += 1
            node[1] = U(*key, n[0])
        if head == "effects" and bottom:
            j = next((c for c in node if isinstance(c, list) and c[0] == "justify"), None)
            if j is None:
                node.append(["justify", "mirror"])
            elif "mirror" not in j:
                j.append("mirror")
        for c in node[1:]:
            if isinstance(c, list):
                walk(c, head)

    walk(item, None)
    if item[0] == "pad" and pad_net:
        item.extend(pad_net)
    # some library items have no UUID; KiCad would add a random one on every upgrade
    if item[0] in ("pad", "point") or item[0].startswith("fp_"):
        if not any(isinstance(c, list) and c[0] == "uuid" for c in item):
            item.append(["uuid", U(*key)])
    return dump(item)


def footprint(ref, x, y, rot):
    kind, _, val, pins, fpname, side, lcsc, note = COMP[ref]
    fp = get_fp(fpname)
    mir = " (justify mirror)" if side == "B" else ""
    my = (lambda v: -v) if side == "B" else (lambda v: v)
    sl = "B" if side == "B" else "F"
    o = [f"(footprint {q(fpname)} (layer {q(sl + '.Cu')}) (uuid {U(ref)}) (at {f(x)} {f(y)} {rot})"]
    fs = f"(font (size {f(TEXT)} {f(TEXT)}) (thickness {f(STROKE)}))"
    o.append(f'(property "Reference" {q(ref)} {label_at(ref, "Reference", x, y, rot)} (layer {q(sl + ".SilkS")}) (uuid {U(ref, "Reference")}) (effects {fs}{mir}))')
    if (ref, "Value") in LABELS:
        vat, vlayer = label_at(ref, "Value", x, y, rot), sl + ".SilkS"
    else:  # value on the fab layer, where the library footprint has it
        vx, vy = fp.val_at
        vat, vlayer = f"(at {f(vx)} {f(my(vy))} {rot})", sl + ".Fab"
    o.append(f'(property "Value" {q(val)} {vat} (layer {q(vlayer)}) (uuid {U(ref, "Value")}) (effects {fs}{mir}))')
    # the footprint carries the same fields as its symbol, otherwise KiCad's schematic parity check complains
    fields = [("Footprint", fpname), ("Datasheet", ""), ("Description", ""), ("LCSC", lcsc), ("Note", note)]
    fields += list(sim_fields(kind, ref, val).items())
    for k, v in fields:
        if k in ("LCSC", "Note") and not v:  # the schematic symbol has these fields only when set
            continue
        o.append(f'(property {q(k)} {q(v)} (at 0 0 {rot}) (layer {q(sl + ".Fab")}) (hide yes) (uuid {U(ref, k)}) (effects (font (size 1 1) (thickness 0.15)){mir}))')
    units = syminfo["sym"].get(ref, {})
    if units:
        first = units[sorted(units, key=int)[0]]
        o.append(f'(path "/{first}")')
        o.append('(sheetname "Root") (sheetfile "venta_overdrive.kicad_sch")')
    def pad_net(num):
        net = pins["K" if num == "1" else "A"] if kind in ("D", "DS") else pins.get(num)
        extra = [["net", str(NET[net]), q(netname(net))]] if net else []
        # op-amp GND pins: only one thermal spoke fits between the 1.27 mm pitch pins, so connect them solid
        if kind == "OPAMP2" and net == "GND":
            extra.append(["zone_connect", "2"])
        return net, extra

    if fp.raw:
        # library footprint: copy it whole (graphics, pads, 3D model, attributes) so it matches the library
        for i, item in enumerate(fp.raw[2:]):
            if isinstance(item, list) and item[0] not in LIB_SKIP:
                o.append(lib_item(item, side, rot, (ref, i), pad_net(item[1].strip('"'))[1] if item[0] == "pad" else None))
        o.append(")")
        return "\n  ".join(o)
    o.append(f"(attr {'smd' if fp.attr == 'smd' else 'through_hole'})")
    o += gfx_items(fp, side, rot, (ref,))
    for p in fp.pads:
        net, extra = pad_net(p.num)
        drill = f" (drill {f(p.drill)})" if p.drill else ""
        rr = f" (roundrect_rratio {f(p.rratio)})" if p.rratio else ""
        o.append(f"(pad {q(p.num)} {p.typ} {p.shape} (at {f(p.x)} {f(my(p.y))} {rot}) (size {f(p.w)} {f(p.h)}){drill} "
                 f"(layers {pad_layers(p, side)}){rr}{''.join(' ' + dump(e) for e in extra)} (uuid {U(ref, 'pad', p.num)}))")
    o.append(")")
    return "\n  ".join(o)


def zone(net, layer, pts):
    return (f'(zone (net {NET[net]}) (net_name {q(netname(net))}) (layer {q(layer)}) (uuid {U('zone', layer)}) (name "GND_{layer[0]}") (hatch edge 0.5) '
            f'(priority 0) (connect_pads (clearance 0.3)) (min_thickness 0.25) (filled_areas_thickness no) '
            f'(fill yes (thermal_gap 0.4) (thermal_bridge_width 0.4) (island_removal_mode 0)) '
            f'(polygon (pts ' + " ".join(f"(xy {f(x)} {f(y)})" for x, y in pts) + ")))")


def main():
    x0, y0, x1, y1 = BOARD
    L = ['(kicad_pcb (version 20240108) (generator "pcbnew") (generator_version "8.0")',
         '(general (thickness 1.6) (legacy_teardrops no))', '(paper "A4")',
         '(title_block (title "Venta Overdrive") (date "2026-10-03") (rev "1") (comment 1 "Hammond 1590N1 / 125B, pots Alpha 16 mm right-angle PCB mount") (comment 2 "SMD on bottom (JLCPCB assembly), pots and wire pads hand-soldered") (comment 3 "Board 12 mm behind the pot mounting surface (inside of the lid)"))',
         '(layers (0 "F.Cu" signal) (31 "B.Cu" signal) (32 "B.Adhes" user "B.Adhesive") (33 "F.Adhes" user "F.Adhesive") '
         '(34 "B.Paste" user) (35 "F.Paste" user) (36 "B.SilkS" user "B.Silkscreen") (37 "F.SilkS" user "F.Silkscreen") '
         '(38 "B.Mask" user) (39 "F.Mask" user) (40 "Dwgs.User" user "User.Drawings") (41 "Cmts.User" user "User.Comments") '
         '(42 "Eco1.User" user "User.Eco1") (43 "Eco2.User" user "User.Eco2") (44 "Edge.Cuts" user) (45 "Margin" user) '
         '(46 "B.CrtYd" user "B.Courtyard") (47 "F.CrtYd" user "F.Courtyard") (48 "B.Fab" user) (49 "F.Fab" user))',
         '(setup (pad_to_mask_clearance 0) (allow_soldermask_bridges_in_footprints no) (aux_axis_origin 75 114) (grid_origin 75 114))',
         '(net 0 "")']
    L += [f"(net {i} {q(netname(n))})" for n, i in NET.items()]
    LABELS.update(place_labels())
    for ref in sorted(placed, key=ref_key):
        x, y, r = placed[ref]
        L.append(footprint(ref, x, y, r))
    # outline, rounded 1 mm corners
    rr = 1.0
    st = '(stroke (width 0.1) (type default))'
    L.append(f'(gr_line (start {f(x0 + rr)} {f(y0)}) (end {f(x1 - rr)} {f(y0)}) {st} (layer "Edge.Cuts") (uuid {U("edge", "top")}))')
    L.append(f'(gr_line (start {f(x1)} {f(y0 + rr)}) (end {f(x1)} {f(y1 - rr)}) {st} (layer "Edge.Cuts") (uuid {U("edge", "right")}))')
    L.append(f'(gr_line (start {f(x1 - rr)} {f(y1)}) (end {f(x0 + rr)} {f(y1)}) {st} (layer "Edge.Cuts") (uuid {U("edge", "bottom")}))')
    L.append(f'(gr_line (start {f(x0)} {f(y1 - rr)}) (end {f(x0)} {f(y0 + rr)}) {st} (layer "Edge.Cuts") (uuid {U("edge", "left")}))')
    k = 1 - 1 / math.sqrt(2)
    for corner, (cx, cy, sx, sy, ex, ey, mx, my) in enumerate([
        (x0 + rr, y0 + rr, x0, y0 + rr, x0 + rr, y0, x0 + rr * k, y0 + rr * k),
        (x1 - rr, y0 + rr, x1 - rr, y0, x1, y0 + rr, x1 - rr * k, y0 + rr * k),
        (x1 - rr, y1 - rr, x1, y1 - rr, x1 - rr, y1, x1 - rr * k, y1 - rr * k),
        (x0 + rr, y1 - rr, x0 + rr, y1, x0, y1 - rr, x0 + rr * k, y1 - rr * k)]):
        L.append(f'(gr_arc (start {f(sx)} {f(sy)}) (mid {f(mx)} {f(my)}) (end {f(ex)} {f(ey)}) {st} (layer "Edge.Cuts") (uuid {U("edge", "corner", corner)}))')
    # helper drawings: enclosure inner face outline + shaft hole marks (User.Drawings), for the drill template
    L.append(f'(gr_rect (start 68.2 40.35) (end 131.8 159.65) (stroke (width 0.15) (type dash)) (fill none) (layer "Dwgs.User") (uuid {U("lid face")}))')
    for ref, (sx, sy) in SHAFTS.items():
        L.append(f'(gr_circle (center {f(sx)} {f(sy)}) (end {f(sx + 3.75)} {f(sy)}) (stroke (width 0.1) (type default)) (fill none) (layer "Dwgs.User") (uuid {U("shaft", ref)}))')
    # silkscreen titles
    for txt, tx, ty, h, t, side in BOARD_TEXTS:
        mir = " (justify mirror)" if side == "B" else ""
        L.append(f'(gr_text {q(txt)} (at {f(tx)} {f(ty)} 0) (layer "{side}.SilkS") (uuid {U("text", side, txt)}) '
                 f'(effects (font (size {f(h)} {f(h)}) (thickness {f(t)})){mir}))')
    # tracks / vias
    for layer, net, pts in tracks:
        for a, b in zip(pts, pts[1:]):
            L.append(f"(segment (start {f(a[0])} {f(a[1])}) (end {f(b[0])} {f(b[1])}) (width {f(TRACK)}) (layer {q(layer)}) (net {NET[net]}) (uuid {U('segment', layer, f(a[0]), f(a[1]), f(b[0]), f(b[1]))}))")
    for x, y, net in vias:
        L.append(f'(via (at {f(x)} {f(y)}) (size {f(VIA_D)}) (drill {f(VIA_DRILL)}) (layers "F.Cu" "B.Cu") (net {NET[net]}) (uuid {U("via", f(x), f(y))}))')
    zp = [(x0 + 0.5, y0 + 0.5), (x1 - 0.5, y0 + 0.5), (x1 - 0.5, y1 - 0.5), (x0 + 0.5, y1 - 0.5)]
    L.append(zone("GND", "F.Cu", zp))
    L.append(zone("GND", "B.Cu", zp))
    L.append(")")
    txt = "\n".join(L) + "\n"
    d = 0
    for ch in txt:
        d += ch == "("; d -= ch == ")"
        assert d >= 0
    assert d == 0
    open(f"{OUT}/venta_overdrive.kicad_pcb", "w", newline="\n").write(txt)
    # project footprint library
    os.makedirs(f"{OUT}/Venta.pretty", exist_ok=True)
    for name in ("Venta:Pot_Alpha_16mm_RA_Single", "Venta:Pot_Alpha_16mm_RA_Dual", "Venta:WirePad"):
        fp = get_fp(name)
        o = [f'(footprint {q(name.split(":")[1])} (version 20240108) (generator "pcbnew") (generator_version "8.0") (layer "F.Cu")',
             f'(property "Reference" "REF**" (at {f(fp.ref_at[0])} {f(fp.ref_at[1])} 0) (layer "F.SilkS") (uuid {U(name, "Reference")}) (effects (font (size 1 1) (thickness 0.15))))',
             f'(property "Value" {q(name.split(":")[1])} (at {f(fp.val_at[0])} {f(fp.val_at[1])} 0) (layer "F.Fab") (uuid {U(name, "Value")}) (effects (font (size 1 1) (thickness 0.15))))']
        # KiCad 10 adds these on upgrade with random UUIDs; write them with stable ones
        for prop in ("Datasheet", "Description"):
            o.append(f'(property {q(prop)} "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid {U(name, prop)}) '
                     f'(effects (font (size 1.27 1.27))))')
        o.append('(attr through_hole)')
        o += gfx_items(fp, "F", 0, (name,))
        for p in fp.pads:
            o.append(f'(pad {q(p.num)} thru_hole {p.shape} (at {f(p.x)} {f(p.y)}) (size {f(p.w)} {f(p.h)}) (drill {f(p.drill)}) (layers "*.Cu" "*.Mask") (uuid {U(name, "pad", p.num)}))')
        o.append(")")
        open(f"{OUT}/Venta.pretty/{name.split(':')[1]}.kicad_mod", "w", newline="\n").write("\n  ".join(o) + "\n")
    upgrade("pcb", f"{OUT}/venta_overdrive.kicad_pcb")
    upgrade("fp", f"{OUT}/Venta.pretty")
    open(f"{OUT}/fp-lib-table", "w", newline="\n").write('(fp_lib_table\n  (version 7)\n  (lib (name "Venta")(type "KiCad")(uri "${KIPRJMOD}/Venta.pretty")(options "")(descr "Venta Overdrive footprints"))\n)\n')
    print("nets", len(NET), "footprints", len(placed), "segments", sum(len(p) - 1 for _, _, p in tracks), "vias", len(vias))


main()
