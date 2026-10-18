# STEPS

**Part A** is what I did, in order. **Part B** is how you run it.

---

## Part A: steps taken

1. **Fixed the edit-script format first:** every op is `(tag, i, j)` where `(i, j)` is the current position in both inputs before the op. That makes a script self-checking (`apply_ops` raises if a position or an "equal" line is wrong) and lets Myers, patience and difflib share the unified writer, the merge and the tests.
2. **Wrote Myers:** greedy forward O(ND) with a per-round trace and backtracking, common prefix/suffix trimmed first. Checked minimality against an O(NM) LCS DP on 600 tiny duplicate-heavy pairs.
3. **Wrote patience:** unique-on-both-sides anchors, longest increasing chain (bisect), recursion between anchors, Myers fallback when a range has no unique line.
4. **Wrote the unified diff writer and parser:** hunk grouping at 2x context, `-0,0` / `+start,count` header rules, the `\ No newline at end of file` marker in both directions, parser that trusts header counts (so a body line that looks like `--- x` followed by `+++ y` stays data).
5. **Wrote patch apply:** match against the original lines, nearest offset first, may not start before the previous hunk ended, GNU-style fuzz, partial application with rejected hunks named.
6. **Wrote the diff3 merge:** hunks from both sides, clustered when they overlap or touch, one-sided cluster takes that side, identical text is clean, else conflict; zealous refinement for merge style only, in a canonical argument order so swapping ours and theirs swaps the output exactly.
7. **Added git as a differential oracle** (`git diff --no-index --minimal`, `git apply`, `git merge-file -p`), with a clean skip when git is missing, and wrote the seeded generators (`gen.py`) with controlled edit relations: far, near, touching, overlap, same, random.
8. **Ran the demo, read the results, changed the setup twice** (see problems below), then wrote 108 tests, then a 23-mutant check.

Problems and choices along the way:
- A python heredoc used to patch `gen.py` turned `\n` into real newlines and produced a syntax error. Fixed with the Edit tool and kept patching to Edit/Write from then on.
- First version of the moved-function files (all-unique bodies) gave identical hunk counts in 200/200 cases (script size differed in only 2), which says nothing. The next version (bodies from a shared vocabulary) made patience look worse on hunks. Only a finer measure (change runs, not just hunks at context 3) shows what patience actually buys, so the demo reports both, plus a boilerplate-heavy and a mixed family. Patience still loses on script size and on hunks; the README says so.
- The first merge-vs-git run already agreed 100% on unique lines. The duplicate-heavy generator was added so the comparison could fail, and it does: 11/240 text differences, all traced to base-to-side alignment differences (the demo classifies each one by comparing the two base-to-side diffs against git's).
- Tests found two design holes in my first patch code, both fixed: a hunk with no old lines floated up to 100 lines (so an insertion past the end of the file "applied"); and fuzz could strip a hunk of every anchoring line and then match anywhere. Now insert-only hunks apply only at their stated line and fuzz needs at least one line left to match.
- The parser silently ignored a body line after a hunk whose header count was too small. It now raises (the `-- ` signature of `git format-patch` and a new file header are exempted).
- A wrong test of mine: I expected patience to move the longer of two ambiguous blocks; it moves the shorter one because it counts anchors. Test fixed to assert 4, and the shorter-or-longer choice is part of the README finding.
- Another wrong test: "ours view of a conflict-free merge equals ours" is false (theirs-only edits are in it). Replaced with "no line inserted by either side is ever lost".
- The suite spawns many `git` processes (about 70 s on Windows). I cut the git case counts so the mutation check stays practical.

- One full-suite run on a heavily loaded machine (15 minutes instead of about 60 seconds) failed one git-oracle test; it passed alone and on re-run (108 passed in 50 s). I did not capture the failure text, so the cause is unconfirmed; the likely one is the 60 s per-git-call timeout, which I raised to 180 s. Treat it as a possible flake under load.
- Mutation check: first run 22/23 killed. The survivor was "refinement not in canonical order" (the swap-symmetry property tests never hit a pair where Myers aligns `diff(x, y)` and `diff(y, x)` differently). I searched for such pairs, added three targeted tests, and the second run killed 23/23. An earlier run of the script crashed after a 900 s timeout (my script did not handle a slow run; it now has a 300 s cap and reports a hang as a separate kill kind; the final run had zero hangs).

---

## Part B: steps for you

### Run it
1. Needs Python 3.11 or newer, no packages (pytest for the tests). `git` is optional but enables the oracle tests and demo sections.
2. `python -m diff3lab demo` prints every number in the README (about 2.5 minutes on Windows because of git process launches).
3. Try it: `python -m diff3lab diff a.txt b.txt > p.diff`, `python -m diff3lab patch a.txt p.diff`, `python -m diff3lab merge ours.txt base.txt theirs.txt --diff3`. Exit codes: 0 ok, 1 differences or conflicts or rejected hunks, 2 could not judge.

### Run the tests
`python -m pytest` (108 tests, about 70 seconds; git tests are skipped with a reason if git is missing).

### Mutation check
`python tools/mutation_check.py` (runs on a scratch copy of the repo; exit 0 only if every mutant is killed).

### What to read first
1. The README "Honest findings" section.
2. `diff3lab/merge.py` (about 200 lines, the cluster rule is the core).
3. `tests/test_merge.py` for the properties and the git comparison, then `diff3lab/demo.py` `_explain` for how each disagreement is classified.
