import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, FancyBboxPatch
from place import BOARD, COMP, pad_list, courtyard, SHAFTS
def render(placed, tracks=(), vias=(), fn="placement.png", title=""):
    fig, ax = plt.subplots(figsize=(10, 11))
    x0,y0,x1,y1 = BOARD
    ax.add_patch(Rectangle((68.2, 40.35), 63.6, 119.3, fill=False, ec="#999", ls="--", lw=1))
    ax.add_patch(Rectangle((x0,y0), x1-x0, y1-y0, fc="#1d5e3a", ec="k", alpha=.25))
    for ref,(sx,sy) in SHAFTS.items():
        ax.add_patch(Circle((sx,sy), 8.25, fill=False, ec="#c80", lw=1, ls=":"))
    for t in tracks:
        (layer, net, pts) = t
        xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
        ax.plot(xs, ys, color="#c33" if layer=="F.Cu" else "#36c", lw=1.4, alpha=.85, solid_capstyle="round")
    for (x,y,net) in vias: ax.add_patch(Circle((x,y),0.3,fc="#ccc",ec="k",lw=.4))
    for ref,(x,y,r) in placed.items():
        side = COMP[ref][5]
        bb = courtyard(ref,x,y,r)
        if side=="B": ax.add_patch(Rectangle((bb[0],bb[1]),bb[2]-bb[0],bb[3]-bb[1],fill=False,ec="#36c",lw=.6))
        for (_,pin,net,gx,gy,p) in pad_list(ref,x,y,r):
            col = "#d4a017" if p.typ=="thru_hole" else "#5b8fd4"
            ax.add_patch(Rectangle((gx-p.w/2,gy-p.h/2),p.w,p.h,fc=col,ec="k",lw=.3))
            ax.text(gx,gy,net or "",fontsize=3.2,ha="center",va="center")
        ax.text(x, bb[1]-0.4 if side=="B" else y, ref, fontsize=6, ha="center", color="#036" if side=="B" else "#840")
    ax.set_xlim(66,134); ax.set_ylim(118,56); ax.set_aspect("equal"); ax.set_title(title)
    fig.savefig(fn, dpi=140, bbox_inches="tight"); plt.close(fig)
if __name__=="__main__":
    from place import auto_place
    p = auto_place(); render(p)
    import json; json.dump(p, open("placed.json","w"), indent=0)
