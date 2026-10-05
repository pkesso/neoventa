"""Repository checks, also used as the git pre-commit hook (.githooks/pre-commit).

Checks:
  format    KiCad files are in KiCad 10 format
  paths     no absolute paths in KiCad files and library tables
  english   no Cyrillic text in the repository's text files
  python    Python scripts compile
  erc       KiCad ERC reports no errors
  drc       KiCad DRC (zones refilled, schematic parity) reports no errors
  assembly  jlcpcb/BOM and CPL match the board: parts, values, LCSC numbers, position, side, rotation

Usage:
  python tools/check.py                run all checks
  python tools/check.py drc assembly   run selected checks
  python tools/check.py --hook         run only the checks relevant to the staged files
  python tools/check.py --strict       also fail on ERC/DRC warnings

Checks read the working tree, not the staged versions of files.
DRC/ERC items excluded in KiCad (right click > Exclude) are not reported.
"""
import argparse
import collections
import csv
import json
import os
import re
import subprocess
import sys
import tempfile

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import kicad_cli  # noqa: E402
from pcb_core import sexpr, kids, kid  # noqa: E402

PROJ = "venta_overdrive"
SCH, PCB = f"{PROJ}.kicad_sch", f"{PROJ}.kicad_pcb"
BOM, CPL = "jlcpcb/BOM_JLCPCB.csv", "jlcpcb/CPL_JLCPCB.csv"
KICAD_EXT = (".kicad_sch", ".kicad_pcb", ".kicad_sym", ".kicad_mod")
KICAD_FILES = KICAD_EXT + (".kicad_pro", "fp-lib-table", "sym-lib-table")
INPUT_ONLY = ("tools/fplib/",)  # old-format footprints read by pcb_core.py, never opened in KiCad

ABS_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]|(?<![\w}$])/(?:home|Users|tmp|mnt)/")
CYRILLIC = re.compile(f"[{chr(0x400)}-{chr(0x4FF)}]")  # written with chr() so this file passes the check
GEN_VERSION = re.compile(rb'\(generator_version "(\d+)\.')


# ---------------------------------------------------------------- helpers
def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")


def repo_files():
    """Tracked and untracked-but-not-ignored files."""
    return sorted(f for f in git("ls-files", "-co", "--exclude-standard") if f and os.path.isfile(os.path.join(ROOT, f)))


def staged_files():
    return [f for f in git("diff", "--cached", "--name-only", "--diff-filter=ACMR") if f]


def is_kicad(f):
    return f.endswith(KICAD_FILES) and not f.startswith(INPUT_ONLY)


def read_text(f):
    """File contents as text, or None for binary files."""
    data = open(os.path.join(ROOT, f), "rb").read()
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


class Result:
    def __init__(self):
        self.errors, self.warnings = [], []


# ---------------------------------------------------------------- file checks
def check_format(files):
    r = Result()
    for f in files:
        if not (f.endswith(KICAD_EXT) and is_kicad(f)):
            continue
        m = GEN_VERSION.search(open(os.path.join(ROOT, f), "rb").read(400))
        if not m or int(m.group(1)) < 10:
            got = f"KiCad {m.group(1).decode()}" if m else "no generator_version"
            r.errors.append(f"{f}: not in KiCad 10 format ({got})")
    return r


def check_paths(files):
    r = Result()
    for f in files:
        if not is_kicad(f):
            continue
        for n, line in enumerate((read_text(f) or "").splitlines(), 1):
            m = ABS_PATH.search(line)
            if m:
                r.errors.append(f"{f}:{n}: absolute path: {line.strip()[:120]}")
    return r


def check_english(files):
    r = Result()
    for f in files:
        for n, line in enumerate((read_text(f) or "").splitlines(), 1):
            if CYRILLIC.search(line):
                r.errors.append(f"{f}:{n}: non-English text: {line.strip()[:120]}")
    return r


def check_python(files):
    r = Result()
    for f in files:
        if f.endswith(".py"):
            try:
                compile(open(os.path.join(ROOT, f), "rb").read(), f, "exec")
            except SyntaxError as e:
                r.errors.append(f"{f}:{e.lineno}: {e.msg}")
    return r


# ---------------------------------------------------------------- KiCad checks
def report(r, items, strict):
    """Sort kicad-cli JSON violations into errors (listed) and warnings (counted by type)."""
    warn = collections.Counter()
    for v in items:
        where = " / ".join(i["description"] for i in v.get("items", []))
        if v["severity"] == "error" or strict:
            r.errors.append(f"{v['severity']} {v['type']}: {v['description']}: {where}")
        else:
            warn[v["type"]] += 1
    r.warnings += [f"{n} x {t}" for t, n in sorted(warn.items(), key=lambda kv: -kv[1])]


def check_erc(_files, strict):
    r = Result()
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "erc.json")
        kicad_cli.run("sch", "erc", "--format", "json", "--severity-error", "--severity-warning", "-o", out,
                      os.path.join(ROOT, SCH))
        d = json.load(open(out, encoding="utf-8"))
    report(r, [v for s in d.get("sheets", []) for v in s.get("violations", [])], strict)
    return r


def check_drc(_files, strict):
    r = Result()
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "drc.json")
        kicad_cli.run("pcb", "drc", "--format", "json", "--severity-error", "--severity-warning",
                      "--schematic-parity", "--refill-zones", "-o", out, os.path.join(ROOT, PCB))
        d = json.load(open(out, encoding="utf-8"))
    report(r, d.get("violations", []) + d.get("unconnected_items", []) + d.get("schematic_parity", []), strict)
    return r


# ---------------------------------------------------------------- assembly files
def board_parts():
    """Footprints on the board that JLCPCB assembles (those with an LCSC number)."""
    t = sexpr(open(os.path.join(ROOT, PCB), encoding="utf-8").read())
    parts = {}
    for fp in kids(t, "footprint"):
        props = {p[1]: p[2] for p in kids(fp, "property")}
        if not props.get("LCSC"):
            continue
        at = kid(fp, "at")
        parts[props["Reference"]] = dict(
            value=props.get("Value", ""), lcsc=props["LCSC"], x=float(at[1]), y=float(at[2]),
            rot=float(at[3]) if len(at) > 3 else 0.0, side={"F.Cu": "Top", "B.Cu": "Bottom"}[kid(fp, "layer")[1]])
    return parts


def mm(s):
    return float(s.strip().removesuffix("mm"))


def check_assembly(_files):
    r = Result()
    parts = board_parts()
    seen = collections.Counter()
    for row in csv.DictReader(open(os.path.join(ROOT, BOM), encoding="utf-8")):
        for ref in (x.strip() for x in row["Designator"].split(",")):
            seen[ref] += 1
            p = parts.get(ref)
            if not p:
                r.errors.append(f"{BOM}: {ref} is not an assembled part on the board")
                continue
            if row["LCSC Part #"] != p["lcsc"]:
                r.errors.append(f"{BOM}: {ref} LCSC {row['LCSC Part #']}, board has {p['lcsc']}")
            if row["Comment"] != p["value"]:
                r.errors.append(f"{BOM}: {ref} value {row['Comment']}, board has {p['value']}")
    r.errors += [f"{BOM}: {ref} listed {n} times" for ref, n in seen.items() if n > 1]
    r.errors += [f"{BOM}: {ref} is missing" for ref in parts if ref not in seen]

    seen = collections.Counter()
    for row in csv.DictReader(open(os.path.join(ROOT, CPL), encoding="utf-8")):
        ref = row["Designator"]
        seen[ref] += 1
        p = parts.get(ref)
        if not p:
            r.errors.append(f"{CPL}: {ref} is not an assembled part on the board")
            continue
        # CPL uses KiCad position-file coordinates: Y axis pointing up
        if abs(mm(row["Mid X"]) - p["x"]) > 0.001 or abs(mm(row["Mid Y"]) + p["y"]) > 0.001:
            r.errors.append(f"{CPL}: {ref} at ({row['Mid X']}, {row['Mid Y']}), board has ({p['x']}, {-p['y']})")
        if row["Layer"] != p["side"]:
            r.errors.append(f"{CPL}: {ref} on {row['Layer']}, board has {p['side']}")
        if (float(row["Rotation"]) - p["rot"]) % 360:
            r.errors.append(f"{CPL}: {ref} rotation {row['Rotation']}, board has {p['rot']:g}")
    r.errors += [f"{CPL}: {ref} listed {n} times" for ref, n in seen.items() if n > 1]
    r.errors += [f"{CPL}: {ref} is missing" for ref in parts if ref not in seen]
    return r


# ---------------------------------------------------------------- main
# name -> (function, takes strict, which changed files make it relevant)
CHECKS = {
    "format": (check_format, False, is_kicad),
    "paths": (check_paths, False, is_kicad),
    "english": (check_english, False, lambda f: True),
    "python": (check_python, False, lambda f: f.endswith(".py")),
    "erc": (check_erc, True, lambda f: f.endswith((".kicad_sch", ".kicad_sym", ".kicad_pro"))),
    "drc": (check_drc, True, lambda f: f.endswith((".kicad_pcb", ".kicad_sch", ".kicad_mod", ".kicad_pro"))),
    "assembly": (check_assembly, False, lambda f: f.endswith(".kicad_pcb") or f.startswith("jlcpcb/")),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("checks", nargs="*", help=f"checks to run (default: all): {', '.join(CHECKS)}")
    ap.add_argument("--hook", action="store_true", help="only checks relevant to the staged files")
    ap.add_argument("--strict", action="store_true", help="fail on ERC/DRC warnings too")
    args = ap.parse_args()
    unknown = [c for c in args.checks if c not in CHECKS]
    if unknown:
        ap.error(f"unknown check(s): {', '.join(unknown)}")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    names = args.checks or list(CHECKS)
    files = staged_files() if args.hook else repo_files()
    failed = False
    for name in names:
        func, takes_strict, relevant = CHECKS[name]
        targets = [f for f in files if relevant(f)]
        if args.hook and not targets:
            continue
        try:
            r = func(targets, args.strict) if takes_strict else func(targets)
        except Exception as e:  # a check that cannot run must not pass silently
            r = Result()
            r.errors.append(f"could not run: {e}")
        status = "FAIL" if r.errors else "ok"
        extra = f"  ({', '.join(r.warnings)} warnings)" if r.warnings else ""
        print(f"{name:9} {status}{extra}")
        for e in r.errors[:30]:
            print(f"    {e}")
        if len(r.errors) > 30:
            print(f"    ... and {len(r.errors) - 30} more")
        failed |= bool(r.errors)
    if failed and args.hook:
        print("\ncommit blocked by tools/check.py; fix the problems above or exclude them in KiCad")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
