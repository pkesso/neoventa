"""Simple grid router: 2 layers, 0.25 mm grid, 0.25 mm tracks, >=0.2 mm clearance, 0.6/0.3 vias."""
import heapq, math
import numpy as np
from scipy.ndimage import binary_dilation
from place import BOARD, pad_list

G = 0.25
TRACK = 0.25
VIA_D, VIA_DRILL = 0.6, 0.3
LAYERS = ["F.Cu", "B.Cu"]
X0, Y0, X1, Y1 = BOARD
NX = int(round((X1 - X0) / G)) + 1
NY = int(round((Y1 - Y0) / G)) + 1


def disk(r_cells):
    R = int(math.ceil(r_cells))
    yy, xx = np.mgrid[-R:R + 1, -R:R + 1]
    return (xx * xx + yy * yy) < r_cells * r_cells


TRACK_KEEP = disk(0.45 / G)   # centre-to-centre distance that is too close: < 0.45 mm
VIA_KEEP = disk(0.70 / G)     # via (r .3) to other copper cell centre, need .3+.2+.125 ~ .625 -> use .70
EDGE_KEEP = 0.55              # mm from board edge to track centre


def cell(x, y):
    return int(round((x - X0) / G)), int(round((y - Y0) / G))


def pos(i, j):
    return X0 + i * G, Y0 + j * G


class Router:
    def __init__(self, placed):
        self.placed = placed
        self.nets = {}
        self.netid = {}
        self.occ = np.zeros((2, NX, NY), dtype=np.int32)  # 0 free, >0 net id
        self.edge = np.zeros((NX, NY), dtype=bool)
        for i in range(NX):
            for j in range(NY):
                x, y = pos(i, j)
                if x - X0 < EDGE_KEEP or X1 - x < EDGE_KEEP or y - Y0 < EDGE_KEEP or Y1 - y < EDGE_KEEP:
                    self.edge[i, j] = True
        self.pads = []
        for ref, (x, y, r) in placed.items():
            for (rf, pin, net, gx, gy, p) in pad_list(ref, x, y, r):
                if net is None:
                    continue
                nid = self.netid.setdefault(net, len(self.netid) + 1)
                layers = [0, 1] if p.typ == "thru_hole" else [1 if ref_side(placed, ref) == "B" else 0]
                cells = []
                for i in range(max(0, int((gx - p.w / 2 - X0) / G) - 1), min(NX, int((gx + p.w / 2 - X0) / G) + 2)):
                    for j in range(max(0, int((gy - p.h / 2 - Y0) / G) - 1), min(NY, int((gy + p.h / 2 - Y0) / G) + 2)):
                        cx, cy = pos(i, j)
                        if p.shape == "circle":
                            inside = math.hypot(cx - gx, cy - gy) <= p.w / 2 + 0.125
                        else:
                            inside = abs(cx - gx) <= p.w / 2 + 0.125 and abs(cy - gy) <= p.h / 2 + 0.125
                        if inside:
                            cells.append((i, j))
                for L in layers:
                    for (i, j) in cells:
                        self.occ[L, i, j] = nid
                # cells where a track may terminate: strictly inside the pad
                term = [(i, j) for (i, j) in cells
                        if (math.hypot(pos(i, j)[0] - gx, pos(i, j)[1] - gy) <= p.w / 2 - 0.1 if p.shape == "circle"
                            else abs(pos(i, j)[0] - gx) <= p.w / 2 - 0.1 and abs(pos(i, j)[1] - gy) <= p.h / 2 - 0.1)]
                if not term:
                    term = [cell(gx, gy)]
                self.pads.append(dict(ref=rf, pin=pin, net=net, nid=nid, x=gx, y=gy, layers=layers, term=term, pad=p))
                self.nets.setdefault(net, []).append(self.pads[-1])
        self.tracks = {}  # net -> list of (layer, [(i,j),...])
        self.vias = {}    # net -> list of (i,j)

    def blocked(self, nid):
        b = np.zeros((2, NX, NY), dtype=bool)
        for L in range(2):
            other = (self.occ[L] != 0) & (self.occ[L] != nid)
            b[L] = binary_dilation(other, structure=TRACK_KEEP) | self.edge
        vb = np.zeros((NX, NY), dtype=bool)
        for L in range(2):
            other = (self.occ[L] != 0) & (self.occ[L] != nid)
            vb |= binary_dilation(other, structure=VIA_KEEP)
        vb |= binary_dilation(self.edge, structure=disk(2))
        return b, vb

    def route_net(self, net, via_cost=6.0):
        pads = self.nets[net]
        if len(pads) < 2:
            return True
        nid = pads[0]["nid"]
        blk, vblk = self.blocked(nid)
        # own copper (pads + already routed) is always passable for this net
        tree = set()
        first = pads[0]
        for L in first["layers"]:
            for c in first["term"]:
                tree.add((L, c[0], c[1]))
        remaining = pads[1:]
        # order: nearest first
        while remaining:
            remaining.sort(key=lambda p: min(math.hypot(p["x"] - pos(t[1], t[2])[0], p["y"] - pos(t[1], t[2])[1]) for t in tree))
            tgt = remaining.pop(0)
            goals = {(L, c[0], c[1]) for L in tgt["layers"] for c in tgt["term"]}
            path = self.astar(tree, goals, blk, vblk, nid, via_cost)
            if path is None:
                return False
            self.commit(net, nid, path)
            tree |= set(path)
            for L in tgt["layers"]:
                for c in tgt["term"]:
                    tree.add((L, c[0], c[1]))
        return True

    def astar(self, starts, goals, blk, vblk, nid, via_cost):
        gx = np.mean([g[1] for g in goals]); gy = np.mean([g[2] for g in goals])
        h = lambda i, j: math.hypot(i - gx, j - gy) * 0.95
        openh = []
        best = {}
        prev = {}
        for s in starts:
            best[s] = 0.0
            heapq.heappush(openh, (h(s[1], s[2]), 0.0, s))
        dirs = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
        n = 0
        while openh:
            f, gcost, cur = heapq.heappop(openh)
            if gcost > best.get(cur, 1e18):
                continue
            if cur in goals:
                path = [cur]
                while path[-1] in prev:
                    path.append(prev[path[-1]])
                return path[::-1]
            n += 1
            if n > 400000:
                return None
            L, i, j = cur
            for di, dj, c in dirs:
                ni, nj = i + di, j + dj
                if not (0 <= ni < NX and 0 <= nj < NY):
                    continue
                nxt = (L, ni, nj)
                if blk[L, ni, nj] and nxt not in goals and self.occ[L, ni, nj] != nid:
                    continue
                if di and dj:  # diagonal: both orthogonal neighbours must be passable too
                    if (blk[L, ni, j] and self.occ[L, ni, j] != nid) or (blk[L, i, nj] and self.occ[L, i, nj] != nid):
                        continue
                # preferred directions: B horizontal, F vertical
                pref = 1.0
                if L == 1 and dj and not di:
                    pref = 1.25
                if L == 0 and di and not dj:
                    pref = 1.25
                ng = gcost + c * pref
                if ng < best.get(nxt, 1e18):
                    best[nxt] = ng; prev[nxt] = cur
                    heapq.heappush(openh, (ng + h(ni, nj), ng, nxt))
            # via
            if not vblk[i, j] or (self.occ[0, i, j] == nid and self.occ[1, i, j] == nid):
                nxt = (1 - L, i, j)
                if not blk[1 - L, i, j] or self.occ[1 - L, i, j] == nid or nxt in goals:
                    ng = gcost + via_cost
                    if ng < best.get(nxt, 1e18):
                        best[nxt] = ng; prev[nxt] = cur
                        heapq.heappush(openh, (ng + h(i, j), ng, nxt))
        return None

    def commit(self, net, nid, path):
        segs = self.tracks.setdefault(net, [])
        cur = [path[0]]
        for a, b in zip(path, path[1:]):
            if a[0] != b[0]:  # via
                self.vias.setdefault(net, []).append((a[1], a[2]))
                for L in range(2):
                    for di in range(-1, 2):
                        for dj in range(-1, 2):
                            if 0 <= a[1] + di < NX and 0 <= a[2] + dj < NY and di * di + dj * dj <= 2:
                                if self.occ[L, a[1] + di, a[2] + dj] == 0:
                                    self.occ[L, a[1] + di, a[2] + dj] = nid
                if len(cur) > 1:
                    segs.append((cur[0][0], [(c[1], c[2]) for c in cur]))
                cur = [b]
            else:
                cur.append(b)
        if len(cur) > 1:
            segs.append((cur[0][0], [(c[1], c[2]) for c in cur]))
        for (L, i, j) in path:
            if self.occ[L, i, j] == 0:
                self.occ[L, i, j] = nid

    def rip(self, net):
        nid = self.netid[net]
        for L in range(2):
            self.occ[L][self.occ[L] == nid] = 0
        for p in self.nets[net]:
            for L in p["layers"]:
                for c in p["term"]:
                    pass
        # re-rasterise pads of this net
        self.tracks.pop(net, None); self.vias.pop(net, None)
        self._reraster(net)

    def _reraster(self, net):
        for p in self.nets[net]:
            pd = p["pad"]
            for i in range(max(0, int((p["x"] - pd.w / 2 - X0) / G) - 1), min(NX, int((p["x"] + pd.w / 2 - X0) / G) + 2)):
                for j in range(max(0, int((p["y"] - pd.h / 2 - Y0) / G) - 1), min(NY, int((p["y"] + pd.h / 2 - Y0) / G) + 2)):
                    cx, cy = pos(i, j)
                    if pd.shape == "circle":
                        inside = math.hypot(cx - p["x"], cy - p["y"]) <= pd.w / 2 + 0.125
                    else:
                        inside = abs(cx - p["x"]) <= pd.w / 2 + 0.125 and abs(cy - p["y"]) <= pd.h / 2 + 0.125
                    if inside:
                        for L in p["layers"]:
                            self.occ[L, i, j] = p["nid"]


def ref_side(placed, ref):
    from place import COMP
    return COMP[ref][5]


def simplify(cells):
    """merge collinear runs -> list of points (mm)."""
    pts = [cells[0]]
    for k in range(1, len(cells) - 1):
        a, b, c = pts[-1], cells[k], cells[k + 1]
        d1 = (b[0] - a[0], b[1] - a[1]); d2 = (c[0] - b[0], c[1] - b[1])
        if d1[0] * d2[1] - d1[1] * d2[0] != 0 or (d1[0] * d2[0] + d1[1] * d2[1]) < 0:
            pts.append(b)
    pts.append(cells[-1])
    return [pos(i, j) for i, j in pts]


def route_all(placed, order_bias=None, verbose=True):
    R = Router(placed)
    def span(net):
        ps = R.nets[net]
        xs = [p["x"] for p in ps]; ys = [p["y"] for p in ps]
        return (max(xs) - min(xs)) + (max(ys) - min(ys))
    order = sorted(R.nets, key=lambda n: (n in ("GND", "VCC"), span(n)))
    if order_bias:
        order = [n for n in order_bias if n in R.nets] + [n for n in order if n not in order_bias]
    failed = []
    for net in order:
        ok = R.route_net(net)
        if not ok:
            R.rip(net)
            failed.append(net)
        if verbose:
            print(("ok  " if ok else "FAIL"), net, flush=True)
    return R, failed
