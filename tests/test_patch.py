import random

import pytest

from diff3lab import apply_hunks, parse_unified, split_lines, unified_diff
from diff3lab.unified import Hunk

from helpers import edited_pair


def hunks_of(a, b, ctx=3, algo="myers"):
    text = unified_diff(a, b, context=ctx, algorithm=algo)
    return parse_unified(text)[0].hunks if text else []


def numbered(n, prefix="l"):
    return [f"{prefix}{i}\n" for i in range(n)]


def test_exact_apply():
    a = numbered(20)
    b = list(a)
    b[10] = "CHANGED\n"
    res = apply_hunks(a, hunks_of(a, b))
    assert res.ok and res.lines == b
    assert res.applied[0].offset == 0 and res.applied[0].fuzz == 0


def test_offset_search_finds_shifted_hunk_and_reports_offset():
    a = numbered(20)
    b = list(a)
    b[10] = "CHANGED\n"
    hs = hunks_of(a, b)
    shifted = ["x\n", "y\n", "z\n"] + a
    res = apply_hunks(shifted, hs)
    assert res.ok and res.lines == ["x\n", "y\n", "z\n"] + b
    assert res.applied[0].offset == 3


def test_offset_beyond_limit_is_rejected_and_reported():
    a = numbered(20)
    b = list(a)
    b[10] = "CHANGED\n"
    shifted = [f"pad{i}\n" for i in range(10)] + a
    res = apply_hunks(shifted, hunks_of(a, b), max_offset=5)
    assert not res.ok
    assert res.lines == shifted
    assert res.rejected[0].hunk == 1 and "context" in res.rejected[0].reason
    assert apply_hunks(shifted, hunks_of(a, b), max_offset=10).ok


def test_exact_only_mode_rejects_any_shift():
    a = numbered(10)
    b = list(a)
    b[5] = "C\n"
    assert not apply_hunks(["p\n"] + a, hunks_of(a, b), max_offset=0).ok


def test_rejected_hunk_is_named_and_the_other_hunks_still_apply():
    a = numbered(60)
    b = list(a)
    b[5] = "FIRST\n"
    b[30] = "SECOND\n"
    b[55] = "THIRD\n"
    hs = hunks_of(a, b)
    assert len(hs) == 3
    damaged = list(a)
    damaged[30] = "someone else edited this\n"
    res = apply_hunks(damaged, hs)
    assert [r.hunk for r in res.rejected] == [2]
    assert [x.hunk for x in res.applied] == [1, 3]
    assert res.lines[5] == "FIRST\n" and res.lines[55] == "THIRD\n"
    assert res.lines[30] == "someone else edited this\n"


def test_fuzz_allows_one_changed_context_line_at_the_edge():
    a = numbered(20)
    b = list(a)
    b[10] = "CHANGED\n"
    hs = hunks_of(a, b)
    target = list(a)
    target[7] = "edge context differs\n"  # first leading context line of the hunk
    assert not apply_hunks(target, hs, fuzz=0).ok
    res = apply_hunks(target, hs, fuzz=1)
    assert res.ok and res.applied[0].fuzz == 1
    expected = list(b)
    expected[7] = "edge context differs\n"  # the file's own line is kept
    assert res.lines == expected


def test_fuzz_does_not_forgive_a_changed_line_next_to_the_edit():
    a = numbered(20)
    b = list(a)
    b[10] = "CHANGED\n"
    hs = hunks_of(a, b)
    target = list(a)
    target[8] = "second context line differs\n"  # 2nd of 3 leading context lines
    assert not apply_hunks(target, hs, fuzz=1).ok
    assert apply_hunks(target, hs, fuzz=2).ok


def test_fuzz_never_strips_a_hunk_of_all_anchoring_lines():
    h = Hunk(5, 2, 5, 3, [(" ", "a\n"), ("+", "new\n"), (" ", "b\n")])
    target = ["zzz\n"] * 10
    assert not apply_hunks(target, [h], fuzz=2).ok
    assert apply_hunks(["a\n", "b\n"], [Hunk(1, 2, 1, 3, h.lines)], fuzz=0).ok


def test_out_of_order_or_overlapping_hunk_is_rejected():
    a = numbered(10)
    h1 = Hunk(5, 1, 5, 1, [("-", "l4\n"), ("+", "A\n")])
    h2 = Hunk(2, 1, 2, 1, [("-", "l1\n"), ("+", "B\n")])
    res = apply_hunks(a, [h1, h2], max_offset=0)
    assert [r.hunk for r in res.rejected] == [2]
    assert res.lines[4] == "A\n" and res.lines[1] == "l1\n"


def test_nearest_of_two_equal_matches_wins():
    a = ["x\n", "dup\n", "y\n", "gap\n", "gap\n", "gap\n", "dup\n", "z\n"]
    h = Hunk(7, 1, 7, 1, [("-", "dup\n"), ("+", "DUP\n")])
    res = apply_hunks(a, [h])
    assert res.lines[6] == "DUP\n" and res.lines[1] == "dup\n"


def test_create_from_empty_and_delete_everything():
    b = numbered(3)
    assert apply_hunks([], hunks_of([], b)).lines == b
    a = numbered(3)
    assert apply_hunks(a, hunks_of(a, [])).lines == []


def test_insertion_position_past_end_of_file_is_rejected():
    h = Hunk(50, 0, 51, 1, [("+", "x\n")])
    res = apply_hunks(["a\n"], [h])
    assert not res.ok and "outside" in res.rejected[0].reason


def test_no_newline_at_eof_round_trips():
    a = split_lines("one\ntwo")
    b = split_lines("one\ntwo\nthree")
    res = apply_hunks(a, hunks_of(a, b))
    assert res.text == "one\ntwo\nthree"
    res2 = apply_hunks(b, hunks_of(b, a))
    assert res2.text == "one\ntwo"


def test_negative_parameters_rejected():
    with pytest.raises(ValueError):
        apply_hunks([], [], max_offset=-1)
    with pytest.raises(ValueError):
        apply_hunks([], [], fuzz=-1)


@pytest.mark.parametrize("algo", ["myers", "patience", "difflib"])
def test_apply_of_diff_gives_b_random(algo):
    rng = random.Random(100 + len(algo))
    for _ in range(300):
        a, b = edited_pair(rng)
        ctx = rng.choice([0, 1, 3, 5])
        hs = hunks_of(a, b, ctx, algo)
        res = apply_hunks(a, hs, max_offset=0)
        assert res.ok and res.lines == b, (a, b, ctx)


def test_shifted_apply_with_enough_context_is_correct_random():
    rng = random.Random(55)
    for _ in range(200):
        a, b = edited_pair(rng, 50, "unique")
        if a == b:
            continue
        k = rng.randint(1, 30)
        pad = [f"pad{i}\n" for i in range(k)]
        res = apply_hunks(pad + a, hunks_of(a, b))
        assert res.ok and res.lines == pad + b
