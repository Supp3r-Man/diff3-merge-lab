"""diff3-style three-way merge.

1. Diff base->ours and base->theirs into change hunks ``(b0, b1, lines)``.
2. Cluster hunks (from either side) whose base ranges overlap or TOUCH
   (``next.b0 <= cluster_end``): like git's xdiff, two edits with no unchanged
   base line between them conflict, an unchanged line between them merges.
3. A cluster touched by one side takes that side; a cluster touched by both
   is clean if both sides produce identical text, otherwise a conflict.
4. ``refine=True`` (git "zealous" behaviour, merge style only) re-diffs
   ours vs theirs inside a conflict and pulls the common lines out of it.
   It is skipped for ``style="diff3"`` (git does the same: base must stay whole).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Union

from .algos import get_algorithm
from .textlines import ensure_eol


@dataclass
class Conflict:
    ours: list[str]
    theirs: list[str]
    base: list[str] | None  # None for refined (zealous) sub-conflicts

    def swapped(self) -> "Conflict":
        return Conflict(self.theirs, self.ours, self.base)


Segment = Union[list, Conflict]  # clean segments are plain list[str]


@dataclass
class MergeResult:
    segments: list[Segment]
    style: str = "merge"
    labels: tuple[str, str, str] = ("ours", "base", "theirs")

    @property
    def conflicts(self) -> list[Conflict]:
        return [s for s in self.segments if isinstance(s, Conflict)]

    @property
    def has_conflict(self) -> bool:
        return bool(self.conflicts)

    @property
    def text(self) -> str:
        return render(self.segments, self.labels, self.style)


def render(segments: Sequence[Segment], labels: tuple[str, str, str] = ("ours", "base", "theirs"), style: str = "merge") -> str:
    out: list[str] = []
    for seg in segments:
        if isinstance(seg, Conflict):
            out.append(f"<<<<<<< {labels[0]}\n")
            out.extend(_with_eol(seg.ours))
            if style == "diff3":
                out.append(f"||||||| {labels[1]}\n")
                out.extend(_with_eol(seg.base or []))
            out.append("=======\n")
            out.extend(_with_eol(seg.theirs))
            out.append(f">>>>>>> {labels[2]}\n")
        else:
            out.extend(seg)
    return "".join(out)


def _with_eol(lines: Sequence[str]) -> list[str]:
    """A conflict side must end in a newline or the next marker would glue on."""
    out = list(lines)
    if out:
        out[-1] = ensure_eol(out[-1])
    return out


@dataclass(frozen=True)
class _Hunk:
    b0: int
    b1: int
    lines: tuple[str, ...]
    side: int  # 0 ours, 1 theirs


def _hunks(base: Sequence[str], other: Sequence[str], side: int, diff) -> list[_Hunk]:
    hunks: list[_Hunk] = []
    cur: list | None = None  # [b0, b1, lines]
    for tag, i, j in diff(base, other):
        if tag == "=":
            if cur is not None:
                hunks.append(_Hunk(cur[0], cur[1], tuple(cur[2]), side))
                cur = None
            continue
        if cur is None:
            cur = [i, i, []]
        if tag == "-":
            cur[1] = i + 1
        else:
            cur[2].append(other[j])
    if cur is not None:
        hunks.append(_Hunk(cur[0], cur[1], tuple(cur[2]), side))
    return hunks


def _apply_range(base: Sequence[str], start: int, end: int, hunks: list[_Hunk]) -> list[str]:
    out: list[str] = []
    pos = start
    for h in sorted(hunks, key=lambda x: (x.b0, x.b1)):
        out.extend(base[pos:h.b0])
        out.extend(h.lines)
        pos = h.b1
    out.extend(base[pos:end])
    return out


def _refine(ours: list[str], theirs: list[str], diff) -> list[Segment]:
    """Split a conflict at lines ours and theirs agree on. The diff is always
    computed in a canonical argument order so merge(a, b) and merge(b, a)
    split identically."""
    swapped = tuple(ours) > tuple(theirs)
    a, b = (theirs, ours) if swapped else (ours, theirs)
    segs: list[Segment] = []
    ca: list[str] = []
    cb: list[str] = []

    def flush() -> None:
        if ca or cb:
            c = Conflict(list(ca), list(cb), None)
            segs.append(c.swapped() if swapped else c)
            ca.clear()
            cb.clear()

    clean: list[str] = []
    for tag, i, j in diff(a, b):
        if tag == "=":
            flush()
            clean.append(a[i])
            continue
        if clean:
            segs.append(clean)
            clean = []
        (ca if tag == "-" else cb).append(a[i] if tag == "-" else b[j])
    flush()
    if clean:
        segs.append(clean)
    return segs


def merge3(
    base: Sequence[str],
    ours: Sequence[str],
    theirs: Sequence[str],
    *,
    labels: tuple[str, str, str] = ("ours", "base", "theirs"),
    style: str = "merge",
    refine: bool = True,
    algorithm: str = "myers",
) -> MergeResult:
    if style not in ("merge", "diff3"):
        raise ValueError("style must be 'merge' or 'diff3'")
    diff = get_algorithm(algorithm)
    hunks = sorted(_hunks(base, ours, 0, diff) + _hunks(base, theirs, 1, diff), key=lambda h: (h.b0, h.b1, h.side))
    segments: list[Segment] = []

    def add_clean(lines: Sequence[str]) -> None:
        if not lines:
            return
        if segments and not isinstance(segments[-1], Conflict):
            segments[-1].extend(lines)  # type: ignore[union-attr]
        else:
            segments.append(list(lines))

    pos = 0
    i = 0
    while i < len(hunks):
        cs, ce = hunks[i].b0, hunks[i].b1
        members = [hunks[i]]
        i += 1
        while i < len(hunks) and hunks[i].b0 <= ce:
            ce = max(ce, hunks[i].b1)
            members.append(hunks[i])
            i += 1
        add_clean(base[pos:cs])
        pos = ce
        sides = {h.side for h in members}
        o = _apply_range(base, cs, ce, [h for h in members if h.side == 0])
        t = _apply_range(base, cs, ce, [h for h in members if h.side == 1])
        if sides == {0}:
            add_clean(o)
        elif sides == {1}:
            add_clean(t)
        elif o == t:
            add_clean(o)
        elif refine and style == "merge":
            for seg in _refine(o, t, diff):
                if isinstance(seg, Conflict):
                    segments.append(seg)
                else:
                    add_clean(seg)
        else:
            segments.append(Conflict(o, t, list(base[cs:ce])))
    add_clean(base[pos:])
    return MergeResult(segments, style, labels)
