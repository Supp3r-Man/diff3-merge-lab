"""Diff algorithm registry, plus difflib adapted to the same op format."""
from __future__ import annotations

import difflib
from typing import Callable, Sequence

from .myers import Op, myers_ops
from .patience import patience_ops


def difflib_ops(a: Sequence[str], b: Sequence[str]) -> list[Op]:
    """difflib.SequenceMatcher (autojunk off) as an edit script."""
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    ops: list[Op] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            ops.extend(("=", i1 + t, j1 + t) for t in range(i2 - i1))
        else:
            ops.extend(("-", i, j1) for i in range(i1, i2))
            ops.extend(("+", i2, j) for j in range(j1, j2))
    return ops


ALGORITHMS: dict[str, Callable[[Sequence[str], Sequence[str]], list[Op]]] = {
    "myers": myers_ops,
    "patience": patience_ops,
    "difflib": difflib_ops,
}


def get_algorithm(name: str) -> Callable[[Sequence[str], Sequence[str]], list[Op]]:
    try:
        return ALGORITHMS[name]
    except KeyError:
        raise ValueError(f"unknown diff algorithm {name!r}; choose from {sorted(ALGORITHMS)}") from None


def apply_ops(a: Sequence[str], b: Sequence[str], ops: Sequence[Op]) -> list[str]:
    """Rebuild b from a and a script (checks the script is consistent)."""
    out: list[str] = []
    ai = bj = 0
    for tag, i, j in ops:
        if (i, j) != (ai, bj):
            raise ValueError(f"inconsistent op {(tag, i, j)} at position {(ai, bj)}")
        if tag == "=":
            if a[i] != b[j]:
                raise ValueError(f"op '=' at {(i, j)} but lines differ")
            out.append(a[i])
            ai += 1
            bj += 1
        elif tag == "-":
            ai += 1
        elif tag == "+":
            out.append(b[j])
            bj += 1
        else:
            raise ValueError(f"bad tag {tag!r}")
    if ai != len(a) or bj != len(b):
        raise ValueError("script does not consume both inputs")
    return out
