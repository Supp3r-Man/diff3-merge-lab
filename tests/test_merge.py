import random

import pytest

from diff3lab import Conflict, merge3, split_lines
from diff3lab import oracle
from diff3lab.gen import MERGE_CLASSES, make_lines, merge_pair, random_edits

from helpers import j


def S(s: str) -> list[str]:
    return split_lines(s)


def rand_triple(rng, style=None):
    style = style or rng.choice(["unique", "dup"])
    base = make_lines(rng, rng.randint(0, 30), style)
    a = random_edits(rng, base, rng.randint(0, 3), "ours", style)
    b = random_edits(rng, base, rng.randint(0, 3), "theirs", style)
    return base, a, b


def test_no_changes_is_clean_and_unchanged():
    base = S("a\nb\nc\n")
    r = merge3(base, base, base)
    assert not r.has_conflict and r.text == "a\nb\nc\n"


def test_one_sided_changes_apply():
    base = S("a\nb\nc\n")
    assert merge3(base, S("a\nB\nc\n"), base).text == "a\nB\nc\n"
    assert merge3(base, base, S("a\nb\nC\n")).text == "a\nb\nC\n"


def test_edits_on_far_apart_lines_both_apply():
    base = S("1\n2\n3\n4\n5\n6\n7\n")
    r = merge3(base, S("ONE\n2\n3\n4\n5\n6\n7\n"), S("1\n2\n3\n4\n5\n6\nSEVEN\n"))
    assert not r.has_conflict and r.text == "ONE\n2\n3\n4\n5\n6\nSEVEN\n"


def test_identical_change_on_both_sides_is_not_a_conflict():
    base = S("a\nb\nc\n")
    both = S("a\nSAME\nc\n")
    r = merge3(base, both, both)
    assert not r.has_conflict and r.text == "a\nSAME\nc\n"


def test_identical_deletion_on_both_sides_is_clean():
    base = S("a\nb\nc\n")
    r = merge3(base, S("a\nc\n"), S("a\nc\n"))
    assert not r.has_conflict and r.text == "a\nc\n"


def test_edits_separated_by_one_unchanged_line_merge_cleanly():
    base = S("a\nb\nc\nd\n")
    r = merge3(base, S("A\nb\nc\nd\n"), S("a\nb\nC\nd\n"))
    assert not r.has_conflict and r.text == "A\nb\nC\nd\n"


def test_touching_edits_with_no_line_between_conflict_like_git():
    base = S("a\nb\nc\nd\n")
    r = merge3(base, S("A\nb\nc\nd\n"), S("a\nB\nc\nd\n"))
    assert r.has_conflict
    assert r.text == "<<<<<<< ours\nA\nb\n=======\na\nB\n>>>>>>> theirs\nc\nd\n"


def test_same_line_edited_differently_is_a_conflict_with_exact_markers():
    base = S("a\nb\nc\n")
    r = merge3(base, S("a\nOURS\nc\n"), S("a\nTHEIRS\nc\n"))
    assert r.text == "a\n<<<<<<< ours\nOURS\n=======\nTHEIRS\n>>>>>>> theirs\nc\n"
    assert len(r.conflicts) == 1


def test_diff3_style_includes_the_base_section():
    base = S("a\nb\nc\n")
    r = merge3(base, S("a\nOURS\nc\n"), S("a\nTHEIRS\nc\n"), style="diff3")
    assert r.text == ("a\n<<<<<<< ours\nOURS\n||||||| base\nb\n=======\nTHEIRS\n>>>>>>> theirs\nc\n")


def test_custom_labels_are_used():
    base = S("b\n")
    r = merge3(base, S("o\n"), S("t\n"), labels=("HEAD", "ancestor", "feature"), style="diff3")
    assert "<<<<<<< HEAD\n" in r.text and "||||||| ancestor\n" in r.text and ">>>>>>> feature\n" in r.text


def test_delete_vs_modify_conflicts_with_empty_side():
    base = S("a\nb\nc\nd\ne\n")
    ours = S("a\nd\ne\n")  # deletes b, c
    theirs = S("a\nb\nCHANGED\nd\ne\n")  # modifies c
    r = merge3(base, ours, theirs)
    assert r.has_conflict
    c = r.conflicts[0]
    assert c.ours == [] and c.theirs == ["b\n", "CHANGED\n"]
    d3 = merge3(base, ours, theirs, style="diff3")
    assert d3.conflicts[0].ours == []
    assert d3.conflicts[0].base == ["b\n", "c\n"]
    assert d3.conflicts[0].theirs == ["b\n", "CHANGED\n"]


def test_both_insert_at_same_point_differently_conflicts_but_same_text_does_not():
    base = S("a\nz\n")
    assert merge3(base, S("a\nX\nz\n"), S("a\nY\nz\n")).has_conflict
    assert not merge3(base, S("a\nX\nz\n"), S("a\nX\nz\n")).has_conflict


def test_conflict_side_without_final_newline_gets_one_before_marker():
    base = S("a\nb")
    r = merge3(base, S("a\nOURS"), S("a\nTHEIRS"))
    assert r.text == "a\n<<<<<<< ours\nOURS\n=======\nTHEIRS\n>>>>>>> theirs\n"


def test_zealous_refine_pulls_common_lines_out_of_a_conflict():
    base = S("1\n2\n3\n")
    ours = S("A\nX\nC\n")
    theirs = S("A\nY\nC\n")
    refined = merge3(base, ours, theirs, refine=True)
    assert refined.text == "A\n<<<<<<< ours\nX\n=======\nY\n>>>>>>> theirs\nC\n"
    plain = merge3(base, ours, theirs, refine=False)
    assert plain.text.startswith("<<<<<<< ours\nA\nX\nC\n=======\nA\nY\nC\n")


def test_invalid_style_rejected():
    with pytest.raises(ValueError):
        merge3([], [], [], style="zdiff3")


def test_patience_algorithm_option_gives_same_result_on_unique_lines():
    rng = random.Random(61)
    for _ in range(60):
        base, a, b = rand_triple(rng, "unique")
        assert merge3(base, a, b, algorithm="patience").text == merge3(base, a, b).text


# ------------------------------------------------------------- properties

def test_merge_of_identical_sides_is_that_side_random():
    rng = random.Random(1)
    for _ in range(400):
        base, a, _ = rand_triple(rng)
        r = merge3(base, a, a)
        assert not r.has_conflict and r.text == j(a)


def test_merge_with_unchanged_side_is_the_changed_side_random():
    rng = random.Random(2)
    for _ in range(400):
        base, a, _ = rand_triple(rng)
        r1 = merge3(base, base, a)
        r2 = merge3(base, a, base)
        assert not r1.has_conflict and r1.text == j(a)
        assert not r2.has_conflict and r2.text == j(a)


@pytest.mark.parametrize("refine", [True, False])
def test_merge_is_symmetric_up_to_swapped_conflict_sides_random(refine):
    rng = random.Random(3)
    for _ in range(500):
        base, a, b = rand_triple(rng)
        r1 = merge3(base, a, b, refine=refine)
        r2 = merge3(base, b, a, refine=refine)
        swapped = [s.swapped() if isinstance(s, Conflict) else s for s in r2.segments]
        assert r1.segments == swapped, (base, a, b)


@pytest.mark.parametrize("ours,theirs", [
    ("aba", "bbbbaa"),
    ("abbbba", "babba"),
    ("baba", "abbbab"),
])
def test_refinement_is_symmetric_where_myers_alignment_is_not(ours, theirs):
    """For these pairs diff(x, y) and diff(y, x) align the duplicate lines
    differently, so refinement must pick one canonical direction."""
    base = ["z\n"]
    o = [c + "\n" for c in ours]
    t = [c + "\n" for c in theirs]
    r1 = merge3(base, o, t)
    r2 = merge3(base, t, o)
    assert r1.has_conflict
    assert r1.segments == [s.swapped() if isinstance(s, Conflict) else s for s in r2.segments]


def test_merge_symmetric_for_every_controlled_class():
    rng = random.Random(4)
    for cls in MERGE_CLASSES:
        for _ in range(60):
            base, a, b = merge_pair(rng, cls)
            r1 = merge3(base, a, b, style="diff3")
            r2 = merge3(base, b, a, style="diff3")
            assert r1.segments == [s.swapped() if isinstance(s, Conflict) else s for s in r2.segments]


def test_conflict_free_merge_contains_every_clean_side_line_of_both_edits():
    rng = random.Random(5)
    for _ in range(100):
        base, a, b = merge_pair(rng, rng.choice(["far", "near"]))
        r = merge3(base, a, b)
        assert not r.has_conflict
        merged = r.text
        for line in a + b:
            if line.startswith(("ours ", "theirs ", "x ")):
                assert line in merged


def test_controlled_classes_behave_as_designed():
    rng = random.Random(6)
    for cls, must_conflict in [("far", False), ("near", False), ("same", False), ("touching", True)]:
        for _ in range(60):
            base, a, b = merge_pair(rng, cls)
            assert merge3(base, a, b).has_conflict == must_conflict, cls
    hits = sum(merge3(*merge_pair(rng, "overlap")).has_conflict for _ in range(100))
    assert hits >= 85


def test_no_inserted_line_from_either_side_is_ever_lost_random():
    rng = random.Random(7)
    for _ in range(200):
        base, a, b = rand_triple(rng, "unique")
        for refine, style in ((True, "merge"), (False, "diff3")):
            merged = set(merge3(base, a, b, style=style, refine=refine).text.splitlines(keepends=True))
            for line in a:
                if line.startswith("ours "):
                    assert line in merged
            for line in b:
                if line.startswith("theirs "):
                    assert line in merged


def test_diff3_conflict_base_section_is_a_slice_of_the_base_random():
    rng = random.Random(12)
    seen = 0
    for _ in range(200):
        base, a, b = rand_triple(rng, "unique")
        for c in merge3(base, a, b, style="diff3").conflicts:
            n = len(c.base)
            assert any(base[i:i + n] == c.base for i in range(len(base) - n + 1))
            seen += 1
    assert seen > 20


# ------------------------------------------------------------ git oracle

needs_git = pytest.mark.skipif(not oracle.git_available(), reason="git not installed")


@needs_git
def test_unique_lines_match_git_merge_file_exactly_all_classes():
    """Unique lines = no alignment ambiguity, so clean/conflict and the exact
    merged text (markers included) must equal git's."""
    rng = random.Random(8)
    for cls in MERGE_CLASSES:
        for _ in range(8):
            base, a, b = merge_pair(rng, cls, 40, "unique")
            mine = merge3(base, a, b)
            gtext, gconf = oracle.git_merge(j(base), j(a), j(b))
            assert mine.has_conflict == (gconf > 0), cls
            assert mine.text == gtext, (cls, mine.text, gtext)


@needs_git
def test_unique_lines_diff3_style_matches_git_diff3():
    rng = random.Random(9)
    for cls in MERGE_CLASSES:
        for _ in range(5):
            base, a, b = merge_pair(rng, cls, 40, "unique")
            mine = merge3(base, a, b, style="diff3")
            gtext, _ = oracle.git_merge(j(base), j(a), j(b), diff3=True)
            assert mine.text == gtext


@needs_git
def test_duplicate_heavy_lines_agree_on_status_almost_always():
    """Documented divergence: with many duplicate lines git's xdiff may align
    base->side differently, so a few cases differ. We bound it, not hide it."""
    rng = random.Random(10)
    n = agree_status = agree_text = 0
    for cls in MERGE_CLASSES:
        for _ in range(10):
            base, a, b = merge_pair(rng, cls, 40, "dup")
            mine = merge3(base, a, b)
            gtext, gconf = oracle.git_merge(j(base), j(a), j(b))
            n += 1
            agree_status += mine.has_conflict == (gconf > 0)
            agree_text += mine.text == gtext
    assert agree_status / n >= 0.95
    assert agree_text / n >= 0.85


@needs_git
def test_git_and_ours_agree_that_clean_merge_of_random_unique_edits_is_equal():
    rng = random.Random(11)
    clean = 0
    for _ in range(40):
        base, a, b = rand_triple(rng, "unique")
        mine = merge3(base, a, b)
        gtext, gconf = oracle.git_merge(j(base), j(a), j(b))
        assert mine.has_conflict == (gconf > 0)
        if not mine.has_conflict:
            assert mine.text == gtext
            clean += 1
    assert clean > 5
