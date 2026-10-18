"""CLI. Exit codes (fail closed): 0 ok / no difference / clean merge,
1 differences / rejected hunks / conflicts, 2 could not judge (bad input,
unreadable file, crash)."""
from __future__ import annotations

import argparse
import sys

from .merge import merge3
from .patch import apply_hunks
from .textlines import split_lines
from .unified import PatchParseError, parse_unified, unified_diff


def _read(path: str) -> str:
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _write_out(text: str) -> None:
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.flush()


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="diff3lab", description="diff, patch and 3-way merge from scratch")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo", help="print the measured numbers (fixed seeds)")
    d = sub.add_parser("diff", help="unified diff of two files (exit 1 if they differ)")
    d.add_argument("old")
    d.add_argument("new")
    d.add_argument("-U", "--context", type=int, default=3)
    d.add_argument("--algorithm", choices=["myers", "patience", "difflib"], default="myers")
    pt = sub.add_parser("patch", help="apply a unified diff to a file, print the result (exit 1 if hunks rejected)")
    pt.add_argument("file")
    pt.add_argument("patch")
    pt.add_argument("--fuzz", type=int, default=0)
    pt.add_argument("--max-offset", type=int, default=100)
    m = sub.add_parser("merge", help="three-way merge: ours base theirs (exit 1 on conflicts)")
    m.add_argument("ours")
    m.add_argument("base")
    m.add_argument("theirs")
    m.add_argument("--diff3", action="store_true", help="show the base section in conflicts")
    m.add_argument("--no-refine", action="store_true")
    return ap


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    try:
        if args.cmd == "demo":
            from .demo import run_demo
            return run_demo()
        if args.cmd == "diff":
            a, b = split_lines(_read(args.old)), split_lines(_read(args.new))
            out = unified_diff(a, b, algorithm=args.algorithm, context=args.context,
                               old_name=args.old, new_name=args.new)
            _write_out(out)
            return 1 if out else 0
        if args.cmd == "patch":
            patches = parse_unified(_read(args.patch))
            if len(patches) != 1:
                print(f"diff3lab: expected exactly one file patch, found {len(patches)}", file=sys.stderr)
                return 2
            res = apply_hunks(split_lines(_read(args.file)), patches[0].hunks, fuzz=args.fuzz, max_offset=args.max_offset)
            _write_out(res.text)
            for r in res.rejected:
                print(f"diff3lab: hunk {r.hunk} {r.header} REJECTED: {r.reason}", file=sys.stderr)
            for ap_ in res.applied:
                if ap_.offset or ap_.fuzz:
                    print(f"diff3lab: hunk {ap_.hunk} applied with offset {ap_.offset}, fuzz {ap_.fuzz}", file=sys.stderr)
            return 0 if res.ok else 1
        if args.cmd == "merge":
            res = merge3(split_lines(_read(args.base)), split_lines(_read(args.ours)), split_lines(_read(args.theirs)),
                         labels=(args.ours, args.base, args.theirs),
                         style="diff3" if args.diff3 else "merge", refine=not args.no_refine)
            _write_out(res.text)
            return 1 if res.has_conflict else 0
    except (OSError, UnicodeDecodeError, PatchParseError, ValueError) as e:
        print(f"diff3lab: error: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # fail closed: a crash must never look like "clean"
        print(f"diff3lab: internal error: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    return 2
