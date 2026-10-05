"""Independent check of the generated .kicad_sch: parse it, rebuild connectivity from
geometry + labels, compare against circuit.py, emit a SPICE netlist from the schematic's
own Sim.* fields, and render a preview PNG."""
import os, re, shutil, sys, subprocess, numpy as np
from circuit2 import COMPONENTS

path = sys.argv[1]
src = open(path).read()


def parse(s):
    tok = re.findall(r'"(?:\\.|[^"\\])*"|\(|\)|[^\s()"]+', s)
    st = [[]]
    for t in tok:
        if t == "(":
            st.append([])
        elif t == ")":
            x = st.pop(); st[-1].append(x)
        elif t.startswith('"'):
            st[-1].append(t[1:-1].replace(chr(92)+chr(34), chr(34)).replace(chr(92)*2, chr(92)))
        else:
            st[-1].append(t)
    return st[0][0]


T = parse(src)
assert T[0] == "kicad_sch"
F = lambda node, key: [x for x in node if isinstance(x, list) and x and x[0] == key]
libs = {}
for sym in F(F(T, "lib_symbols")[0], "symbol"):
    name = sym[1]; units = {}; gfx = {}
    for sub in F(sym, "symbol"):
        un = int(sub[1].split("_")[-2])
        for p in F(sub, "pin"):
            at = F(p, "at")[0]; num = F(p, "number")[0][1]; ln = float(F(p, "length")[0][1])
            units.setdefault(un, []).append((num, float(at[1]), float(at[2]), int(at[3]), ln))
        for g in sub:
            if isinstance(g, list) and g[0] in ("polyline", "rectangle", "circle"):
                gfx.setdefault(un, []).append(g)
    libs[name] = (units, gfx)

parent = {}
def find(a):
    parent.setdefault(a, a)
    while parent[a] != a:
        parent[a] = parent[parent[a]]; a = parent[a]
    return a
def union(a, b): parent[find(a)] = find(b)
P = lambda x, y: ("pt", round(float(x), 2), round(float(y), 2))

wires = []
for w in F(T, "wire"):
    pts = F(w, "pts")[0][1:]
    a, b = P(pts[0][1], pts[0][2]), P(pts[1][1], pts[1][2]); union(a, b); wires.append((a, b))
labels = []
for l in F(T, "label"):
    at = F(l, "at")[0]; union(P(at[1], at[2]), ("net", l[1])); labels.append((l[1], float(at[1]), float(at[2]), int(at[3])))

placed = []  # ref, unit, pins{num:pt}, props, lib
for s in F(T, "symbol"):
    lib = F(s, "lib_id")[0][1]; at = F(s, "at")[0]; unit = int(F(s, "unit")[0][1])
    cx, cy = float(at[1]), float(at[2])
    assert int(at[3]) == 0
    props = {p[1]: p[2] for p in F(s, "property")}
    flags = {k: F(s, k)[0][1] for k in ("exclude_from_sim", "on_board")}
    pins = {num: P(cx + x, cy - y) for num, x, y, a, l in libs[lib][0][unit]}
    for pt in pins.values(): find(pt)
    placed.append((props["Reference"], unit, pins, props, lib, flags, cx, cy))

# net name per point-group
groupnet = {}
for k in list(parent):
    if k[0] == "net":
        r = find(k)
        if r in groupnet and groupnet[r] != k[1]:
            print("SHORT between", groupnet[r], k[1]); sys.exit(1)
        groupnet[r] = k[1]

got = {}
for ref, unit, pins, props, lib, flags, cx, cy in placed:
    for num, pt in pins.items():
        r = find(pt)
        if r not in groupnet:
            print("UNCONNECTED pin", ref, num); sys.exit(1)
        got[(ref, num)] = groupnet[r]

errors = 0
want = {}
for kind, ref, val, pins, fp, side, lcsc, note in COMPONENTS:
    for k, net in pins.items():
        num = {"A": "2", "K": "1"}.get(k, k)
        want[(ref, num)] = net
for key, net in want.items():
    if got.get(key) != net:
        print("MISMATCH", key, "want", net, "got", got.get(key)); errors += 1
extra = set(got) - set(want) - {("V1", "1"), ("V1", "2"), ("V2", "1"), ("V2", "2")}
if extra: print("EXTRA pins", extra); errors += 1
print("pins checked:", len(want), "errors:", errors)

# ---- SPICE netlist from the schematic's own Sim fields (as KiCad's exporter would) ----
n = lambda x: "0" if x == "GND" else x.replace("+", "P")
lines = ["* netlist rebuilt from schematic"]
libsincl = set(); seen = set()
for ref, unit, pins, props, lib, flags, cx, cy in sorted(placed, key=lambda p: p[0]):
    if flags["exclude_from_sim"] == "yes" or ref in seen: continue
    seen.add(ref)
    allpins = {}
    for r2, u2, p2, *_ in placed:
        if r2 == ref:
            for num in p2: allpins[num] = got[(ref, num)]
    dev = props.get("Sim.Device", "")
    val = props["Value"].replace("M", "Meg") if ref.startswith("R") and props["Value"].endswith("M") else props["Value"]
    if dev == "V":
        prm = dict(kv.split("=") for kv in props["Sim.Params"].split())
        spec = f"DC {prm['dc']}" if props["Sim.Type"] == "DC" else f"DC 0 AC {prm.get('ac', 0)} SIN({prm['dc']} {prm['ampl']} {prm['f']})"
        lines.append(f"{ref} {n(allpins['1'])} {n(allpins['2'])} {spec}")
    elif dev in ("SUBCKT", "D"):
        libsincl.add(props["Sim.Library"])
        order = [kv.split("=")[0] for kv in props["Sim.Pins"].split()]
        if dev == "D":
            pm = dict(kv.split("=") for kv in props["Sim.Pins"].split())
            inv = {v: k for k, v in pm.items()}
            lines.append(f"D{ref} {n(allpins[inv['A']])} {n(allpins[inv['K']])} {props['Sim.Name']}")
        else:
            lines.append(f"X{ref} " + " ".join(n(allpins[o]) for o in order) + f" {props['Sim.Name']} {props.get('Sim.Params', '')}")
    elif ref[0] in "RC":
        lines.append(f"{ref} {n(allpins['1'])} {n(allpins['2'])} {val}")
    else:
        print("no sim model for", ref); errors += 1
texts = [t[1] for t in F(T, "text") if t[1].startswith(".")]
deck = "\n".join([lines[0]] + [f".include {l}" for l in sorted(libsincl)] + lines[1:] + texts +
                 [".control", "set wr_singlescale", "set wr_vecnames", "run", "wrdata sch_res.txt v(in) v(out)", ".endc", ".end"]) + "\n"
open("from_schematic.cir", "w").write(deck)
ngspice = os.environ.get("NGSPICE") or shutil.which("ngspice") or "ngspice"
p = subprocess.run([ngspice, "-b", "from_schematic.cir"], capture_output=True, text=True)
d = np.genfromtxt("sch_res.txt", names=True)
print("schematic sim: out min/max", round(d["vout"].min(), 3), round(d["vout"].max(), 3))

# ---- preview render ----
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle
fig, ax = plt.subplots(figsize=(23.4, 16.5))
ax.set_facecolor("#fffff8")
for a, b in wires: ax.plot([a[1], b[1]], [a[2], b[2]], color="#008400", lw=1)
for name, x, y, ang in labels:
    rot = {0: 0, 90: 90, 180: 0, 270: 90}[ang]; ha = "left" if ang in (0, 90) else "right"
    if ang == 270: ha = "right"
    ax.text(x, y, name, fontsize=5.5, rotation=rot, ha=ha if ang in (0, 180) else "center",
            va="bottom" if ang in (0, 180) else ("bottom" if ang == 90 else "top"), color="#1f3a93")
for ref, unit, pins, props, lib, flags, cx, cy in placed:
    for g in libs[lib][1].get(unit, []):
        if g[0] == "polyline":
            pts = [(float(x[1]), float(x[2])) for x in F(g, "pts")[0][1:]]
            ax.plot([cx + p[0] for p in pts], [cy - p[1] for p in pts], color="#840000", lw=1)
        elif g[0] == "rectangle":
            s_, e_ = F(g, "start")[0], F(g, "end")[0]
            x0, y0, x1, y1 = float(s_[1]), float(s_[2]), float(e_[1]), float(e_[2])
            ax.add_patch(Rectangle((cx + min(x0, x1), cy - max(y0, y1)), abs(x1 - x0), abs(y1 - y0), fill=False, ec="#840000", lw=1))
        elif g[0] == "circle":
            c_ = F(g, "center")[0]; r = float(F(g, "radius")[0][1])
            ax.add_patch(Circle((cx + float(c_[1]), cy - float(c_[2])), r, fill=False, ec="#840000", lw=1))
    for num, x, y, a, l in libs[lib][0][unit]:
        dx, dy = {0: (1, 0), 180: (-1, 0), 90: (0, -1), 270: (0, 1)}[a]
        ax.plot([cx + x, cx + x + dx * l], [cy - y, cy - y + dy * l], color="#840000", lw=1)
        ax.text(cx + x + dx * l / 2, cy - y + dy * l / 2, num, fontsize=4, color="#840000")
    for p in F(next(s for s in F(T, "symbol") if F(s, "uuid")[0] and False), "x") if False else []: pass
for s in F(T, "symbol"):
    for pr in F(s, "property"):
        if pr[1] in ("Reference", "Value") and not any(isinstance(e, list) and e[0] == "effects" and F(e, "hide") for e in pr):
            at = F(pr, "at")[0]
            eff = F(pr, "effects")[0]; j = F(eff, "justify")
            ha = {"left": "left", "right": "right"}.get(j[0][1] if j else "", "center")
            ax.text(float(at[1]), float(at[2]), pr[2], fontsize=6 if pr[1] == "Reference" else 5.5, ha=ha, va="center",
                    color="#000" if pr[1] == "Reference" else "#555", weight="bold" if pr[1] == "Reference" else "normal")
for t in F(T, "text"):
    at = F(t, "at")[0]; ax.text(float(at[1]), float(at[2]), t[1], fontsize=9, weight="bold", color="#333")
ax.set_xlim(0, 594); ax.set_ylim(420, 0); ax.set_aspect("equal"); ax.axis("off")
fig.savefig("schematic_preview.png", dpi=110, bbox_inches="tight")
sys.exit(1 if errors else 0)
