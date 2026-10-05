import json, math, random
from place import COMP, FIXED, BOARD, pad_list, courtyard, auto_place
from pcb_core import get_fp, to_global
random.seed(7)
x0,y0,x1,y1 = BOARD
start = {k: tuple(v) for k, v in json.load(open("placed.json")).items()}
movable = [r for r in start if COMP[r][5] == "B"]
fixed_refs = [r for r in start if r not in movable]
# local pad offsets cache
def pads_local(ref):
    fp = get_fp(COMP[ref][4]); return fp
def bbox(ref, x, y, r): return courtyard(ref, x, y, r)
tht_boxes = []
for ref in fixed_refs:
    x,y,r = start[ref]
    for (_,_,_,gx,gy,p) in pad_list(ref,x,y,r):
        if p.typ=="thru_hole": tht_boxes.append((gx-p.w/2-0.6, gy-p.h/2-0.6, gx+p.w/2+0.6, gy+p.h/2+0.6))
def ok_box(bb, others):
    if bb[0] < x0+0.6 or bb[1] < y0+0.6 or bb[2] > x1-0.6 or bb[3] > y1-0.6: return False
    for b in others:
        if not (bb[2]+0.5 <= b[0] or b[2]+0.5 <= bb[0] or bb[3]+0.5 <= b[1] or b[3]+0.5 <= bb[1]): return False
    return True
nets = {}
def build_netpins(pl):
    d = {}
    for ref,(x,y,r) in pl.items():
        for (_,_,net,gx,gy,p) in pad_list(ref,x,y,r):
            if net: d.setdefault(net, []).append((ref,gx,gy))
    return d
def cost(pl):
    d = build_netpins(pl); c = 0
    for net, ps in d.items():
        xs=[p[1] for p in ps]; ys=[p[2] for p in ps]
        w = 0.25 if net in ("GND","VCC") else (1.5 if net in ("IN","BUF_IN","DRIVE_W","GAIN_FB","SUM","INT1_N","INT2_N") else 1.0)
        c += w*((max(xs)-min(xs)) + (max(ys)-min(ys)))
    # decoupling: cap centre close to op-amp V+ pin (pin 8); bulk cap close to D3
    pinpos = {(ref, pin): (gx, gy) for ref,(x,y,r) in pl.items() for (_,pin,_,gx,gy,p) in pad_list(ref,x,y,r)}
    for cap, u in (("C10","U1"),("C11","U2"),("C12","U3")):
        a = pl[cap]; b = pinpos[(u,"8")]
        c += 6*max(0, math.hypot(a[0]-b[0], a[1]-b[1]) - 2.5)
    a = pl["C1"]; b = pl["D3"]; c += 3*max(0, math.hypot(a[0]-b[0], a[1]-b[1]) - 5)
    return c
pl = dict(start)
boxes = {r: bbox(r,*pl[r]) for r in movable}
cur = cost(pl); best = (cur, dict(pl))
T = 20.0
N = 150000
for it in range(N):
    T = 20.0 * (0.002 ** (it / N))
    r = random.choice(movable)
    old = pl[r]
    mv = random.random()
    if mv < 0.7:
        step = max(0.5, 8 * T / 20)
        nx = round((old[0] + random.uniform(-step, step)) * 2) / 2
        ny = round((old[1] + random.uniform(-step, step)) * 2) / 2
        new = (nx, ny, old[2] if random.random() > 0.15 else 180 - old[2])
        others = [b for k,b in boxes.items() if k != r] + tht_boxes
        nb = bbox(r, *new)
        if not ok_box(nb, others): continue
        pl[r] = new
        c = cost(pl)
        if c < cur or random.random() < math.exp((cur - c) / T):
            cur = c; boxes[r] = nb
            if c < best[0]: best = (c, dict(pl))
        else:
            pl[r] = old
    else:  # swap two parts with same footprint
        r2 = random.choice([m for m in movable if COMP[m][4] == COMP[r][4] and m != r] or [r])
        if r2 == r: continue
        a, b = pl[r], pl[r2]
        pl[r], pl[r2] = b, a
        c = cost(pl)
        if c < cur or random.random() < math.exp((cur - c) / T):
            cur = c; boxes[r], boxes[r2] = bbox(r,*pl[r]), bbox(r2,*pl[r2])
            if c < best[0]: best = (c, dict(pl))
        else:
            pl[r], pl[r2] = a, b
print("start", round(cost(start),1), "best", round(best[0],1))
json.dump(best[1], open("placed2.json","w"), indent=0)
