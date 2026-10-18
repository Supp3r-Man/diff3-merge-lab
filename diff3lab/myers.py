"""Myers O(ND) diff, greedy forward algorithm, producing a minimal edit script.

An edit script is a list of ops ``(tag, i, j)``. ``(i, j)`` is always the
current position in ``a`` and ``b`` *before* the op is applied:

* ``("=", i, j)``  a[i] == b[j], both advance
* ``("-", i, j)``  delete a[i], i advances
* ``("+", i, j)``  insert b[j], j advances

The script length (number of non-"=" ops) is D = N + M - 2 * LCS, the minimum
possible. Memory is O(D^2) for the trace (the linear-space refinement is not
implemented, see README).
"""
from __future__ import annotations

from typing import Sequence

Op = tuple[str, int, int]


def myers_range(a: Sequence[str], b: Sequence[str], a0: int, a1: int, b0: int, b1: int) -> list[Op]:
    """Minimal edit script for a[a0:a1] vs b[b0:b1], with absolute indices."""
    n = a1 - a0
    m = b1 - b0
    if n == 0 and m == 0:
        return []
    maxd = n + m
    off = maxd + 1
    v = [0] * (2 * maxd + 3)
    trace: list[list[int]] = []
    found = -1
    for d in range(maxd + 1):
        # state after round d-1, restricted to diagonals -d-1 .. d+1
        trace.append(v[off - d - 1: off + d + 2])
        for k in range(-d, d + 1, 2):
            if k == -d or (k != d and v[off + k - 1] < v[off + k + 1]):
                x = v[off + k + 1]  # step down: insertion of b[y-1]
            else:
                x = v[off + k - 1] + 1  # step right: deletion of a[x-1]
            y = x - k
            while x < n and y < m and a[a0 + x] == b[b0 + y]:
                x += 1
                y += 1
            v[off + k] = x
            if x >= n and y >= m:
                found = d
                break
        if found >= 0:
            break
    rev: list[Op] = []
    x, y = n, m
    for d in range(found, 0, -1):
        prev = trace[d]  # index of diagonal k in this slice is k + d + 1
        k = x - y
        if k == -d or (k != d and prev[k - 1 + d + 1] < prev[k + 1 + d + 1]):
            pk = k + 1
        else:
            pk = k - 1
        px = prev[pk + d + 1]
        py = px - pk
        sx, sy = (px, py + 1) if pk == k + 1 else (px + 1, py)  # snake start
        while x > sx:
            rev.append(("=", a0 + x - 1, b0 + y - 1))
            x -= 1
            y -= 1
        if pk == k + 1:
            rev.append(("+", a0 + px, b0 + py))
        else:
            rev.append(("-", a0 + px, b0 + py))
        x, y = px, py
    while x > 0 and y > 0:
        rev.append(("=", a0 + x - 1, b0 + y - 1))
        x -= 1
        y -= 1
    rev.reverse()
    return rev


def myers_ops(a: Sequence[str], b: Sequence[str]) -> list[Op]:
    """Minimal edit script (common prefix and suffix are trimmed first)."""
    n, m = len(a), len(b)
    pre = 0
    while pre < n and pre < m and a[pre] == b[pre]:
        pre += 1
    suf = 0
    while suf < n - pre and suf < m - pre and a[n - 1 - suf] == b[m - 1 - suf]:
        suf += 1
    ops: list[Op] = [("=", i, i) for i in range(pre)]
    ops.extend(myers_range(a, b, pre, n - suf, pre, m - suf))
    ops.extend(("=", n - suf + t, m - suf + t) for t in range(suf))
    return ops


def script_length(ops: Sequence[Op]) -> int:
    return sum(1 for op in ops if op[0] != "=")
