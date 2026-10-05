"""Run a WAV file through the simulated pedal and write the output to a WAV file.

The input is a dry (DI) guitar recording. Its peak is scaled to --peak volts (guitar level) and fed to the
pedal input as an ngspice EXTERNAL source; v(out) is sampled at the file's rate and written as 16-bit PCM.

Examples:
  python simulations/render_wav.py riff.wav riff_out.wav
  python simulations/render_wav.py riff.wav riff_out.wav --drive 80 --eq 30 --res 70 --volume 60
  python simulations/render_wav.py riff.wav riff_out.wav --start 2 --duration 5 --peak 0.3 --pickup
"""
import argparse
import os
import sys
import time

import numpy as np
from scipy.io import wavfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import simulate  # noqa: E402
from kicad_cli import kicad_file  # noqa: E402

PREROLL = 0.3  # s of silence before the audio, so the coupling and reference capacitors settle
# --pickup: a typical single coil (series R and L) and the cable capacitance, between the source and the input
PICKUP = ["RPU IN_SRC PU1 6.5k", "LPU PU1 IN 2.5", "CCABLE IN 0 470p"]


def read_mono(path, start, duration):
    """Samples of the first channel as float in [-1, 1], and the sample rate."""
    fs, data = wavfile.read(path)
    if data.ndim > 1:
        data = data[:, 0]
    if data.dtype.kind == "i":
        data = data / float(np.iinfo(data.dtype).max)
    elif data.dtype.kind == "u":  # 8-bit WAV is unsigned
        data = (data.astype(float) - 128) / 128
    data = data.astype(float)
    a = int(start * fs)
    b = len(data) if duration is None else min(len(data), a + int(duration * fs))
    if a >= b:
        sys.exit(f"{path}: nothing to render between {start} s and {start + (duration or 0)} s")
    return data[a:b], fs


def deck(pos, fs, n, pickup):
    """Netlist with the input driven by the external source, through a pickup model if asked."""
    tstop = PREROLL + n / fs
    analysis = f".tran {1 / fs:.6g} {tstop:.6g} 0 {1 / fs:.6g}"  # max step = one sample
    lines = simulate.netlist(pos, analysis, "V1 IN_SRC 0 DC 0 EXTERNAL")
    extra = PICKUP if pickup else ["RSRC IN_SRC IN 1"]  # else a near-ideal source
    return lines[:-3] + extra + lines[-3:]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="dry guitar recording, WAV (first channel is used)")
    ap.add_argument("output", help="WAV file to write")
    for knob in ("drive", "eq", "res", "volume"):
        ap.add_argument(f"--{knob}", type=float, default=50, help=f"{knob} knob, 0..100 %% (default 50)")
    ap.add_argument("--peak", type=float, default=0.2, help="input peak in volts (default 0.2, a single coil)")
    ap.add_argument("--start", type=float, default=0.0, help="start of the fragment, s")
    ap.add_argument("--duration", type=float, default=None, help="length of the fragment, s (default: to the end)")
    ap.add_argument("--pickup", action="store_true", help="drive the input through a single-coil pickup and cable model")
    ap.add_argument("--gain", type=float, default=None,
                    help="output scale in dBFS per volt (0 means 1 V = full scale); default: normalise to -1 dBFS")
    args = ap.parse_args()

    for knob in ("drive", "eq", "res", "volume"):
        if not 0 <= getattr(args, knob) <= 100:
            ap.error(f"--{knob} must be within 0..100")
    pos = {"RV1": args.drive / 100, "RV3": args.eq / 100, "RV2": args.res / 100, "RV4": args.volume / 100}

    x, fs = read_mono(args.input, args.start, args.duration)
    peak = np.max(np.abs(x))
    if peak == 0:
        sys.exit(f"{args.input}: the fragment is silent")
    x = x * (args.peak / peak)
    t_in = PREROLL + np.arange(len(x)) / fs

    ng = simulate.Ngspice(kicad_file("ngspice.dll"))
    ng.external = lambda t: float(np.interp(t, t_in, x, left=0.0, right=0.0))
    print(f"{args.input}: {len(x) / fs:.2f} s at {fs} Hz, peak scaled to {args.peak} V; simulating...", flush=True)
    t0 = time.time()
    r = ng.run(deck(pos, fs, len(x), args.pickup), ["time", "out"])
    elapsed = time.time() - t0

    y = np.interp(t_in, r["time"], r["out"])
    y -= np.mean(y[: min(len(y), fs // 10)])  # remove any DC left at the start
    if args.gain is None:
        scale = 10 ** (-1 / 20) / max(np.max(np.abs(y)), 1e-9)
    else:
        scale = 10 ** (args.gain / 20)
    out = y * scale
    clipped = int(np.sum(np.abs(out) > 1))
    wavfile.write(args.output, fs, (np.clip(out, -1, 1) * 32767).astype(np.int16))
    print(f"wrote {args.output}: output peak {np.max(np.abs(y)):.3f} V, "
          f"{elapsed:.1f} s of simulation ({elapsed / (len(x) / fs):.1f}x real time)"
          + (f", {clipped} samples clipped (lower --gain)" if clipped else ""))


if __name__ == "__main__":
    main()
