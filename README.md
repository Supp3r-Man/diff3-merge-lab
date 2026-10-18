# diff3-merge-lab

Diff, patch and three-way merge written from scratch in pure Python (standard library only), checked against `git` and `difflib` as differential oracles, with the places where it disagrees measured and explained rather than hidden.

Package: `diff3lab`. Python 3.11+. pytest is the only third-party dependency (tests only). CI is configured in `.github/workflows/ci.yml` (Python 3.11 and 3.13: tests plus the demo).

## What is in it

| Piece | Module | Notes |
|---|---|---|
| Myers O(ND) diff | `myers.py` | greedy forward algorithm, minimal edit script, O(D^2) trace memory |
| Patience diff | `patience.py` | unique-line anchors + longest increasing chain, recursion between anchors, Myers fallback |
| Unified diff writer + parser | `unified.py` | hunks, context N, `\ No newline at end of file` both ways, header counts decide where a hunk ends |
| Patch apply | `patch.py` | exact match, nearest-offset search, optional fuzz, rejects named by hunk number, partial apply |
| diff3 merge | `merge.py` | git-style markers, optional `|||||||` base section, identical-change handling, zealous refinement |
| Oracles | `oracle.py` | `git diff --no-index`, `git apply`, `git merge-file -p`; tests and demo skip cleanly if git is missing |

## Quick start

```
python -m diff3lab demo                    # every number below, fixed seeds
python -m pytest                           # 108 tests
python tools/mutation_check.py             # 23 deliberate breaks, each must fail the suite
python -m diff3lab diff old.txt new.txt    # exit 0 same, 1 differ, 2 error
python -m diff3lab patch file.txt p.diff   # prints result; exit 1 if any hunk rejected (named on stderr)
python -m diff3lab merge ours base theirs [--diff3]   # exit 0 clean, 1 conflicts, 2 error
```

The demo takes about 2.5 minutes on Windows (almost all of it is about 800 `git` process launches); the git sections are skipped with a message if git is not installed.

## Results (copied from `python -m diff3lab demo`, Python 3.13, git 2.53)

**Edit-script size** (non-equal lines, 60-line files, 300 random cases per row; Myers is minimal by construction and the tests compare it with an O(NM) LCS DP):

| lines | Myers | patience | difflib |
|---|---|---|---|
| unique | 8.86 | 8.86 | 8.86 |
| duplicate-heavy (12-line vocabulary) | 7.98 | 8.47 (larger in 13/300) | 8.00 (larger in 3/300) |

Against `git diff --no-index --minimal --no-indent-heuristic` (149 random cases): same number of `+`/`-` lines in 149/149, but byte-identical hunks in only 49/149. Where equal lines can slide, the two pick different but equally minimal placements.

**Moved-function files** (6 functions, one moved, one body line edited, 200 cases per family, context 3). Mean script / change runs / hunks / diff lines:

| family | algorithm | script | runs | hunks | diff lines |
|---|---|---|---|---|---|
| boilerplate-heavy bodies | Myers | 20.07 | 3.98 | 1.95 | 36.10 |
| | patience | 21.95 | 2.49 | 2.10 | 36.20 |
| | difflib | 21.18 | 2.47 | 2.13 | 34.73 |
| mixed (half unique lines) | Myers | 22.30 | 2.67 | 2.25 | 37.69 |
| | patience | 23.01 | 2.56 | 2.23 | 38.20 |
| | difflib | 22.59 | 2.54 | 2.25 | 36.85 |

**Merge vs `git merge-file -p`** (40-line base, one edit per side; 40 cases per class; "exact" = byte-identical merged text including markers):

| base lines | cases | mine conflicts | git conflicts | clean/conflict agree | exact text equal |
|---|---|---|---|---|---|
| unique | 240 | 37.1% | 37.1% | 100.0% | 100.0% |
| duplicate-heavy | 240 | 39.2% | 38.8% | 99.6% | 95.4% |

By designed overlap (unique lines): far 0% conflicts, near (1-2 unchanged lines between) 0%, touching (no line between) 100%, overlap 95%, identical change on both sides 0%, random 1-3 edits per side 27.5%. Mine and git are identical in every one of those 240 cases. diff3-style output (`|||||||` base section) equals `git merge-file --diff3` in 120/120 cases (52 with conflicts).

**Applying a diff to a file shifted by 1-30 inserted lines** (300 cases per row; "wrong" = applied without error but result differs from the expected file):

| lines | context | exact only | offset search | applied in wrong place | one perturbed context line: fuzz 0 / fuzz 1 correct |
|---|---|---|---|---|---|
| unique | 3 | 0.0% | 100.0% | 0 | 0.0% / 100.0% |
| unique | 1 | 0.0% | 100.0% | 0 | 0.0% / 67.7% |
| unique | 0 | 0.0% | 38.7% | 137 | n/a |
| duplicate-heavy | 3 | 0.0% | 100.0% | 0 | 0.0% / 99.6% |
| duplicate-heavy | 1 | 0.0% | 93.6% | 19 | 4.1% / 52.4% |
| duplicate-heavy | 0 | 0.0% | 20.8% | 167 | n/a |

## Honest findings

- **Patience does not win on edit-script size, by construction**: Myers is minimal. Patience made the script larger in 51/200 boilerplate-heavy moved-function files (worst case: 32 changed lines vs 18 for Myers; it keeps the larger of two ambiguous moves because it counts anchors, not lines). Its advantage is fragmentation: 2.49 change runs vs 3.98 when function bodies are mostly shared boilerplate, because Myers matches boilerplate lines across function boundaries to save a few edits. But that does not become fewer hunks at context 3 (2.10 vs 1.95, so slightly worse) or fewer diff lines (36.20 vs 36.10). With half-unique bodies it is a wash (2.56 vs 2.67 runs, 38.20 vs 37.69 diff lines). difflib's heuristic matcher reaches about the same fragmentation as patience with a smaller script on this data. The "patience is more readable" claim holds only under the finer fragmentation measure and only for boilerplate-heavy code.
- **Merge disagreements with git exist and are all explained**: with duplicate-heavy lines the merge conflict/clean status differs from git in 1 of 240 cases (mine conflict, git clean) and the merged text differs in 11 of 240 (10 where both conflict). Each one was checked: the base-to-side diff that `git merge-file` computes (xdiff) is aligned differently from mine on duplicate lines, so the edits touch or do not touch differently. An earlier exploratory run with 60 cases per class also produced one case in the other direction (mine clean, git conflict) with the same cause. With unique lines there are no disagreements. This is a difference in alignment choice, not an error in either, but it means "same as git" is only true where alignment is unambiguous.
- **Touching edits conflict, as in git.** Two edits with no unchanged base line between them are a conflict (100% in the `touching` class for both); one unchanged line between them merges cleanly.
- **Zero-context patches are unsafe to float.** Applied to a shifted file, `-U0` hunks were applied in the wrong place in 137/300 (unique) and 167/300 (duplicate-heavy) cases with offset search enabled (pure-insertion hunks have nothing to verify, so they only apply at the stated line). With 1 line of context and duplicate lines, 19/300 hunks landed in the wrong place. This is why fuzz refuses to strip a hunk of all its anchoring lines (the 1-line-context row: 67.7% of perturbed cases succeed, the rest are insert-only hunks left with no context).

## Limitations

- Line based only: no word/character diff, no whitespace-ignore options, `\r` stays part of the line.
- Myers keeps an O(D^2) trace; the linear-space (divide and conquer) refinement is not implemented. 3000-line files with 4 edits are fine, large rewrites would not be.
- Single-file patches in the CLI; the parser reads several file patches but there is no rename/mode/binary handling.
- The zealous conflict refinement splits a conflict at lines both sides agree on, like git; git's extra merging of conflicts separated only by non-alphanumeric lines is not implemented (the test data has none).
- Merge and patch tests use synthetic generators written by the same author; there is no real-repository corpus.

## Layout

```
diff3lab/        myers, patience, unified, patch, merge, gen (seeded inputs), oracle (git), demo, cli
tests/           108 tests: property tests (fixed seeds), git differential tests, CLI exit codes
tools/mutation_check.py   23 mutants run against a scratch copy of the repo
STEPS.md         steps taken and how to run it
```

## Mutation check

`python tools/mutation_check.py` copies the repo, breaks one behaviour at a time (23 of them: Myers snake and tie-break, patience uniqueness, hunk merging distance, the no-newline marker, parser count checks, offset search, fuzz relaxation and its safety guard, overlap and order checks, reject numbering, touching/identical-change rules, diff3 base section, ours/theirs order, newline before marker, canonical refinement order, zealous refinement, two CLI exit codes, final-line handling) and requires the suite to fail. A pattern that is not found is reported as such and counts as a failure. Result: 23/23 killed. The first run killed 22/23; the survivor (removing the canonical argument order in the refinement step) showed the symmetry property tests were too weak, because random inputs rarely hit pairs where `diff(x, y)` and `diff(y, x)` align duplicates differently. I found such pairs by search, added three targeted tests, and the mutant is now killed.
