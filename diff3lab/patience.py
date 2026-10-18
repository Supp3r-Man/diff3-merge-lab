"""Patience diff: anchor on lines that occur exactly once on each side, keep
the longest increasing chain of anchors, recurse between them. Ranges with no
unique common line fall back to Myers. The result is a valid edit script but
NOT always minimal (Myers is the minimal one)."""
from __future__ import annotations

from bisect import bisect_left
from collections import Counter
from typing import Sequence

from .myers import Op, myers_range


def _unique_anchors(a: Sequence[str], b: Sequence[str], a0: int, a1: int, b0: int, b1: int) -> list[tuple[int, int]]:
    ca = Counter(a[a0:a1])
    cb = Counter(b[b0:b1])
    pos_b = {b[j]: j for j in range(b0, b1) if cb[b[j]] == 1}
    pairs = [(i, pos_b[a[i]]) for i in range(a0, a1) if ca[a[i]] == 1 and a[i] in pos_b]
    return _lis(pairs)


def _lis(pairs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Longest chain increasing in the second element (pairs sorted by first)."""
    tails: list[int] = []  # tails[k] = smallest b-index ending a chain of length k+1
    tail_idx: list[int] = []  # index into pairs for that tail
    prev: list[int] = [-1] * len(pairs)
    for idx, (_, bj) in enumerate(pairs):
        k = bisect_left(tails, bj)
        if k == len(tails):
            tails.append(bj)
            tail_idx.append(idx)
        else:
            tails[k] = bj
            tail_idx[k] = idx
        prev[idx] = tail_idx[k - 1] if k > 0 else -1
    out: list[tuple[int, int]] = []
    cur = tail_idx[-1] if tail_idx else -1
    while cur >= 0:
        out.append(pairs[cur])
        cur = prev[cur]
    out.reverse()
    return out


def _patience(a: Sequence[str], b: Sequence[str], a0: int, a1: int, b0: int, b1: int, ops: list[Op]) -> None:
    while a0 < a1 and b0 < b1 and a[a0] == b[b0]:
        ops.append(("=", a0, b0))
        a0 += 1
        b0 += 1
    tail: list[Op] = []
    while a0 < a1 and b0 < b1 and a[a1 - 1] == b[b1 - 1]:
        a1 -= 1
        b1 -= 1
        tail.append(("=", a1, b1))
    if a0 == a1 and b0 == b1:
        pass
    elif a0 == a1:
        ops.extend(("+", a0, j) for j in range(b0, b1))
    elif b0 == b1:
        ops.extend(("-", i, b0) for i in range(a0, a1))
    else:
        anchors = _unique_anchors(a, b, a0, a1, b0, b1)
        if not anchors:
            ops.extend(myers_range(a, b, a0, a1, b0, b1))
        else:
            ai, bj = a0, b0
            for i, j in anchors:
                _patience(a, b, ai, i, bj, j, ops)
                ops.append(("=", i, j))
                ai, bj = i + 1, j + 1
            _patience(a, b, ai, a1, bj, b1, ops)
    tail.reverse()
    ops.extend(tail)


def patience_ops(a: Sequence[str], b: Sequence[str]) -> list[Op]:
    ops: list[Op] = []
    _patience(a, b, 0, len(a), 0, len(b), ops)
    return ops
