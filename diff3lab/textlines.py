"""Line helpers. Lines always keep their own line ending, so a final line
without a newline compares unequal to the same text with one (like git)."""
from __future__ import annotations


def split_lines(text: str) -> list[str]:
    """Split on "\\n" only (not \\r, \\x0b, \\u2028...), keeping the ending."""
    if not text:
        return []
    parts = text.split("\n")
    out = [p + "\n" for p in parts[:-1]]
    if parts[-1] != "":
        out.append(parts[-1])
    return out


def join_lines(lines: list[str]) -> str:
    return "".join(lines)


def ensure_eol(line: str) -> str:
    return line if line.endswith("\n") else line + "\n"
