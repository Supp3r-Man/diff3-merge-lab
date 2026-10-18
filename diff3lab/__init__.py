"""diff3lab: diff, patch and three-way merge from scratch (stdlib only)."""
from .algos import ALGORITHMS, apply_ops, get_algorithm
from .merge import Conflict, MergeResult, merge3, render
from .myers import myers_ops, script_length
from .patch import ApplyResult, apply_hunks
from .patience import patience_ops
from .textlines import join_lines, split_lines
from .unified import Hunk, PatchParseError, make_hunks, parse_unified, unified_diff

__all__ = [
    "ALGORITHMS", "ApplyResult", "Conflict", "Hunk", "MergeResult", "PatchParseError",
    "apply_hunks", "apply_ops", "get_algorithm", "join_lines", "make_hunks", "merge3",
    "myers_ops", "parse_unified", "patience_ops", "render", "script_length",
    "split_lines", "unified_diff",
]
__version__ = "0.1.0"
