import random

from diff3lab import apply_ops, myers_ops, patience_ops, script_length
from diff3lab.gen import make_lines, random_edits
from diff3lab.patience import _lis, _unique_anchors

from helpers import edited_pair


def L(s: str) -> list[str]:
    return [c + "\n" for c in s]


def test_lis_picks_longest_increasing_chain():
    pairs = [(0, 3), (1, 1), (2, 2), (3, 0), (4, 4)]
    chain = _lis(pairs)
    assert [b for _, b in chain] == [1, 2, 4]
    assert _lis([]) == []


def test_unique_anchor_must_be_unique_on_both_sides():
    a = L("xAyAz")  # A twice in a
    b = L("xAyz")
    anchors = _unique_anchors(a, b, 0, len(a), 0, len(b))
    assert [a[i] for i, _ in anchors] == L("xyz")


def test_valid_script_on_random_inputs():
    rng = random.Random(21)
    for _ in range(300):
        a, b = edited_pair(rng)
        assert apply_ops(a, b, patience_ops(a, b)) == b


def test_valid_script_on_tiny_alphabet():
    rng = random.Random(22)
    for _ in range(300):
        a = [rng.choice("ab") + "\n" for _ in range(rng.randint(0, 12))]
        b = [rng.choice("ab") + "\n" for _ in range(rng.randint(0, 12))]
        assert apply_ops(a, b, patience_ops(a, b)) == b


def test_never_smaller_than_myers_and_sometimes_larger():
    """Myers is minimal, so patience can only tie or lose on script size.
    This documents the cost: on duplicate-heavy input it does lose."""
    rng = random.Random(23)
    larger = 0
    for _ in range(300):
        a = make_lines(rng, 40, "dup")
        b = random_edits(rng, a, rng.randint(1, 6), "n", "dup")
        sp = script_length(patience_ops(a, b))
        sm = script_length(myers_ops(a, b))
        assert sp >= sm
        larger += sp > sm
    assert larger > 0


def test_no_unique_lines_falls_back_to_myers_exactly():
    a, b = L("aabba"), L("bbaab")
    assert patience_ops(a, b) == myers_ops(a, b)


def test_moved_unique_block_is_kept_together():
    a = L("12ABC34")
    b = L("1234ABC")
    ops = patience_ops(a, b)
    assert script_length(ops) == 4  # keeps 1,2,A,B,C; moves the shorter "34"
    assert apply_ops(a, b, ops) == b


def test_swapped_functions_with_shared_boilerplate_keep_one_function_whole():
    # patience anchors on the unique headers: one function header stays equal
    f1 = ["def one():\n", "  a()\n", "}\n", "\n"]
    f2 = ["def two():\n", "  b()\n", "}\n", "\n"]
    a = f1 + f2
    b = f2 + f1
    pat = patience_ops(a, b)
    assert apply_ops(a, b, pat) == b
    assert script_length(pat) == 8  # == Myers: the LCS is one function (4 lines)
    kept = {a[o[1]] for o in pat if o[0] == "="}
    assert kept & {"def one():\n", "def two():\n"}
