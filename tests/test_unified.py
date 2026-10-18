import random

import pytest

from diff3lab import (PatchParseError, apply_hunks, make_hunks, myers_ops, parse_unified,
                      patience_ops, split_lines, unified_diff)
from diff3lab import oracle

from helpers import edited_pair, j


def test_simple_diff_exact_text():
    a = split_lines("a\nb\nc\n")
    b = split_lines("a\nX\nc\n")
    assert unified_diff(a, b) == "--- a/file\n+++ b/file\n@@ -1,3 +1,3 @@\n a\n-b\n+X\n c\n"


def test_identical_inputs_give_empty_diff():
    a = split_lines("a\nb\n")
    assert unified_diff(a, a) == ""


def test_context_zero_and_single_line_header_omits_count():
    a = split_lines("a\nb\nc\n")
    b = split_lines("a\nX\nc\n")
    assert unified_diff(a, b, context=0) == "--- a/file\n+++ b/file\n@@ -2 +2 @@\n-b\n+X\n"


def test_insert_into_empty_and_delete_everything():
    assert "@@ -0,0 +1,2 @@\n+a\n+b\n" in unified_diff([], split_lines("a\nb\n"))
    assert "@@ -1,2 +0,0 @@\n-a\n-b\n" in unified_diff(split_lines("a\nb\n"), [])


def test_zero_context_insertion_header_points_at_line_before():
    a = split_lines("a\nb\n")
    b = split_lines("a\nNEW\nb\n")
    assert "@@ -1,0 +2 @@\n+NEW\n" in unified_diff(a, b, context=0)


def test_no_newline_at_end_of_file_markers():
    a = split_lines("a\nb")
    b = split_lines("a\nb\n")
    d = unified_diff(a, b)
    assert d.endswith("-b\n\\ No newline at end of file\n+b\n")
    both = unified_diff(split_lines("x\nold"), split_lines("x\nnew"))
    assert both.count("\\ No newline at end of file") == 2
    ctx = unified_diff(split_lines("a\nz"), split_lines("A\nz"))
    assert ctx.endswith(" z\n\\ No newline at end of file\n")


def test_nearby_changes_share_a_hunk_and_far_ones_split():
    base = [f"l{i}\n" for i in range(30)]
    near = list(base)
    near[5] = "X\n"
    near[11] = "Y\n"  # 5 unchanged lines between, 2*3 >= 5
    assert unified_diff(base, near).count("@@ -") == 1
    far = list(base)
    far[5] = "X\n"
    far[12] = "Y\n"  # 6 unchanged lines between, still merges (<= 2*3)
    assert unified_diff(base, far).count("@@ -") == 1
    farther = list(base)
    farther[5] = "X\n"
    farther[13] = "Y\n"  # 7 between: two hunks
    assert unified_diff(base, farther).count("@@ -") == 2


def test_negative_context_and_unknown_algorithm_rejected():
    with pytest.raises(ValueError):
        unified_diff(["a\n"], ["b\n"], context=-1)
    with pytest.raises(ValueError):
        unified_diff(["a\n"], ["b\n"], algorithm="nope")


def test_hunk_header_counts_match_body_random():
    rng = random.Random(3)
    for _ in range(200):
        a, b = edited_pair(rng)
        ctx = rng.randint(0, 4)
        for h in make_hunks(a, b, myers_ops(a, b), ctx):
            assert h.old_len == sum(1 for t, _ in h.lines if t in " -")
            assert h.new_len == sum(1 for t, _ in h.lines if t in " +")


def test_roundtrip_parse_equals_written_hunks_random():
    rng = random.Random(4)
    for _ in range(200):
        a, b = edited_pair(rng)
        if rng.random() < 0.3 and a:
            a = a[:-1] + [a[-1].rstrip("\n")]  # no trailing newline
        ctx = rng.randint(0, 4)
        algo = rng.choice(["myers", "patience"])
        ops = patience_ops(a, b) if algo == "patience" else myers_ops(a, b)
        hunks = make_hunks(a, b, ops, ctx)
        parsed = parse_unified(unified_diff(a, b, context=ctx, algorithm=algo))
        if not hunks:
            assert parsed == []
        else:
            assert parsed[0].hunks == hunks


def test_parse_skips_git_headers_and_reads_multiple_files():
    text = ("diff --git a/x b/x\nindex 111..222 100644\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"
            "diff --git a/y b/y\n--- a/y\t2020\n+++ b/y\n@@ -1,0 +1 @@\n+z\n")
    ps = parse_unified(text)
    assert [p.old_name for p in ps] == ["a/x", "a/y"]
    assert ps[0].hunks[0].lines == [("-", "a\n"), ("+", "b\n")]


def test_body_line_that_looks_like_a_file_header_is_data():
    # the removed line is "-- x" so it is written as "--- x"; counts decide
    a = ["-- x\n", "keep\n"]
    b = ["++ y\n", "keep\n"]
    text = unified_diff(a, b)
    assert "\n--- x\n+++ y\n" in text  # byte-for-byte what a file header looks like
    patches = parse_unified(text)
    assert len(patches) == 1
    assert patches[0].hunks[0].lines[:2] == [("-", "-- x\n"), ("+", "++ y\n")]
    assert apply_hunks(a, patches[0].hunks).lines == b


@pytest.mark.parametrize("bad", [
    "--- a\n+++ b\n@@ nonsense @@\n",
    "--- a\n+++ b\n@@ -1,2 +1,2 @@\n a\n",  # truncated body
    "--- a\n+++ b\n@@ -1 +1 @@\n a\n+extra\n",  # extra body line after a complete hunk
    "--- a\n+++ b\n@@ -1,2 +1 @@\n a\n b\n",  # context overruns the new side
    "--- a\n+++ b\n@@ -1 +1 @@\n?weird\n",
    "--- a\n+++ b\n@@ -1 +1 @@\n\\ No newline at end of file\n-a\n+b\n",
    "--- a\n+++ b\n@@ -1 +1 @@\n-a\n\\ No newline at end of file\n\\ No newline at end of file\n+b\n",
])
def test_parse_errors_are_reported(bad):
    with pytest.raises(PatchParseError):
        parse_unified(bad)


def test_context_line_with_stripped_space_is_accepted():
    text = "--- a\n+++ b\n@@ -1,3 +1,3 @@\n a\n\n-c\n+d\n"
    h = parse_unified(text)[0].hunks[0]
    assert h.lines[1] == (" ", "\n")


def test_text_without_patch_parses_to_nothing():
    assert parse_unified("hello\nworld\n") == []


# ------------------------------------------------------------ git oracles

needs_git = pytest.mark.skipif(not oracle.git_available(), reason="git not installed")


@needs_git
def test_git_apply_accepts_our_diffs():
    rng = random.Random(8)
    checked = 0
    for _ in range(30):
        a, b = edited_pair(rng, rng.randint(3, 30))
        if a == b:
            continue
        if rng.random() < 0.3:
            b = b[:-1] + [b[-1].rstrip("\n")] if b else b
        ctx = rng.choice([0, 1, 3])
        patch = unified_diff(a, b, context=ctx, old_name="a/a.txt", new_name="b/a.txt")
        if not patch:
            continue
        ok, out = oracle.git_apply(j(a), patch, unidiff_zero=ctx == 0)
        assert ok, (patch, out)
        assert out == j(b)
        checked += 1
    assert checked > 12


@needs_git
def test_we_apply_gits_diffs():
    rng = random.Random(9)
    checked = 0
    for _ in range(30):
        a, b = edited_pair(rng, rng.randint(3, 30))
        if a == b or not a or not b:
            continue
        if rng.random() < 0.3:
            b = b[:-1] + [b[-1].rstrip("\n")]
        text = oracle.git_diff_full(j(a), j(b), context=rng.choice([1, 3]))
        patches = parse_unified(text)
        assert len(patches) == 1
        res = apply_hunks(a, patches[0].hunks, max_offset=0)
        assert res.ok and res.text == j(b), text
        checked += 1
    assert checked > 12


@needs_git
def test_known_simple_diff_is_byte_identical_to_git():
    a, b = split_lines("a\nb\nc\nd\n"), split_lines("a\nB\nc\nd\ne\n")
    git_body = oracle.git_diff(j(a), j(b))
    mine = unified_diff(a, b)
    assert mine[mine.index("@@"):] == git_body
