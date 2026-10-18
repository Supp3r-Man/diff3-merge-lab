import io
import random
import subprocess
import sys
from pathlib import Path

import pytest

from diff3lab import demo
from diff3lab.cli import main
from diff3lab.gen import make_lines, merge_pair, moved_block_pair, random_edits
from diff3lab.textlines import ensure_eol, join_lines, split_lines

ROOT = Path(__file__).resolve().parent.parent


def run(*args, cwd=None):
    return subprocess.run([sys.executable, "-m", "diff3lab", *args], capture_output=True, text=True,
                          cwd=cwd or ROOT, timeout=120)


def w(path: Path, text: str) -> str:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return str(path)


# --------------------------------------------------------------- CLI exits

def test_cli_diff_exit_codes(tmp_path):
    a = w(tmp_path / "a", "x\ny\n")
    b = w(tmp_path / "b", "x\nZ\n")
    same = run("diff", a, a)
    assert same.returncode == 0 and same.stdout == ""
    d = run("diff", a, b)
    assert d.returncode == 1 and "-y" in d.stdout and "+Z" in d.stdout


def test_cli_diff_missing_file_is_exit_2(tmp_path):
    r = run("diff", str(tmp_path / "nope"), str(tmp_path / "nope2"))
    assert r.returncode == 2 and "error" in r.stderr


def test_cli_patch_ok_reject_and_bad_patch(tmp_path):
    a = w(tmp_path / "a", "".join(f"l{i}\n" for i in range(30)))
    b = w(tmp_path / "b", "".join(f"l{i}\n" if i != 15 else "NEW\n" for i in range(30)))
    patch = tmp_path / "p.diff"
    diff = run("diff", a, b).stdout
    w(patch, diff)
    ok = run("patch", a, str(patch))
    assert ok.returncode == 0 and "NEW" in ok.stdout
    damaged = w(tmp_path / "d", "".join(f"l{i}\n" if i != 15 else "other\n" for i in range(30)))
    rej = run("patch", damaged, str(patch))
    assert rej.returncode == 1 and "hunk 1" in rej.stderr and "REJECTED" in rej.stderr
    bad = w(tmp_path / "bad.diff", "--- a\n+++ b\n@@ -1,5 +1,5 @@\n x\n")
    assert run("patch", a, bad).returncode == 2
    assert run("patch", a, w(tmp_path / "empty.diff", "nothing here\n")).returncode == 2


def test_cli_merge_clean_conflict_and_missing(tmp_path):
    base = w(tmp_path / "base", "a\nb\nc\nd\ne\n")
    ours = w(tmp_path / "ours", "A\nb\nc\nd\ne\n")
    theirs = w(tmp_path / "theirs", "a\nb\nc\nd\nE\n")
    clean = run("merge", ours, base, theirs)
    assert clean.returncode == 0 and clean.stdout == "A\nb\nc\nd\nE\n"
    t2 = w(tmp_path / "t2", "X\nb\nc\nd\ne\n")
    conf = run("merge", ours, base, t2, "--diff3")
    assert conf.returncode == 1 and "<<<<<<<" in conf.stdout and "|||||||" in conf.stdout
    assert run("merge", ours, base, str(tmp_path / "missing")).returncode == 2


def test_cli_bad_usage_is_exit_2():
    assert main(["nonsense"]) == 2
    assert main([]) == 2


def test_cli_preserves_crlf(tmp_path):
    a = w(tmp_path / "a", "x\r\ny\r\n")
    b = w(tmp_path / "b", "x\r\nz\r\n")
    r = subprocess.run([sys.executable, "-m", "diff3lab", "diff", a, b], capture_output=True, cwd=ROOT)
    assert r.returncode == 1 and b"-y\r\n" in r.stdout and b"+z\r\n" in r.stdout


# ------------------------------------------------------------- text helpers

def test_split_lines_only_splits_on_newline():
    assert split_lines("a\r\nb\x0bc d\ne") == ["a\r\n", "b\x0bc d\n", "e"]
    assert split_lines("") == []
    assert split_lines("a\n") == ["a\n"]
    assert join_lines(split_lines("a\n\nb")) == "a\n\nb"
    assert ensure_eol("x") == "x\n" and ensure_eol("x\n") == "x\n"


# ---------------------------------------------------------- generators/demo

def test_generators_are_deterministic():
    a = merge_pair(random.Random(5), "overlap")
    b = merge_pair(random.Random(5), "overlap")
    assert a == b
    assert moved_block_pair(random.Random(1)) == moved_block_pair(random.Random(1))
    with pytest.raises(ValueError):
        make_lines(random.Random(1), 3, "weird")
    with pytest.raises(ValueError):
        merge_pair(random.Random(1), "bogus")


def test_moved_block_pair_is_a_permutation_plus_one_edit():
    for seed in range(20):
        a, b = moved_block_pair(random.Random(seed), 6, 0.5)
        assert len(a) == len(b)
        assert len(set(a) ^ set(b)) <= 2


def test_demo_sections_are_deterministic_and_sane():
    assert demo.edit_script_sizes(cases=20) == demo.edit_script_sizes(cases=20)
    es = demo.edit_script_sizes(cases=40)
    for style in ("unique", "dup"):
        assert es[style]["myers"][1] == 0  # Myers is never larger than itself
        assert es[style]["myers"][0] <= es[style]["patience"][0]
        assert es[style]["myers"][0] <= es[style]["difflib"][0]
    mb = demo.moved_block_study(cases=20)
    assert set(mb) == {"boilerplate-heavy", "mixed"}
    fz = demo.fuzz_study(cases=20)
    c = fz[("unique", 3)]
    assert c["exact_ok"] == 0 and c["offset_ok"] == c["n"]
    assert demo.fuzz_study(cases=20) == fz


def test_change_runs_counts_maximal_runs():
    ops = [("=", 0, 0), ("-", 1, 1), ("+", 2, 1), ("=", 2, 2), ("+", 3, 3)]
    assert demo.change_runs(ops) == 2
    assert demo.change_runs([("=", 0, 0)]) == 0


def test_projection_helper_round_trips_conflict_text():
    text = "a\n<<<<<<< ours\nX\n=======\nY\n>>>>>>> theirs\nb\n"
    assert demo._projections(text) == (["a\n", "X\n", "b\n"], ["a\n", "Y\n", "b\n"])
    assert demo._projections("<<<<<<< ours\nX\n") is None


def test_run_demo_reports_when_git_missing(monkeypatch):
    monkeypatch.setattr(demo.oracle, "GIT", None)
    # shrink the slow parts: only check it prints the skip notes and exits 0
    monkeypatch.setattr(demo, "edit_script_sizes", lambda: {"unique": {"cases": 1, **{a: (0.0, 0) for a in demo.ALGS}},
                                                              "dup": {"cases": 1, **{a: (0.0, 0) for a in demo.ALGS}}})
    monkeypatch.setattr(demo, "moved_block_study", lambda: {})
    monkeypatch.setattr(demo, "fuzz_study", lambda: {})
    buf = io.StringIO()
    assert demo.run_demo(buf) == 0
    out = buf.getvalue()
    assert "NOT FOUND" in out and out.count("skipped: git not found") == 2
