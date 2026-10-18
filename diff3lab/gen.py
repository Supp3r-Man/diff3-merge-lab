"""Seeded synthetic inputs shared by tests and the demo (no real data)."""
from __future__ import annotations

import random

WORDS = ["alpha", "bravo", "cargo", "delta", "ember", "forge", "gamma", "harbor",
         "ivory", "jungle", "kernel", "lumen", "matrix", "nectar", "orbit", "prism"]

DUP_VOCAB = ["\n", "}\n", "{\n", "    return x\n", "    x = 1\n", "    pass\n", "end\n",
             "if x:\n", "else:\n", "x += 1\n", "# note\n", "call()\n"]


def make_lines(rng: random.Random, n: int, style: str = "unique") -> list[str]:
    if style == "unique":
        return [f"line {i:03d} {rng.choice(WORDS)}\n" for i in range(n)]
    if style == "dup":
        return [rng.choice(DUP_VOCAB) for _ in range(n)]
    raise ValueError(style)


def new_lines(rng: random.Random, tag: str, k: int) -> list[str]:
    return [f"{tag} {rng.randrange(10**6):06d}\n" for _ in range(k)]


def one_edit(rng: random.Random, lines: list[str], tag: str, style: str = "unique") -> list[str]:
    """Delete, insert or replace a short run at a random place."""
    n = len(lines)
    kind = rng.choice(["del", "ins", "rep"]) if n else "ins"
    pos = rng.randrange(0, n + 1) if kind == "ins" else rng.randrange(0, max(n, 1))
    k = rng.randint(1, 3)
    fresh = new_lines(rng, tag, k) if style == "unique" else [rng.choice(DUP_VOCAB) for _ in range(k)]
    if kind == "ins":
        return lines[:pos] + fresh + lines[pos:]
    if kind == "del":
        return lines[:pos] + lines[pos + k:]
    return lines[:pos] + fresh + lines[pos + k:]


def random_edits(rng: random.Random, lines: list[str], n_edits: int, tag: str = "new", style: str = "unique") -> list[str]:
    for _ in range(n_edits):
        lines = one_edit(rng, lines, tag, style)
    return lines


# ---- moved-function files ------------------------------------------------

STATEMENTS = ["    x = load(x)\n", "    x = clean(x)\n", "    log(x)\n"]


def _function(rng: random.Random, name: str, unique_frac: float) -> list[str]:
    """Unique header; each body line is either unique to this function (with
    probability ``unique_frac``) or boilerplate from a 3-statement vocabulary;
    a few blank lines inside. unique_frac=0 is all-boilerplate."""
    body: list[str] = []
    for k in range(rng.randint(4, 10)):
        body.append(f"    x = step_{name}_{k}(x)\n" if rng.random() < unique_frac else rng.choice(STATEMENTS))
        if rng.random() < 0.2:
            body.append("\n")
    return [f"def {name}(x):\n"] + body + ["    return x\n", "\n", "\n"]


def moved_block_pair(rng: random.Random, n_funcs: int = 6, unique_frac: float = 0.0) -> tuple[list[str], list[str]]:
    """A module and the same module with one function moved to another place
    and one extra line edited inside another function."""
    funcs = [_function(rng, f"func_{k}", unique_frac) for k in range(n_funcs)]
    a = [ln for f in funcs for ln in f]
    order = list(range(n_funcs))
    src = rng.randrange(n_funcs)
    order.remove(src)
    dst = rng.randrange(n_funcs)
    order.insert(dst, src)
    edited = [list(f) for f in funcs]
    tgt = rng.randrange(n_funcs)
    edited[tgt][1] = f"    x = tweak_{tgt}(x)\n"
    b = [ln for k in order for ln in edited[k]]
    return a, b


# ---- merge pairs ---------------------------------------------------------

MERGE_CLASSES = ["far", "near", "touching", "overlap", "same", "random"]


def _edit_region(rng: random.Random, base_n: int, kind: str, length: int, start: int) -> tuple[int, int, list[str]]:
    """(b0, b1, replacement) for a single edit; kind in del/ins/rep."""
    tag = "x"
    if kind == "ins":
        return start, start, new_lines(rng, tag, length)
    end = min(start + length, base_n)
    if kind == "del":
        return start, end, []
    return start, end, new_lines(rng, tag, rng.randint(1, 3))


def _apply_edit(lines: list[str], edit: tuple[int, int, list[str]], tag: str) -> list[str]:
    b0, b1, rep = edit
    rep = [r.replace("x ", tag + " ", 1) for r in rep]
    return lines[:b0] + rep + lines[b1:]


def merge_pair(rng: random.Random, cls: str, n: int = 40, style: str = "unique") -> tuple[list[str], list[str], list[str]]:
    """(base, ours, theirs) where the relation between the two edits is
    controlled by ``cls``. ``random`` gives each side 1-3 independent edits."""
    base = make_lines(rng, n, style)
    if cls == "random":
        ours = random_edits(rng, base, rng.randint(1, 3), "ours", style)
        theirs = random_edits(rng, base, rng.randint(1, 3), "theirs", style)
        return base, ours, theirs
    la = rng.randint(1, 3)
    s1 = rng.randrange(6, n - 16)
    k1 = rng.choice(["del", "rep", "ins"] if cls != "overlap" else ["del", "rep"])
    e1 = _edit_region(rng, n, k1, la, s1)
    if cls == "same":
        return base, _apply_edit(base, e1, "x"), _apply_edit(base, e1, "x")
    k2 = rng.choice(["del", "rep", "ins"] if cls != "overlap" else ["del", "rep"])
    lb = rng.randint(1, 3)
    if cls == "far":
        s2 = e1[1] + rng.randint(4, 10)
    elif cls == "near":
        s2 = e1[1] + rng.randint(1, 2)
    elif cls == "touching":
        s2 = e1[1]
    elif cls == "overlap":
        s2 = rng.randint(e1[0], max(e1[0], e1[1] - 1))
    else:
        raise ValueError(cls)
    e2 = _edit_region(rng, n, k2, lb, s2)
    ours = _apply_edit(base, e1, "ours")
    theirs = _apply_edit(base, e2, "theirs")
    if rng.random() < 0.5:
        ours, theirs = (_apply_edit(base, e2, "ours"), _apply_edit(base, e1, "theirs"))
    return base, ours, theirs
