"""Thin wrapper around kicad-cli. Set KICAD_CLI to override the default KiCad 10 location."""
import glob
import os
import shutil
import subprocess

KICAD_CLI = (os.environ.get("KICAD_CLI") or shutil.which("kicad-cli")
             or r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")


def to_lf(path):
    """kicad-cli writes CRLF on Windows; the repository uses LF."""
    data = open(path, "rb").read()
    if b"\r\n" in data:
        open(path, "wb").write(data.replace(b"\r\n", b"\n"))


def upgrade(kind, path):
    """Resave a KiCad file or library in the current KiCad format. kind: sch, pcb, sym or fp."""
    p = subprocess.run([KICAD_CLI, kind, "upgrade", "--force", path], capture_output=True)
    if p.returncode:
        out = (p.stdout + p.stderr).decode(errors="replace")
        raise RuntimeError(f"kicad-cli {kind} upgrade {path} failed:\n{out}")
    for f in glob.glob(os.path.join(path, "*.kicad_mod")) if os.path.isdir(path) else [path]:
        to_lf(f)
