"""Write venta_overdrive.kicad_pcb (KiCad 8 syntax; KiCad 10 opens and upgrades it) + project footprint lib."""
import json, math, pickle, uuid, os
from circuit2 import COMPONENTS
from place import COMP, BOARD, SHAFTS, LED_CENTRE
from pcb_core import get_fp, flip_layer, to_global
from route import TRACK, VIA_D, VIA_DRILL

OUT = "/home/claude/work/v2/venta_overdrive"
NS = uuid.UUID("3b1a7c55-0f7e-4d0c-9a43-6f1b2a9d8e10")
_n = [0]


def U():
    _n[0] += 1
    return '"' + str(uuid.uuid5(NS, str(_n[0]))) + '"'


def q(s):
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'


def f(v):
    return f"{round(v, 4):g}"


placed, tracks, vias, failed = pickle.load(open("/home/claude/work/routed.pkl", "rb"))
assert not failed
syminfo = json.load(open("/home/claude/work/v2/symuuid.json"))
nets = sorted({n for c in COMPONENTS for n in c[3].values()})
nets.remove("GND"); nets = ["GND"] + nets
NET = {n: i + 1 for i, n in enumerate(nets)}

MODEL = {
    "Resistor_SMD:R_0805_2012Metric": "Resistor_SMD.3dshapes/R_0805_2012Metric",
    "Capacitor_SMD:C_0805_2012Metric": "Capacitor_SMD.3dshapes/C_0805_2012Metric",
    "Capacitor_SMD:C_0603_1608Metric": "Capacitor_SMD.3dshapes/C_0603_1608Metric",
    "Capacitor_SMD:C_1206_3216Metric": "Capacitor_SMD.3dshapes/C_1206_3216Metric",
    "Diode_SMD:D_SMA": "Diode_SMD.3dshapes/D_SMA",
    "Diode_SMD:D_SOD-123": "Diode_SMD.3dshapes/D_SOD-123",
    "LED_THT:LED_D5.0mm": "LED_THT.3dshapes/LED_D5.0mm",
    "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm": "Package_SO.3dshapes/SOIC-8_3.9x4.9mm_P1.27mm",
}


def arc_pts(c, s, ang):
    def rot(p, a):
        a = math.radians(a)
        dx, dy = p[0] - c[0], p[1] - c[1]
        return (c[0] + dx * math.cos(a) - dy * math.sin(a), c[1] + dx * math.sin(a) + dy * math.cos(a))
    return s, rot(s, ang / 2), rot(s, ang)


def gfx_items(fp, side, rot, for_lib=False):
    out = []
    my = (lambda y: -y) if side == "B" else (lambda y: y)
    for kind, layer, d, w in fp.gfx:
        L = flip_layer(layer) if side == "B" else layer
        st = f"(stroke (width {f(w)}) (type solid))"
        if kind == "fp_line":
            out.append(f"(fp_line (start {f(d[0])} {f(my(d[1]))}) (end {f(d[2])} {f(my(d[3]))}) {st} (layer {q(L)}) (uuid {U()}))")
        elif kind == "fp_circle":
            out.append(f"(fp_circle (center {f(d[0])} {f(my(d[1]))}) (end {f(d[2])} {f(my(d[3]))}) {st} (fill none) (layer {q(L)}) (uuid {U()}))")
        else:
            s, m, e = arc_pts((d[0], d[1]), (d[2], d[3]), d[4])
            out.append(f"(fp_arc (start {f(s[0])} {f(my(s[1]))}) (mid {f(m[0])} {f(my(m[1]))}) (end {f(e[0])} {f(my(e[1]))}) {st} (layer {q(L)}) (uuid {U()}))")
    return out


def pad_layers(p, side):
    if p.typ == "thru_hole":
        return '"*.Cu" "*.Mask"'
    ls = [l for l in p.layers if l.startswith("F.")]
    return " ".join(q(flip_layer(l) if side == "B" else l) for l in ls)


def footprint(ref, x, y, rot):
    kind, _, val, pins, fpname, side, lcsc, note = COMP[ref]
    fp = get_fp(fpname)
    mir = " (justify mirror)" if side == "B" else ""
    my = (lambda v: -v) if side == "B" else (lambda v: v)
    sl = "B" if side == "B" else "F"
    o = [f"(footprint {q(fpname)} (layer {q(sl + '.Cu')}) (uuid {U()}) (at {f(x)} {f(y)} {rot})"]
    rx, ry = fp.ref_at
    big = kind in ("POT", "POT2", "PAD", "LED")
    fs = "(font (size 1 1) (thickness 0.15))" if big else "(font (size 0.7 0.7) (thickness 0.12))"
    o.append(f'(property "Reference" {q(ref)} (at {f(rx)} {f(my(ry))} {rot}) (layer {q(sl + ".SilkS")}) (uuid {U()}) (effects {fs}{mir}))')
    vx, vy = fp.val_at
    vlayer = sl + (".SilkS" if kind in ("POT", "POT2", "PAD") else ".Fab")
    o.append(f'(property "Value" {q(val)} (at {f(vx)} {f(my(vy))} {rot}) (layer {q(vlayer)}) (uuid {U()}) (effects {fs}{mir}))')
    for k, v in (("Footprint", fpname), ("Datasheet", ""), ("Description", note), ("LCSC", lcsc)):
        if k == "LCSC" and not v:
            continue
        o.append(f'(property {q(k)} {q(v)} (at 0 0 {rot}) (layer {q(sl + ".Fab")}) (hide yes) (uuid {U()}) (effects (font (size 1 1) (thickness 0.15)){mir}))')
    units = syminfo["sym"].get(ref, {})
    if units:
        first = units[sorted(units, key=int)[0]]
        o.append(f'(path "/{first}")')
        o.append('(sheetname "Root") (sheetfile "venta_overdrive.kicad_sch")')
    o.append(f"(attr {'smd' if fp.attr == 'smd' else 'through_hole'})")
    o += gfx_items(fp, side, rot)
    for p in fp.pads:
        if kind in ("D", "DS", "LED"):
            net = pins["K" if p.num == "1" else "A"]
        else:
            net = pins.get(p.num)
        netstr = f" (net {NET[net]} {q(net)})" if net else ""
        drill = f" (drill {f(p.drill)})" if p.drill else ""
        rr = f" (roundrect_rratio {f(p.rratio)})" if p.rratio else ""
        o.append(f"(pad {q(p.num)} {p.typ} {p.shape} (at {f(p.x)} {f(my(p.y))} {rot}) (size {f(p.w)} {f(p.h)}){drill} "
                 f"(layers {pad_layers(p, side)}){rr}{netstr} (uuid {U()}))")
    if fpname in MODEL:
        o.append(f'(model "${{KICAD10_3DMODEL_DIR}}/{MODEL[fpname]}.step" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))')
    o.append(")")
    return "\n  ".join(o)


def zone(net, layer, pts):
    return (f'(zone (net {NET[net]}) (net_name {q(net)}) (layer {q(layer)}) (uuid {U()}) (name "GND_{layer[0]}") (hatch edge 0.5) '
            f'(priority 0) (connect_pads (clearance 0.3)) (min_thickness 0.25) (filled_areas_thickness no) '
            f'(fill yes (thermal_gap 0.4) (thermal_bridge_width 0.4) (island_removal_mode 1) (island_area_min 4)) '
            f'(polygon (pts ' + " ".join(f"(xy {f(x)} {f(y)})" for x, y in pts) + ")))")


def main():
    x0, y0, x1, y1 = BOARD
    L = ['(kicad_pcb (version 20240108) (generator "pcbnew") (generator_version "8.0")',
         '(general (thickness 1.6) (legacy_teardrops no))', '(paper "A4")',
         '(title_block (title "Venta Overdrive") (date "2026-10-03") (rev "1") (comment 1 "Hammond 1590N1 / 125B, pots Alpha 16 mm right-angle PCB mount") (comment 2 "SMD on bottom (JLCPCB assembly), pots/LED/wire pads hand-soldered"))',
         '(layers (0 "F.Cu" signal) (31 "B.Cu" signal) (32 "B.Adhes" user "B.Adhesive") (33 "F.Adhes" user "F.Adhesive") '
         '(34 "B.Paste" user) (35 "F.Paste" user) (36 "B.SilkS" user "B.Silkscreen") (37 "F.SilkS" user "F.Silkscreen") '
         '(38 "B.Mask" user) (39 "F.Mask" user) (40 "Dwgs.User" user "User.Drawings") (41 "Cmts.User" user "User.Comments") '
         '(42 "Eco1.User" user "User.Eco1") (43 "Eco2.User" user "User.Eco2") (44 "Edge.Cuts" user) (45 "Margin" user) '
         '(46 "B.CrtYd" user "B.Courtyard") (47 "F.CrtYd" user "F.Courtyard") (48 "B.Fab" user) (49 "F.Fab" user))',
         '(setup (pad_to_mask_clearance 0) (allow_soldermask_bridges_in_footprints no) (aux_axis_origin 75 114) (grid_origin 75 114))',
         '(net 0 "")']
    L += [f"(net {i} {q(n)})" for n, i in NET.items()]
    for ref in sorted(placed, key=lambda r: (r[0], int(''.join(ch for ch in r if ch.isdigit()) or 0))):
        x, y, r = placed[ref]
        L.append(footprint(ref, x, y, r))
    # outline, rounded 1 mm corners
    rr = 1.0
    st = '(stroke (width 0.1) (type default))'
    L.append(f'(gr_line (start {f(x0 + rr)} {f(y0)}) (end {f(x1 - rr)} {f(y0)}) {st} (layer "Edge.Cuts") (uuid {U()}))')
    L.append(f'(gr_line (start {f(x1)} {f(y0 + rr)}) (end {f(x1)} {f(y1 - rr)}) {st} (layer "Edge.Cuts") (uuid {U()}))')
    L.append(f'(gr_line (start {f(x1 - rr)} {f(y1)}) (end {f(x0 + rr)} {f(y1)}) {st} (layer "Edge.Cuts") (uuid {U()}))')
    L.append(f'(gr_line (start {f(x0)} {f(y1 - rr)}) (end {f(x0)} {f(y0 + rr)}) {st} (layer "Edge.Cuts") (uuid {U()}))')
    k = 1 - 1 / math.sqrt(2)
    for (cx, cy, sx, sy, ex, ey, mx, my) in [
        (x0 + rr, y0 + rr, x0, y0 + rr, x0 + rr, y0, x0 + rr * k, y0 + rr * k),
        (x1 - rr, y0 + rr, x1 - rr, y0, x1, y0 + rr, x1 - rr * k, y0 + rr * k),
        (x1 - rr, y1 - rr, x1, y1 - rr, x1 - rr, y1, x1 - rr * k, y1 - rr * k),
        (x0 + rr, y1 - rr, x0 + rr, y1, x0, y1 - rr, x0 + rr * k, y1 - rr * k)]:
        L.append(f'(gr_arc (start {f(sx)} {f(sy)}) (mid {f(mx)} {f(my)}) (end {f(ex)} {f(ey)}) {st} (layer "Edge.Cuts") (uuid {U()}))')
    # helper drawings: enclosure inner face outline + shaft/LED hole marks (User.Drawings), for the drill template
    L.append(f'(gr_rect (start 68.2 40.35) (end 131.8 159.65) (stroke (width 0.15) (type dash)) (fill none) (layer "Dwgs.User") (uuid {U()}))')
    for ref, (sx, sy) in SHAFTS.items():
        L.append(f'(gr_circle (center {f(sx)} {f(sy)}) (end {f(sx + 3.75)} {f(sy)}) (stroke (width 0.1) (type default)) (fill none) (layer "Dwgs.User") (uuid {U()}))')
    L.append(f'(gr_circle (center {f(LED_CENTRE[0])} {f(LED_CENTRE[1])}) (end {f(LED_CENTRE[0] + 2.6)} {f(LED_CENTRE[1])}) (stroke (width 0.1) (type default)) (fill none) (layer "Dwgs.User") (uuid {U()}))')
    # silkscreen titles
    L.append(f'(gr_text "VENTA OD" (at 100 112.2 0) (layer "B.SilkS") (uuid {U()}) (effects (font (size 1.2 1.2) (thickness 0.2)) (justify mirror)))')
    L.append(f'(gr_text "VENTA OD  125B" (at 100 113 0) (layer "F.SilkS") (uuid {U()}) (effects (font (size 0.8 0.8) (thickness 0.15))))')
    # tracks / vias
    for layer, net, pts in tracks:
        for a, b in zip(pts, pts[1:]):
            L.append(f"(segment (start {f(a[0])} {f(a[1])}) (end {f(b[0])} {f(b[1])}) (width {f(TRACK)}) (layer {q(layer)}) (net {NET[net]}) (uuid {U()}))")
    for x, y, net in vias:
        L.append(f'(via (at {f(x)} {f(y)}) (size {f(VIA_D)}) (drill {f(VIA_DRILL)}) (layers "F.Cu" "B.Cu") (net {NET[net]}) (uuid {U()}))')
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
    open(f"{OUT}/venta_overdrive.kicad_pcb", "w").write(txt)
    # project footprint library
    os.makedirs(f"{OUT}/Venta.pretty", exist_ok=True)
    for name in ("Venta:Pot_Alpha_16mm_RA_Single", "Venta:Pot_Alpha_16mm_RA_Dual", "Venta:WirePad"):
        fp = get_fp(name)
        o = [f'(footprint {q(name.split(":")[1])} (version 20240108) (generator "pcbnew") (generator_version "8.0") (layer "F.Cu")',
             f'(property "Reference" "REF**" (at {f(fp.ref_at[0])} {f(fp.ref_at[1])} 0) (layer "F.SilkS") (uuid {U()}) (effects (font (size 1 1) (thickness 0.15))))',
             f'(property "Value" {q(name.split(":")[1])} (at {f(fp.val_at[0])} {f(fp.val_at[1])} 0) (layer "F.Fab") (uuid {U()}) (effects (font (size 1 1) (thickness 0.15))))',
             f'(attr through_hole)']
        o += gfx_items(fp, "F", 0)
        for p in fp.pads:
            o.append(f'(pad {q(p.num)} thru_hole {p.shape} (at {f(p.x)} {f(p.y)}) (size {f(p.w)} {f(p.h)}) (drill {f(p.drill)}) (layers "*.Cu" "*.Mask") (uuid {U()}))')
        o.append(")")
        open(f"{OUT}/Venta.pretty/{name.split(':')[1]}.kicad_mod", "w").write("\n  ".join(o) + "\n")
    open(f"{OUT}/fp-lib-table", "w").write('(fp_lib_table\n  (version 7)\n  (lib (name "Venta")(type "KiCad")(uri "${KIPRJMOD}/Venta.pretty")(options "")(descr "Venta Overdrive footprints"))\n)\n')
    print("nets", len(NET), "footprints", len(placed), "segments", sum(len(p) - 1 for _, _, p in tracks), "vias", len(vias))


main()
