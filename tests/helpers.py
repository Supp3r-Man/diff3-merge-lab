"""Shared test helpers."""
from __future__ import annotations

import random

from diff3lab.gen import make_lines, random_edits


def lcs_len(a, b) -> int:
    """Simple O(NM) dynamic-programming LCS length (the oracle for minimality)."""
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b):
            cur.append(prev[j] + 1 if x == y else max(prev[j + 1], cur[j]))
        prev = cur
    return prev[-1]


def min_script_len(a, b) -> int:
    return len(a) + len(b) - 2 * lcs_len(a, b)


def small_pair(rng: random.Random):
    """Tiny alphabet so duplicates are everywhere (the hard case for diff)."""
    alpha = "abcd"[: rng.randint(2, 4)]
    a = [rng.choice(alpha) + "\n" for _ in range(rng.randint(0, 14))]
    b = [rng.choice(alpha) + "\n" for _ in range(rng.randint(0, 14))]
    return a, b


def edited_pair(rng: random.Random, n: int | None = None, style: str | None = None):
    style = style or rng.choice(["unique", "dup"])
    a = make_lines(rng, n if n is not None else rng.randint(0, 40), style)
    b = random_edits(rng, a, rng.randint(0, 5), "new", style)
    return a, b


def j(lines) -> str:
    return "".join(lines)
