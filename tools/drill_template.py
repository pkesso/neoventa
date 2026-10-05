"""Lid drilling template for the 1590N1/125B enclosure (top view), A4 PDF at 1:1 scale.
Hole positions come from place.py (enclosure centre at (100,100), y grows downwards)."""
import os
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle
from place import SHAFTS, LED_CENTRE

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "drill_template_1590N1.pdf")

PAGE_W, PAGE_H = 210.0, 297.0          # A4, mm
CX, CY = 100.0, 100.0                  # enclosure centre in board coordinates
FACE_W, FACE_H = 63.6, 119.3           # flat area of the lid
POT_D, LED_D, SW_D = 7.5, 5.5, 12.0
SW_CENTRE = (100.0, 134.0)             # 3PDT footswitch
CROSS = 2.0                            # half-length of the centre cross

HOLES = [
    (SHAFTS["RV4"], POT_D, "VOLUME"),
    (SHAFTS["RV1"], POT_D, "DRIVE"),
    (SHAFTS["RV3"], POT_D, "EQ"),
    (SHAFTS["RV2"], POT_D, "RES"),
    (LED_CENTRE, LED_D, "LED"),
    (SW_CENTRE, SW_D, "3PDT"),
]


def page(x, y):
    """Board coordinates (mm, y down) -> page coordinates (mm, y up), lid centred on the page."""
    return PAGE_W / 2 + (x - CX), PAGE_H / 2 - (y - CY)


def main():
    fig = plt.figure(figsize=(PAGE_W / 25.4, PAGE_H / 25.4))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, PAGE_W); ax.set_ylim(0, PAGE_H); ax.set_aspect("equal"); ax.axis("off")

    x0, y0 = page(CX - FACE_W / 2, CY + FACE_H / 2)
    ax.add_patch(Rectangle((x0, y0), FACE_W, FACE_H, fill=False, lw=0.8, ec="black"))

    for (x, y), d, name in HOLES:
        px, py = page(x, y)
        ax.add_patch(Circle((px, py), d / 2, fill=False, lw=0.6, ec="black"))
        ax.plot([px - CROSS, px + CROSS], [py, py], lw=0.4, color="black")
        ax.plot([px, px], [py - CROSS, py + CROSS], lw=0.4, color="black")
        ax.text(px, py - d / 2 - 1.5, f"{name}  Ø{d:g}", ha="center", va="top", fontsize=7)

    # scale check: a 50 mm bar near the top-left corner
    ax.plot([10, 60], [PAGE_H - 10, PAGE_H - 10], lw=0.8, color="#1f77b4", solid_capstyle="butt")
    ax.text(10, PAGE_H - 9, "50 mm (check 1:1 scale)", ha="left", va="bottom", fontsize=7)

    ax.text(PAGE_W / 2, PAGE_H - 25, "Venta OD — 1590N1/125B lid drilling template (top view)",
            ha="center", va="center", fontsize=10)
    ax.text(PAGE_W / 2, 22,
            "Print at 100 % (actual size). Jacks are not on the PCB: IN on the right side, OUT on the left side,\n"
            "DC on the top end, centred. Mark them on the enclosure in place.",
            ha="center", va="center", fontsize=7, linespacing=1.4)

    fig.savefig(OUT, metadata={"Title": "Venta OD drilling template 1590N1"})
    plt.close(fig)
    print("wrote", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
