"""Unified diff writer and parser.

Hunk lines are ``(tag, text)`` with tag in " -+" and ``text`` including its
own line ending. A last line without "\\n" is written followed by
"\\ No newline at end of file" and parsed back into a text without "\\n".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

from .algos import get_algorithm
from .myers import Op
from .textlines import split_lines

NO_EOL = "\\ No newline at end of file"
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class PatchParseError(ValueError):
    pass


@dataclass
class Hunk:
    old_start: int  # 1-based; for old_len == 0 it is the line BEFORE the hunk
    old_len: int
    new_start: int
    new_len: int
    lines: list[tuple[str, str]] = field(default_factory=list)

    def old_lines(self) -> list[str]:
        return [t for tag, t in self.lines if tag in " -"]

    def new_lines(self) -> list[str]:
        return [t for tag, t in self.lines if tag in " +"]

    def header(self) -> str:
        def rng(start: int, n: int) -> str:
            return f"{start}" if n == 1 else f"{start},{n}"
        return f"@@ -{rng(self.old_start, self.old_len)} +{rng(self.new_start, self.new_len)} @@"


@dataclass
class FilePatch:
    old_name: str
    new_name: str
    hunks: list[Hunk]


def make_hunks(a: Sequence[str], b: Sequence[str], ops: Sequence[Op], context: int = 3) -> list[Hunk]:
    if context < 0:
        raise ValueError("context must be >= 0")
    changes = [idx for idx, op in enumerate(ops) if op[0] != "="]
    if not changes:
        return []
    groups: list[tuple[int, int]] = []
    cs = ce = changes[0]
    for c in changes[1:]:
        if c - ce - 1 <= 2 * context:
            ce = c
        else:
            groups.append((cs, ce))
            cs = ce = c
    groups.append((cs, ce))
    hunks: list[Hunk] = []
    for cs, ce in groups:
        lo = max(cs - context, 0)
        hi = min(ce + 1 + context, len(ops))
        i0, j0 = ops[lo][1], ops[lo][2]
        lines: list[tuple[str, str]] = []
        old_len = new_len = 0
        for tag, i, j in ops[lo:hi]:
            if tag == "=":
                lines.append((" ", a[i]))
                old_len += 1
                new_len += 1
            elif tag == "-":
                lines.append(("-", a[i]))
                old_len += 1
            else:
                lines.append(("+", b[j]))
                new_len += 1
        hunks.append(Hunk(i0 + (1 if old_len else 0), old_len, j0 + (1 if new_len else 0), new_len, lines))
    return hunks


def format_hunks(hunks: Sequence[Hunk], old_name: str = "a/file", new_name: str = "b/file") -> str:
    if not hunks:
        return ""
    out = [f"--- {old_name}\n", f"+++ {new_name}\n"]
    for h in hunks:
        out.append(h.header() + "\n")
        for tag, text in h.lines:
            out.append(tag + text)
            if not text.endswith("\n"):
                out.append("\n" + NO_EOL + "\n")
    return "".join(out)


def unified_diff(
    a: Sequence[str],
    b: Sequence[str],
    *,
    algorithm: str = "myers",
    context: int = 3,
    old_name: str = "a/file",
    new_name: str = "b/file",
) -> str:
    ops = get_algorithm(algorithm)(a, b)
    return format_hunks(make_hunks(a, b, ops, context), old_name, new_name)


def _clean_name(raw: str) -> str:
    return raw.split("\t")[0].rstrip("\n").rstrip("\r")


def parse_unified(text: str) -> list[FilePatch]:
    """Parse one or more file patches. Lines before the first '---' header
    (``diff --git``, ``index`` ...) are ignored. Hunk bodies are delimited by
    the counts in the header, so a body line that starts with '--- ' is data."""
    lines = split_lines(text)
    pos = 0
    n = len(lines)
    patches: list[FilePatch] = []
    while pos < n:
        if not (lines[pos].startswith("--- ") and pos + 1 < n and lines[pos + 1].startswith("+++ ")):
            pos += 1
            continue
        fp = FilePatch(_clean_name(lines[pos][4:]), _clean_name(lines[pos + 1][4:]), [])
        pos += 2
        while pos < n and lines[pos].startswith("@@"):
            m = _HUNK_RE.match(lines[pos])
            if not m:
                raise PatchParseError(f"line {pos + 1}: malformed hunk header {lines[pos].rstrip()!r}")
            old_len = int(m.group(2)) if m.group(2) is not None else 1
            new_len = int(m.group(4)) if m.group(4) is not None else 1
            hunk = Hunk(int(m.group(1)), old_len, int(m.group(3)), new_len, [])
            pos += 1
            seen_old = seen_new = 0
            while seen_old < old_len or seen_new < new_len:
                if pos >= n:
                    raise PatchParseError("unexpected end of patch inside a hunk")
                raw = lines[pos]
                tag = raw[:1]
                body = raw[1:]
                if raw == "\n":  # context line whose single space was stripped
                    tag, body = " ", "\n"
                if tag == " ":
                    seen_old += 1
                    seen_new += 1
                elif tag == "-":
                    seen_old += 1
                elif tag == "+":
                    seen_new += 1
                elif tag == "\\":
                    _strip_eol(hunk, pos)
                    pos += 1
                    continue
                else:
                    raise PatchParseError(f"line {pos + 1}: unexpected line in hunk {raw.rstrip()!r}")
                if seen_old > old_len or seen_new > new_len:
                    raise PatchParseError(f"line {pos + 1}: hunk longer than its header says")
                hunk.lines.append((tag, body))
                pos += 1
            while pos < n and lines[pos].startswith("\\"):
                _strip_eol(hunk, pos)
                pos += 1
            if pos < n and _looks_like_body(lines, pos):
                raise PatchParseError(f"line {pos + 1}: hunk is longer than its header says")
            fp.hunks.append(hunk)
        patches.append(fp)
    return patches


def _looks_like_body(lines: list[str], pos: int) -> bool:
    """A diff body line right after a complete hunk means the header counts are
    wrong (fail closed instead of silently dropping the line). A new file
    header and the '-- ' signature of git format-patch are not body lines."""
    ln = lines[pos]
    if ln[:1] in (" ", "+"):
        return True
    if ln[:1] == "-":
        is_header = ln.startswith("--- ") and pos + 1 < len(lines) and lines[pos + 1].startswith("+++ ")
        return not is_header and ln != "-- \n"
    return False


def _strip_eol(hunk: Hunk, pos: int) -> None:
    if not hunk.lines:
        raise PatchParseError(f"line {pos + 1}: '\\ No newline' marker with no preceding line")
    tag, text = hunk.lines[-1]
    if not text.endswith("\n"):
        raise PatchParseError(f"line {pos + 1}: duplicate '\\ No newline' marker")
    hunk.lines[-1] = (tag, text[:-1])
