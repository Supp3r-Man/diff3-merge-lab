"""Mutation check: break one behaviour at a time in a scratch COPY of the repo
and require the test suite to fail. Never edits the real tree.

    python tools/mutation_check.py          # exit 0 only if every mutant is killed

A mutant whose pattern is not found (or found more than once) is reported as
"pattern not found" and counts as a failure, so a stale pattern can never
pass silently against an unchanged file."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (name, file, old, new)  -- old must occur exactly once (after LF normalisation)
MUTANTS = [
    ("myers: no snake extension", "diff3lab/myers.py",
     "while x < n and y < m and a[a0 + x] == b[b0 + y]:", "while False:"),
    ("myers: backtrack tie-break flipped", "diff3lab/myers.py",
     "if k == -d or (k != d and prev[k - 1 + d + 1] < prev[k + 1 + d + 1]):",
     "if k == -d or (k != d and prev[k - 1 + d + 1] > prev[k + 1 + d + 1]):"),
    ("patience: uniqueness in a not required", "diff3lab/patience.py",
     "if ca[a[i]] == 1 and a[i] in pos_b", "if a[i] in pos_b"),
    ("unified: hunks merge only within 1x context", "diff3lab/unified.py",
     "if c - ce - 1 <= 2 * context:", "if c - ce - 1 <= context:"),
    ("unified: drop 'No newline' marker", "diff3lab/unified.py",
     'out.append("\\n" + NO_EOL + "\\n")', 'out.append("\\n")'),
    ("unified: parser ignores hunk overrun", "diff3lab/unified.py",
     "if seen_old > old_len or seen_new > new_len:", "if False:"),
    ("unified: parser accepts body after a complete hunk", "diff3lab/unified.py",
     "if pos < n and _looks_like_body(lines, pos):", "if False:"),
    ("patch: offset search disabled", "diff3lab/patch.py",
     "for k in range(1, max_offset + 1):", "for k in range(1, 1):"),
    ("patch: fuzz does not relax context", "diff3lab/patch.py",
     "dl, dt = min(f, lead), min(f, trail)\n            if f > 0 and dl == 0 and dt == 0:",
     "dl, dt = 0, 0\n            if f > 0 and dl == 0 and dt == 0:"),
    ("patch: fuzz may strip all anchoring lines", "diff3lab/patch.py",
     "if f > 0 and not core:", "if False:"),
    ("patch: hunks may overlap earlier ones", "diff3lab/patch.py",
     "if p < cursor or p + len(old) > n:", "if p + len(old) > n:"),
    ("patch: empty-old hunks may float", "diff3lab/patch.py",
     "for off in (_offsets(max_offset) if old else (0,)):", "for off in _offsets(max_offset):"),
    ("patch: wrong hunk number in rejects", "diff3lab/patch.py",
     "Rejected(idx, h.header(), reason)", "Rejected(idx - 1, h.header(), reason)"),
    ("merge: touching edits no longer conflict", "diff3lab/merge.py",
     "while i < len(hunks) and hunks[i].b0 <= ce:", "while i < len(hunks) and hunks[i].b0 < ce:"),
    ("merge: identical change treated as conflict", "diff3lab/merge.py",
     "elif o == t:", "elif False:"),
    ("merge: diff3 base section dropped", "diff3lab/merge.py",
     "out.extend(_with_eol(seg.base or []))", "out.extend([])"),
    ("merge: ours/theirs swapped in output", "diff3lab/merge.py",
     "out.extend(_with_eol(seg.ours))", "out.extend(_with_eol(seg.theirs))"),
    ("merge: no newline added before marker", "diff3lab/merge.py",
     "out[-1] = ensure_eol(out[-1])", "out[-1] = out[-1]"),
    ("merge: refinement not canonical (asymmetric)", "diff3lab/merge.py",
     "swapped = tuple(ours) > tuple(theirs)", "swapped = False"),
    ("merge: zealous refinement off", "diff3lab/merge.py",
     'elif refine and style == "merge":', "elif False:"),
    ("cli: conflicts exit 0", "diff3lab/cli.py",
     "return 1 if res.has_conflict else 0", "return 0"),
    ("cli: rejected hunks exit 0", "diff3lab/cli.py",
     "return 0 if res.ok else 1", "return 0"),
    ("textlines: final line without newline dropped", "diff3lab/textlines.py",
     'if parts[-1] != "":', "if False:"),
]


def copy_repo(dst: Path) -> None:
    shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "*.pyc"))


TIMEOUT = 300  # a clean run takes about 70 s; a mutant that hangs is reported as such


def run_tests(cwd: Path) -> int:
    """pytest exit code; 124 if the run hangs (an infinite loop is a detectable break, reported separately)."""
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider"],
                           cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return 124
    return r.returncode


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="diff3lab-mut-"))
    results: list[tuple[str, str]] = []
    try:
        base = work / "baseline"
        copy_repo(base)
        if run_tests(base) != 0:
            print("baseline (unmutated copy) FAILS; fix the tests first")
            return 2
        for n, (name, rel, old, new) in enumerate(MUTANTS):
            dst = work / f"m{n}"
            copy_repo(dst)
            path = dst / rel
            with open(path, encoding="utf-8", newline="") as f:
                text = f.read().replace("\r\n", "\n")
            if text.count(old) != 1:
                results.append((name, f"pattern not found (occurs {text.count(old)}x)"))
                print(f"  [{n + 1}/{len(MUTANTS)}] {results[-1][1]:22s} {name}", flush=True)
                continue
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text.replace(old, new))
            rc = run_tests(dst)
            results.append((name, "SURVIVED" if rc == 0 else "killed (hang/timeout)" if rc == 124 else "killed"))
            print(f"  [{n + 1}/{len(MUTANTS)}] {results[-1][1]:22s} {name}", flush=True)
            shutil.rmtree(dst, ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    killed = sum(1 for _, s in results if s.startswith("killed"))
    hung = sum(1 for _, s in results if s.startswith("killed (hang"))
    print(f"{killed}/{len(MUTANTS)} killed ({hung} of them by hanging past {TIMEOUT}s)")
    return 0 if killed == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
