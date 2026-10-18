"""Apply hunks to a list of lines: exact match, offset search, optional fuzz.

Each hunk is matched against the ORIGINAL lines (never against a partly
patched copy), nearest offset first (0, +1, -1, +2, -2 ...), and may not start
before the end of the previously applied hunk. ``fuzz=f`` lets up to f leading
and f trailing context lines of a hunk differ, like GNU patch; the file's own
lines are kept in those positions. Hunks that do not apply are rejected and
reported by number; the others are still applied (partial result)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .unified import Hunk


@dataclass
class Applied:
    hunk: int  # 1-based
    offset: int  # lines from where the header said
    fuzz: int


@dataclass
class Rejected:
    hunk: int  # 1-based
    header: str
    reason: str


@dataclass
class ApplyResult:
    lines: list[str]
    applied: list[Applied] = field(default_factory=list)
    rejected: list[Rejected] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.rejected

    @property
    def text(self) -> str:
        return "".join(self.lines)


def _offsets(max_offset: int):
    yield 0
    for k in range(1, max_offset + 1):
        yield k
        yield -k


def _lead_trail(h: Hunk) -> tuple[int, int]:
    tags = [t for t, _ in h.lines]
    lead = 0
    while lead < len(tags) and tags[lead] == " ":
        lead += 1
    trail = 0
    while trail < len(tags) - lead and tags[len(tags) - 1 - trail] == " ":
        trail += 1
    return lead, trail


def apply_hunks(
    src: Sequence[str],
    hunks: Sequence[Hunk],
    *,
    max_offset: int = 100,
    fuzz: int = 0,
) -> ApplyResult:
    if max_offset < 0 or fuzz < 0:
        raise ValueError("max_offset and fuzz must be >= 0")
    n = len(src)
    out: list[str] = []
    cursor = 0  # first source line not yet consumed
    res = ApplyResult(lines=out)
    for idx, h in enumerate(hunks, start=1):
        old = h.old_lines()
        expected = h.old_start - 1 if h.old_len > 0 else h.old_start
        lead, trail = _lead_trail(h)
        found: tuple[int, int, int] | None = None  # pos, offset, fuzz
        for f in range(fuzz + 1):
            dl, dt = min(f, lead), min(f, trail)
            if f > 0 and dl == 0 and dt == 0:
                break  # nothing more to relax
            core = old[dl: len(old) - dt]
            if f > 0 and not core:
                break  # fuzz may not strip a hunk of every anchoring line
            # a hunk with no old lines has nothing to verify, so it cannot float
            for off in (_offsets(max_offset) if old else (0,)):
                p = expected + off
                if p < cursor or p + len(old) > n:
                    continue
                if list(src[p + dl: p + len(old) - dt]) == core:
                    found = (p, off, f)
                    break
            if found:
                break
        if not found:
            reason = "context does not match" if old else "position outside file"
            res.rejected.append(Rejected(idx, h.header(), reason))
            continue
        p, off, f = found
        dl, dt = min(f, lead), min(f, trail)
        out.extend(src[cursor:p])
        out.extend(src[p: p + dl])
        body = h.lines[dl: len(h.lines) - dt]
        out.extend(t for tag, t in body if tag in " +")
        out.extend(src[p + len(old) - dt: p + len(old)])
        cursor = p + len(old)
        res.applied.append(Applied(idx, off, f))
    out.extend(src[cursor:])
    return res
