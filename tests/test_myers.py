import difflib
import random

import pytest

from diff3lab import apply_ops, myers_ops, script_length
from diff3lab.myers import myers_range
from diff3lab import oracle

from helpers import edited_pair, j, min_script_len, small_pair


def L(s: str) -> list[str]:
    return [c + "\n" for c in s]


def test_empty_inputs():
    assert myers_ops([], []) == []


def test_identical_is_all_equal():
    a = L("abc")
    ops = myers_ops(a, a)
    assert [o[0] for o in ops] == ["=", "=", "="]
    assert script_length(ops) == 0


def test_pure_insert_and_delete():
    assert [o[0] for o in myers_ops([], L("ab"))] == ["+", "+"]
    assert [o[0] for o in myers_ops(L("ab"), [])] == ["-", "-"]


def test_classic_paper_example_has_d_5():
    a, b = L("ABCABBA"), L("CBABAC")
    ops = myers_ops(a, b)
    assert script_length(ops) == 5
    assert apply_ops(a, b, ops) == b


def test_final_newline_matters():
    ops = myers_ops(["a\n", "b"], ["a\n", "b\n"])
    assert script_length(ops) == 2


def test_minimal_vs_lcs_dp_random_small_inputs():
    rng = random.Random(1234)
    for _ in range(600):
        a, b = small_pair(rng)
        ops = myers_ops(a, b)
        assert script_length(ops) == min_script_len(a, b), (a, b)
        assert apply_ops(a, b, ops) == b


def test_minimal_vs_lcs_dp_realistic_edits():
    rng = random.Random(99)
    for _ in range(150):
        a, b = edited_pair(rng)
        assert script_length(myers_ops(a, b)) == min_script_len(a, b)


def test_never_longer_than_difflib():
    rng = random.Random(7)
    for _ in range(200):
        a, b = edited_pair(rng, 50)
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        dl = sum((i2 - i1) + (j2 - j1) for t, i1, i2, j1, j2 in sm.get_opcodes() if t != "equal")
        assert script_length(myers_ops(a, b)) <= dl


def test_ops_positions_are_consistent():
    # apply_ops raises if any (i, j) disagrees with the running position
    rng = random.Random(5)
    for _ in range(100):
        a, b = small_pair(rng)
        apply_ops(a, b, myers_ops(a, b))


def test_apply_ops_rejects_a_corrupted_script():
    a, b = L("abc"), L("abd")
    ops = myers_ops(a, b)
    bad = [("=", 0, 1)] + ops[1:]
    with pytest.raises(ValueError):
        apply_ops(a, b, bad)
    with pytest.raises(ValueError):
        apply_ops(a, b, ops[:-1])


def test_myers_range_uses_absolute_indices():
    a = L("xxABCyy")
    b = L("xxACyy")
    ops = myers_range(a, b, 2, 5, 2, 4)
    assert script_length(ops) == 1
    assert ops[0][1] >= 2 and ops[0][2] >= 2


def test_large_similar_files_are_fast_and_correct():
    a = [f"line {i}\n" for i in range(3000)]
    b = list(a)
    del b[1000:1003]
    b.insert(2000, "new\n")
    ops = myers_ops(a, b)
    assert script_length(ops) == 4
    assert apply_ops(a, b, ops) == b


@pytest.mark.skipif(not oracle.git_available(), reason="git not installed")
def test_script_length_equals_git_minimal():
    rng = random.Random(77)
    checked = 0
    for _ in range(25):
        a, b = edited_pair(rng, rng.randint(3, 30))
        if a == b:
            continue
        g = oracle.git_diff(j(a), j(b))
        git_len = sum(1 for ln in g.splitlines() if ln[:1] in "+-")
        assert script_length(myers_ops(a, b)) == git_len
        checked += 1
    assert checked > 12
