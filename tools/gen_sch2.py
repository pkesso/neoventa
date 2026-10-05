"""Generate the schematic + symbol library from circuit2.py, then resave them in KiCad 10 format via kicad-cli."""
import uuid, os
from circuit2 import COMPONENTS, POT_POS
from kicad_cli import upgrade
import json

PROJ = "venta_overdrive"
TOOLS = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(TOOLS)  # repository root
LIB = "Venta"
NS = uuid.UUID("8d2f6a1e-5b3c-4c8e-9a7d-2f1e0b6c4d3a")
_used = set()
SYMUUID = {}


def U(*key):
    """UUID derived from what the item is, not from where it is written. KiCad sorts items by UUID,
    so a sequential UUID would shift every later item (and reorder the whole file) on any insertion."""
    k = "/".join(map(str, key))
    assert k not in _used, f"duplicate UUID key {k}"
    _used.add(k)
    return str(uuid.uuid5(NS, k))


ROOT = str(uuid.uuid5(NS, "1"))  # the sheet UUID; venta_overdrive.kicad_pro refers to it, so it never changes
FONT = "(effects (font (size 1.27 1.27)))"
HIDE = "(effects (font (size 1.27 1.27)) (hide yes))"
STROKE = "(stroke (width 0.254) (type default))"
STROKE0 = "(stroke (width 0) (type default))"


def q(s):
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'


# ---------------------------------------------------------------------------
# Symbol library.  pins: (number, name, x, y, angle, length, etype)
# Coordinates are library coordinates (Y up), as in KiCad.
# ---------------------------------------------------------------------------
def poly(*pts, fill="none"):
    return "(polyline (pts " + " ".join(f"(xy {x} {y})" for x, y in pts) + f") {STROKE} (fill (type {fill})))"


SYMBOLS = {
    "R": dict(prefix="R", desc="Resistor", pin_names=False, units={1: dict(
        gfx=[f"(rectangle (start -1.016 -2.54) (end 1.016 2.54) {STROKE} (fill (type none)))"],
        pins=[("1", "~", 0, 3.81, 270, 1.27, "passive"), ("2", "~", 0, -3.81, 90, 1.27, "passive")])}),
    "C": dict(prefix="C", desc="Capacitor", pin_names=False, units={1: dict(
        gfx=[poly((-2.032, -0.762), (2.032, -0.762)), poly((-2.032, 0.762), (2.032, 0.762))],
        pins=[("1", "~", 0, 3.81, 270, 3.048, "passive"), ("2", "~", 0, -3.81, 90, 3.048, "passive")])}),
    "D": dict(prefix="D", desc="Diode (pin 1 = K)", pin_names=False, units={1: dict(
        gfx=[poly((-1.27, 1.27), (-1.27, -1.27)), poly((1.27, 1.27), (1.27, -1.27), (-1.27, 0), (1.27, 1.27)),
             poly((1.27, 0), (-1.27, 0))],
        pins=[("1", "K", -3.81, 0, 0, 2.54, "passive"), ("2", "A", 3.81, 0, 180, 2.54, "passive")])}),
    "D_Schottky": dict(prefix="D", desc="Schottky diode (pin 1 = K)", pin_names=False, units={1: dict(
        gfx=[poly((-1.905, 0.635), (-1.905, 1.27), (-1.27, 1.27), (-1.27, -1.27), (-0.635, -1.27), (-0.635, -0.635)),
             poly((1.27, 1.27), (1.27, -1.27), (-1.27, 0), (1.27, 1.27)), poly((1.27, 0), (-1.27, 0))],
        pins=[("1", "K", -3.81, 0, 0, 2.54, "passive"), ("2", "A", 3.81, 0, 180, 2.54, "passive")])}),
    "OPAMP_DUAL": dict(prefix="U", desc="Dual op-amp, DIP-8 (4558, 1458, 5532, TL072...)", pin_names=True, units={
        1: dict(gfx=[poly((-5.08, 5.08), (5.08, 0), (-5.08, -5.08), (-5.08, 5.08), fill="background")],
                pins=[("1", "~", 7.62, 0, 180, 2.54, "output"), ("2", "-", -7.62, -2.54, 0, 2.54, "input"),
                      ("3", "+", -7.62, 2.54, 0, 2.54, "input")]),
        2: dict(gfx=[poly((-5.08, 5.08), (5.08, 0), (-5.08, -5.08), (-5.08, 5.08), fill="background")],
                pins=[("7", "~", 7.62, 0, 180, 2.54, "output"), ("6", "-", -7.62, -2.54, 0, 2.54, "input"),
                      ("5", "+", -7.62, 2.54, 0, 2.54, "input")]),
        3: dict(gfx=[], pins=[("8", "V+", -2.54, 7.62, 270, 3.81, "passive"),
                              ("4", "V-", -2.54, -7.62, 90, 3.81, "passive")])}),
    "POT": dict(prefix="RV", desc="Potentiometer (1 = CCW, 2 = wiper, 3 = CW)", pin_names=False, units={1: dict(
        gfx=[f"(rectangle (start -1.016 -2.54) (end 1.016 2.54) {STROKE} (fill (type none)))",
             poly((2.54, 0), (1.524, 0)), poly((1.143, 0), (2.286, 0.508), (2.286, -0.508), (1.143, 0), fill="outline")],
        pins=[("1", "1", 0, 3.81, 270, 1.27, "passive"), ("2", "2", 3.81, 0, 180, 1.27, "passive"),
              ("3", "3", 0, -3.81, 90, 1.27, "passive")])}),
    "POT_DUAL": dict(prefix="RV", desc="Dual-gang potentiometer", pin_names=False, units={
        1: dict(gfx=[f"(rectangle (start -1.016 -2.54) (end 1.016 2.54) {STROKE} (fill (type none)))",
                     poly((2.54, 0), (1.524, 0)), poly((1.143, 0), (2.286, 0.508), (2.286, -0.508), (1.143, 0), fill="outline")],
                pins=[("1", "1", 0, 3.81, 270, 1.27, "passive"), ("2", "2", 3.81, 0, 180, 1.27, "passive"),
                      ("3", "3", 0, -3.81, 90, 1.27, "passive")]),
        2: dict(gfx=[f"(rectangle (start -1.016 -2.54) (end 1.016 2.54) {STROKE} (fill (type none)))",
                     poly((2.54, 0), (1.524, 0)), poly((1.143, 0), (2.286, 0.508), (2.286, -0.508), (1.143, 0), fill="outline")],
                pins=[("4", "4", 0, 3.81, 270, 1.27, "passive"), ("5", "5", 3.81, 0, 180, 1.27, "passive"),
                      ("6", "6", 0, -3.81, 90, 1.27, "passive")])}),
    "PAD": dict(prefix="J", desc="Wire solder pad", pin_names=False, units={1: dict(
        gfx=[f"(circle (center 0 0) (radius 0.762) {STROKE} (fill (type none)))"],
        pins=[("1", "~", -3.81, 0, 0, 3.048, "passive")])}),
    "VSOURCE": dict(prefix="V", desc="Simulation voltage source", pin_names=False, units={1: dict(
        gfx=[f"(circle (center 0 0) (radius 2.54) {STROKE} (fill (type background)))",
             poly((-0.635, 1.524), (0.635, 1.524)), poly((0, 2.159), (0, 0.889)), poly((-0.635, -1.524), (0.635, -1.524))],
        pins=[("1", "+", 0, 5.08, 270, 2.54, "passive"), ("2", "-", 0, -5.08, 90, 2.54, "passive")])}),
}

KIND2SYM = {"R": "R", "C": "C", "D": "D", "DS": "D_Schottky", "OPAMP2": "OPAMP_DUAL",
            "POT": "POT", "POT2": "POT_DUAL", "V": "VSOURCE", "PAD": "PAD"}


def lib_symbol(name, full):
    s = SYMBOLS[name]
    out = [f"(symbol {q(full)}"]
    if not s["pin_names"]:
        out.append("(pin_names (offset 0) (hide yes))")
    else:
        out.append("(pin_names (offset 0.254))")
    out.append("(exclude_from_sim no) (in_bom yes) (on_board yes)")
    out.append(f'(property "Reference" {q(s["prefix"])} (at 2.54 1.27 0) {FONT})')
    out.append(f'(property "Value" {q(name)} (at 2.54 -1.27 0) {FONT})')
    out.append(f'(property "Footprint" "" (at 0 0 0) {HIDE})')
    out.append(f'(property "Datasheet" "~" (at 0 0 0) {HIDE})')
    out.append(f'(property "Description" {q(s["desc"])} (at 0 0 0) {HIDE})')
    multi = len(s["units"]) > 1
    for un, u in s["units"].items():
        out.append(f'(symbol "{name}_{un if multi else 1}_1"')
        out += u["gfx"]
        for num, pname, x, y, a, l, et in u["pins"]:
            out.append(f"(pin {et} line (at {x} {y} {a}) (length {l}) (name {q(pname)} {FONT}) (number {q(num)} {FONT}))")
        out.append(")")
    out.append(")")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Simulation fields per component
# ---------------------------------------------------------------------------
def sim_fields(kind, ref, value):
    if kind == "D":
        return {"Sim.Library": "simulations/venta.lib", "Sim.Name": "D1N4148", "Sim.Device": "D", "Sim.Pins": "1=K 2=A"}
    if kind == "DS":
        return {"Sim.Library": "simulations/venta.lib", "Sim.Name": "D1N5817", "Sim.Device": "D", "Sim.Pins": "1=K 2=A"}
    if kind == "OPAMP2":
        return {"Sim.Library": "simulations/venta.lib", "Sim.Name": "DUAL_OPAMP", "Sim.Device": "SUBCKT",
                "Sim.Pins": "1=outa 2=ina_n 3=ina_p 4=vee 5=inb_p 6=inb_n 7=outb 8=vcc"}
    if kind == "POT":
        return {"Sim.Library": "simulations/venta.lib", "Sim.Name": "POT", "Sim.Device": "SUBCKT",
                "Sim.Params": f"R=50k POS={POT_POS.get(ref, 0.5)}", "Sim.Pins": "1=1 2=2 3=3"}
    if kind == "POT2":
        return {"Sim.Library": "simulations/venta.lib", "Sim.Name": "POT_DUAL", "Sim.Device": "SUBCKT",
                "Sim.Params": f"R=50k POS={POT_POS.get(ref, 0.5)}", "Sim.Pins": "1=1 2=2 3=3 4=4 5=5 6=6"}
    return {}


def kicad_value(v):
    return v


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------
GROUPS = [
    ("Power, reference voltage VREF = VCC/2, external LED pads", ["J3", "J4", "D3", "C1", "R1", "R2", "C2", "U3:1", "V2", "U1:3", "U2:3", "U3:3", "C10", "C11", "C12", "J6", "J7"]),
    ("Input: buffer (U1B) and Drive", ["V1", "J1", "R3", "C3", "R4", "U1:2", "C4", "RV1"]),
    ("Gain stage (U1A) and diode clipper", ["U1:1", "R5", "R6", "C5", "R7", "D1", "D2"]),
    ("State-variable filter (Eq, Resonance): summer U2A, integrators U2B and U3B",
     ["R8", "R9", "R10", "U2:1", "R11", "RV2", "R12", "RV3:1", "C6", "U2:2", "RV3:2", "R13", "C7", "U3:2"]),
    ("Output: Volume", ["C8", "R14", "RV4", "C9", "R15", "R16", "J2", "J5"]),
]
SIM_SOURCES = [("V", "V1", "VSIN", {"1": "IN", "2": "GND"}, "", "dc=0 ampl=0.1 f=440 ac=1", "SIN"),
               ("V", "V2", "VDC", {"1": "+9V_IN", "2": "GND"}, "", "dc=9", "DC")]

WIDTH = {"OPAMP_DUAL": 50.8, "POT": 38.1, "POT_DUAL": 38.1, "D": 38.1, "D_Schottky": 38.1, "VSOURCE": 27.94}
X0, XMAX, ROWH = 30.48, 575, 50.8
STUB = 2.54


def snap(v):
    return round(round(v / 1.27) * 1.27, 3)


def main():
    comps = {c[1]: c for c in COMPONENTS}
    for s in SIM_SOURCES:
        comps[s[1]] = s
    items, wires, labels, texts = [], [], [], []
    y = 45.72
    pin_net_check = []
    for title, refs in GROUPS:
        texts.append((title, X0 - 5.08, y - 25.4, 2.0))
        x = X0 + 10.16
        for r in refs:
            ref, unit = (r.split(":") + ["1"])[:2]
            unit = int(unit)
            c = comps[ref]
            kind = c[0]
            sname = KIND2SYM[kind]
            w = WIDTH.get(sname, 25.4)
            if sname == "OPAMP_DUAL" and unit == 3:
                w = 22.86
            if x + w > XMAX:
                x = X0 + 10.16
                y += ROWH
            cx, cy = snap(x + w / 2), snap(y)
            x += w
            items.append((c, sname, unit, cx, cy))
            for num, pname, px, py, a, l, et in SYMBOLS[sname]["units"][unit]["pins"]:
                net = c[3][num] if num in c[3] else c[3][pname]
                sx, sy = cx + px, cy - py  # lib Y-up -> schematic Y-down
                dx, dy = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}[a]  # outward, schematic coords
                ex, ey = round(sx + dx * STUB, 3), round(sy + dy * STUB, 3)
                wires.append((round(sx, 3), round(sy, 3), ex, ey))
                ang = {(-1, 0): 180, (1, 0): 0, (0, -1): 90, (0, 1): 270}[(dx, dy)]
                labels.append((net, ex, ey, ang))
                pin_net_check.append((ref, num, net))
        y += ROWH + 12.7
    texts.append(("Simulation: Inspect > Simulator; the analysis is taken from the .tran text above. Knob positions: the Sim.Params field of RV1..RV4 (POS = 0..1).", X0 - 5.08, y - 20, 1.6))
    texts.append(("V1 (100 mV, 440 Hz sine) and V2 (9 V) are for simulation only and are not on the board. J1..J7: wire pads for the jacks, the footswitch and the external LED.", X0 - 5.08, y - 15, 1.6))

    os.makedirs(OUT, exist_ok=True)
    # ---------------- schematic ----------------
    o = ['(kicad_sch (version 20231120) (generator "eeschema") (generator_version "8.0")',
         f"(uuid {q(ROOT)})", '(paper "A2")',
         '(title_block (title "Venta Overdrive (PE-12 Elektronika)") (date "2026-10-03") (rev "1")'
         ' (comment 1 "Traced from the stripboard layout; nets connect by labels")'
         ' (comment 2 "Pots and op-amps use models from simulations/venta.lib; V1/V2 are simulation-only"))',
         "(lib_symbols"]
    for sname in SYMBOLS:
        o.append(lib_symbol(sname, f"{LIB}:{sname}"))
    o.append(")")
    for x1, y1, x2, y2 in wires:
        o.append(f"(wire (pts (xy {x1} {y1}) (xy {x2} {y2})) {STROKE0} (uuid {q(U("wire", x1, y1, x2, y2))}))")
    for net, x, yy, a in labels:
        just = "left bottom" if a in (0, 90) else "right bottom"
        o.append(f"(label {q(net)} (at {x} {yy} {a}) (fields_autoplaced yes) "
                 f"(effects (font (size 1.27 1.27)) (justify {just})) (uuid {q(U("label", x, yy))}))")  # keyed by position: a new net is an edit, not a new label
    for t, x, yy, size in texts:
        o.append(f"(text {q(t)} (exclude_from_sim yes) (at {x} {yy} 0) "
                 f"(effects (font (size {size} {size}) (bold yes)) (justify left bottom)) (uuid {q(U("text", t))}))")
    o.append(f'(text ".tran 5u 60m 50m" (exclude_from_sim no) (at {X0} 30 0) '
             f'(effects (font (size 1.8 1.8)) (justify left bottom)) (uuid {q(U('text', '.tran'))}))')
    for c, sname, unit, cx, cy in items:
        kind, ref, val, pins, fp = c[0], c[1], c[2], c[3], c[4]
        SYMUUID.setdefault(ref, {})
        is_src = kind == "V"
        props = {"Reference": ref, "Value": kicad_value(val), "Footprint": fp, "Datasheet": "~"}
        if is_src:
            props.update({"Sim.Device": "V", "Sim.Type": c[6], "Sim.Params": c[5], "Sim.Pins": "1=+ 2=-"})
        else:
            props.update(sim_fields(kind, ref, val))
            if c[6]:
                props["LCSC"] = c[6]
            if c[7]:
                props["Note"] = c[7]
        excl_sim = "yes" if kind == "PAD" else "no"
        board = "no" if is_src else "yes"
        su = U("symbol", ref, unit); SYMUUID[ref][unit] = su
        o.append(f'(symbol (lib_id {q(LIB + ":" + sname)}) (at {cx} {cy} 0) (unit {unit}) '
                 f'(exclude_from_sim {excl_sim}) (in_bom {board}) (on_board {board}) (dnp no) (uuid {q(su)})')
        L, R_, C_ = "(justify left)", "(justify right)", ""
        if sname in ("R", "C"):
            pos = [(cx + 2.54, cy - 1.27, L), (cx + 2.54, cy + 1.27, L)]
        elif sname == "VSOURCE":
            pos = [(cx + 3.81, cy - 1.27, L), (cx + 3.81, cy + 1.27, L)]
        elif sname in ("POT", "POT_DUAL"):
            pos = [(cx - 2.54, cy - 1.27, R_), (cx - 2.54, cy + 1.27, R_)]
        elif sname in ("D", "D_Schottky"):
            pos = [(cx, cy - 3.81, C_), (cx, cy + 3.81, C_)]
        elif sname == "OPAMP_DUAL" and unit != 3:
            pos = [(cx, cy - 7.62, C_), (cx, cy + 7.62, C_)]
        elif sname == "OPAMP_DUAL":
            pos = [(cx, cy - 1.27, C_), (cx, cy + 1.27, C_)]
        else:  # PAD
            pos = [(cx, cy - 2.54, C_), (cx, cy + 6.35, C_)]
        for k, v in props.items():
            if k in ("Reference", "Value"):
                px, py, j = pos[0 if k == "Reference" else 1]
                eff = f"(effects (font (size 1.27 1.27)) {j})" if j else FONT
                at = f"{round(px, 3)} {round(py, 3)} 0"
            else:
                at, eff = f"{cx} {cy} 0", HIDE
            o.append(f"(property {q(k)} {q(v)} (at {at}) {eff})")
        # KiCad 10 lists the pins of all units in every unit instance: this unit's pins first, then the others
        units = SYMBOLS[sname]["units"]
        for un in [unit] + [u for u in units if u != unit]:
            for num, *_ in units[un]["pins"]:
                o.append(f"(pin {q(num)} (uuid {q(U('pin', ref, unit, num))}))")
        o.append(f'(instances (project {q(PROJ)} (path {q("/" + ROOT)} (reference {q(ref)}) (unit {unit}))))')
        o.append(")")
    o.append('(sheet_instances (path "/" (page "1")))')
    o.append(")")
    open(f"{OUT}/{PROJ}.kicad_sch", "w", newline="\n").write("\n".join(o) + "\n")

    # ---------------- symbol library + lib tables ----------------
    lib = ['(kicad_symbol_lib (version 20231120) (generator "kicad_symbol_editor") (generator_version "8.0")']
    for sname in SYMBOLS:
        lib.append(lib_symbol(sname, sname))
    lib.append(")")
    open(f"{OUT}/{LIB}.kicad_sym", "w", newline="\n").write("\n".join(lib) + "\n")
    open(f"{OUT}/sym-lib-table", "w", newline="\n").write(
        '(sym_lib_table\n  (version 7)\n  (lib (name "Venta")(type "KiCad")(uri "${KIPRJMOD}/Venta.kicad_sym")(options "")(descr "Venta Overdrive symbols"))\n)\n')
    # the project file holds settings edited in KiCad; only create a stub when it is missing
    if not os.path.exists(f"{OUT}/{PROJ}.kicad_pro"):
        open(f"{OUT}/{PROJ}.kicad_pro", "w", newline="\n").write(PRO)
    upgrade("sch", f"{OUT}/{PROJ}.kicad_sch")
    upgrade("sym", f"{OUT}/{LIB}.kicad_sym")
    return pin_net_check


PRO = """{
  "board": {"design_settings": {"defaults": {}, "rules": {}}},
  "meta": {"filename": "venta_overdrive.kicad_pro", "version": 1},
  "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
  "sheets": [["%s", "Root"]],
  "text_variables": {}
}
"""

if __name__ == "__main__":
    PRO = PRO % ROOT
    chk = main()
    json.dump({"root": ROOT, "sym": SYMUUID}, open(os.path.join(TOOLS, "symuuid.json"), "w", newline="\n"), indent=1)
    print("pins placed:", len(chk))
