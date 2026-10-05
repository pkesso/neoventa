"""Simulate the Venta Overdrive with ngspice and plot the results.

The netlist is built from tools/circuit2.py; models come from venta.lib. ngspice is used as a
shared library: the ngspice.dll in KiCad's bin directory ($KICAD_BIN, see tools/kicad_cli.py).

Outputs (next to this script):
  sim_frequency.png  small-signal frequency response vs the Eq and Resonance knobs
  sim_waveforms.png  440 Hz / 100 mV input and the output at several Drive settings
"""
import ctypes as C
import os
import sys

import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from circuit2 import COMPONENTS  # noqa: E402
from kicad_cli import kicad_file  # noqa: E402

LIB = os.path.join(HERE, "venta.lib").replace("\\", "/")

IN_AMPL, IN_FREQ = 0.1, 440.0
TRAN = ".tran 5u 60m 50m"   # same analysis as on the schematic; the last 10 ms are plotted
DEFAULT_POS = {"RV1": 0.5, "RV2": 0.5, "RV3": 0.5, "RV4": 0.5}
KNOB = {"RV1": "Drive", "RV2": "Resonance", "RV3": "Eq", "RV4": "Volume"}


# ---------------------------------------------------------------- netlist
def node(net):
    return "0" if net == "GND" else net.replace("+", "P")


def netlist(pos, analysis):
    """SPICE deck for the given pot positions {ref: 0..1} and analysis line."""
    out = ["* Venta Overdrive", f".include {LIB}"]
    for kind, ref, val, pins, *_ in COMPONENTS:
        p = {k: node(v) for k, v in pins.items()}
        if kind in ("R", "C"):
            value = val[:-1] + "Meg" if val.endswith("M") else val
            out.append(f"{ref} {p['1']} {p['2']} {value}")
        elif kind in ("D", "DS"):
            model = {"D": "D1N4148", "DS": "D1N5817"}[kind]
            out.append(f"D{ref} {p['A']} {p['K']} {model}")
        elif kind == "OPAMP2":
            out.append(f"X{ref} " + " ".join(p[str(i)] for i in range(1, 9)) + " DUAL_OPAMP")
        elif kind in ("POT", "POT2"):
            n = 3 if kind == "POT" else 6
            sub = "POT" if kind == "POT" else "POT_DUAL"
            out.append(f"X{ref} " + " ".join(p[str(i)] for i in range(1, n + 1)) + f" {sub} R=50k POS={pos[ref]}")
        elif kind == "PAD":
            continue
        else:
            raise ValueError(f"no simulation model for {ref} ({kind})")
    out += [f"V1 IN 0 DC 0 AC 1 SIN(0 {IN_AMPL} {IN_FREQ})", "V2 P9V_IN 0 DC 9", analysis, ".end"]
    return out


# ---------------------------------------------------------------- ngspice
class VecInfo(C.Structure):
    _fields_ = [("vname", C.c_char_p), ("vtype", C.c_int), ("vflags", C.c_short),
                ("vrealdata", C.POINTER(C.c_double)), ("vcompdata", C.POINTER(C.c_double)),
                ("vlength", C.c_int)]


class Ngspice:
    def __init__(self, path):
        os.add_dll_directory(os.path.dirname(path))
        self.lib = C.CDLL(path)
        self.log = []
        self._cb = (
            C.CFUNCTYPE(C.c_int, C.c_char_p, C.c_int, C.c_void_p)(self._print),
            C.CFUNCTYPE(C.c_int, C.c_char_p, C.c_int, C.c_void_p)(lambda *a: 0),
            C.CFUNCTYPE(C.c_int, C.c_int, C.c_bool, C.c_bool, C.c_int, C.c_void_p)(lambda *a: 0),
        )
        self.lib.ngSpice_Init(*self._cb, None, None, None, None)
        self.lib.ngGet_Vec_Info.restype = C.POINTER(VecInfo)

    def _print(self, s, _id, _user):
        self.log.append(s.decode(errors="replace"))
        return 0

    def run(self, lines, vectors):
        self.log.clear()
        enc = [l.encode() for l in lines] + [None]
        self.lib.ngSpice_Circ((C.c_char_p * len(enc))(*enc))
        self.lib.ngSpice_Command(b"run")
        if any("rror" in l for l in self.log):
            raise RuntimeError("\n".join(self.log))
        res = {name: self._vec(name) for name in vectors}
        self.lib.ngSpice_Command(b"remcirc")
        self.lib.ngSpice_Command(b"destroy all")
        return res

    def _vec(self, name):
        p = self.lib.ngGet_Vec_Info(name.encode())
        if not p:
            raise KeyError(name)
        v = p.contents
        if v.vcompdata:
            a = np.ctypeslib.as_array(v.vcompdata, (v.vlength * 2,))
            return a[0::2] + 1j * a[1::2]
        return np.ctypeslib.as_array(v.vrealdata, (v.vlength,)).copy()


# ---------------------------------------------------------------- plots
COLORS = ["#2a7ad5", "#e8643a", "#1aab7a"]
plt.rcParams.update({
    "figure.facecolor": "#fbfbfa", "axes.facecolor": "#fbfbfa", "savefig.facecolor": "#fbfbfa",
    "axes.edgecolor": "#cccccc", "axes.grid": True, "grid.color": "#e4e4e4", "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlesize": 11, "axes.titlelocation": "left", "axes.labelcolor": "#555555",
    "xtick.color": "#555555", "ytick.color": "#555555", "legend.frameon": False,
    "lines.linewidth": 2.0,
})


def hz(x, _):
    return f"{x / 1000:g}k" if x >= 1000 else f"{x:g}"


def frequency_plot(ng):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    for ax, ref in zip(axes, ("RV3", "RV2")):
        for pos, color in zip((0.0, 0.5, 1.0), COLORS):
            r = ng.run(netlist({**DEFAULT_POS, ref: pos}, ".ac dec 100 20 20k"), ["frequency", "out"])
            f = r["frequency"].real
            ax.semilogx(f, 20 * np.log10(np.abs(r["out"])), color=color, label=f"{KNOB[ref]} {pos:.0%}")
        ax.set_title(f"{KNOB[ref]} knob (others at 50%)")
        ax.set_xlabel("Frequency, Hz")
        ax.set_xticks([20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000])
        ax.xaxis.set_major_formatter(FuncFormatter(hz))
        ax.legend(loc="upper left" if ref == "RV3" else "lower left")
    axes[0].set_ylabel("Gain, input → output, dB")
    fig.suptitle("Small-signal frequency response (before clipping)", x=0.01, ha="left", fontsize=13)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "sim_frequency.png"), dpi=120)
    plt.close(fig)


def waveform_plot(ng):
    fig, (ax_in, ax_out) = plt.subplots(2, 1, figsize=(11, 7.5), sharex=True,
                                        gridspec_kw={"height_ratios": [1, 1.6]})
    for i, (pos, color) in enumerate(zip((0.1, 0.5, 1.0), COLORS)):
        r = ng.run(netlist({**DEFAULT_POS, "RV1": pos}, TRAN), ["time", "in", "out"])
        t = (r["time"] - r["time"][0]) * 1000
        if i == 0:
            ax_in.plot(t, r["in"] * 1000, color="#4a4a4a")
        ax_out.plot(t, r["out"], color=color, label=f"Drive {pos:.0%}")
    ax_in.set_title(f"Input: {IN_FREQ:g} Hz sine, {IN_AMPL * 1000:g} mV (guitar level)")
    ax_in.set_ylabel("Input, mV")
    ax_out.set_title("Output at Volume 50%, Eq 50%, Resonance 50%")
    ax_out.set_ylabel("Output, V")
    ax_out.set_xlabel("Time, ms")
    ax_out.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "sim_waveforms.png"), dpi=120)
    plt.close(fig)


def main():
    ng = Ngspice(kicad_file("ngspice.dll"))
    frequency_plot(ng)
    waveform_plot(ng)
    print("wrote sim_frequency.png, sim_waveforms.png")


if __name__ == "__main__":
    main()
