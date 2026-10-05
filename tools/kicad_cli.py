"""KiCad tools: kicad-cli and ngspice, both in KiCad's bin directory (see kicad_bin())."""
import glob
import os
import shutil
import subprocess

KICAD_VERSION = "10.0"


def kicad_bin():
    """KiCad's bin directory: $KICAD_BIN if set, else the directory of kicad-cli on PATH,
    else the default Windows install, %ProgramFiles%\\KiCad\\10.0\\bin."""
    d = os.environ.get("KICAD_BIN")
    if d:
        if not os.path.isdir(d):
            raise RuntimeError(f"KICAD_BIN={d} is not a directory")
        return d
    cli = shutil.which("kicad-cli")
    if cli:
        return os.path.dirname(cli)
    if os.environ.get("ProgramFiles"):
        d = os.path.join(os.environ["ProgramFiles"], "KiCad", KICAD_VERSION, "bin")
        if os.path.isdir(d):
            return d
    raise RuntimeError(f"KiCad {KICAD_VERSION} not found: set KICAD_BIN to KiCad's bin directory")


def kicad_file(name):
    """Path of a file in KiCad's bin directory; raises if it is missing."""
    path = os.path.join(kicad_bin(), name)
    if not os.path.isfile(path):
        raise RuntimeError(f"{path} not found (check KICAD_BIN)")
    return path


def run(*args):
    """Run kicad-cli with the given arguments; raise with its output if it errors out."""
    cli = kicad_file("kicad-cli.exe" if os.name == "nt" else "kicad-cli")
    p = subprocess.run([cli, *args], capture_output=True)
    if p.returncode:
        out = (p.stdout + p.stderr).decode(errors="replace")
        raise RuntimeError(f"kicad-cli {' '.join(args)} failed:\n{out}")
    return p


def to_lf(path):
    """kicad-cli writes CRLF on Windows; the repository uses LF."""
    data = open(path, "rb").read()
    if b"\r\n" in data:
        open(path, "wb").write(data.replace(b"\r\n", b"\n"))


def upgrade(kind, path):
    """Resave a KiCad file or library in the current KiCad format. kind: sch, pcb, sym or fp."""
    run(kind, "upgrade", "--force", path)
    for f in glob.glob(os.path.join(path, "*.kicad_mod")) if os.path.isdir(path) else [path]:
        to_lf(f)
