"""Git as a differential oracle. Everything here degrades to "unavailable"
rather than failing when git is missing."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

GIT = shutil.which("git")


def git_available() -> bool:
    return GIT is not None


def _write(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    assert GIT
    return subprocess.run([GIT, "-c", "core.autocrlf=false", *args], cwd=cwd, capture_output=True, timeout=180)


def git_merge(base: str, ours: str, theirs: str, *, diff3: bool = False) -> tuple[str, int]:
    """``git merge-file -p``: (merged text, number of conflicts). Raises on
    a git error (exit code < 0 / 255)."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _write(d / "ours", ours)
        _write(d / "base", base)
        _write(d / "theirs", theirs)
        args = ["merge-file", "-p", "-L", "ours", "-L", "base", "-L", "theirs"]
        if diff3:
            args.append("--diff3")
        r = _run(args + ["ours", "base", "theirs"], d)
        if r.returncode < 0 or r.returncode > 127:
            raise RuntimeError(f"git merge-file failed: {r.stderr.decode(errors='replace')}")
        return r.stdout.decode("utf-8"), r.returncode


def git_diff(a: str, b: str, *, minimal: bool = True, context: int = 3) -> str:
    """Body of ``git diff --no-index`` (from the first '@@'); '' if equal."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _write(d / "a.txt", a)
        _write(d / "b.txt", b)
        args = ["diff", "--no-index", "--no-color", "--no-indent-heuristic", f"-U{context}"]
        if minimal:
            args.append("--minimal")
        r = _run(args + ["a.txt", "b.txt"], d)
        if r.returncode not in (0, 1):
            raise RuntimeError(f"git diff failed: {r.stderr.decode(errors='replace')}")
        out = r.stdout.decode("utf-8")
        i = out.find("\n@@")
        return out[i + 1:] if i >= 0 else ""


def git_diff_full(a: str, b: str, *, context: int = 3) -> str:
    """Whole ``git diff --no-index`` output including headers."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _write(d / "a.txt", a)
        _write(d / "b.txt", b)
        r = _run(["diff", "--no-index", "--no-color", "--no-indent-heuristic", "--minimal", f"-U{context}", "a.txt", "b.txt"], d)
        return r.stdout.decode("utf-8")


def git_apply(original: str, patch: str, *, unidiff_zero: bool = False) -> tuple[bool, str]:
    """``git apply`` of ``patch`` (names a/a.txt, b/a.txt) onto ``original``."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _write(d / "a.txt", original)
        _write(d / "p.diff", patch)
        args = ["apply"] + (["--unidiff-zero"] if unidiff_zero else []) + ["p.diff"]
        r = _run(args, d)
        if r.returncode != 0:
            return False, r.stderr.decode(errors="replace")
        with open(d / "a.txt", encoding="utf-8", newline="") as f:
            return True, f.read()
