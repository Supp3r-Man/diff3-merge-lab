"""`python -m diff3lab demo`: every number the README quotes, fixed seeds."""
from __future__ import annotations

import random
import statistics
import sys
import time
from collections import Counter

from . import oracle
from .algos import ALGORITHMS
from .gen import MERGE_CLASSES, make_lines, merge_pair, moved_block_pair, random_edits
from .merge import merge3
from .myers import script_length
from .patch import apply_hunks
from .unified import format_hunks, make_hunks, parse_unified, unified_diff

ALGS = ["myers", "patience", "difflib"]


def _j(lines: list[str]) -> str:
    return "".join(lines)


def change_runs(ops) -> int:
    """Number of maximal runs of consecutive non-equal ops (a fragmentation
    measure finer than hunks: hunks merge runs closer than 2*context)."""
    runs, prev_eq = 0, True
    for tag, _, _ in ops:
        if tag != "=" and prev_eq:
            runs += 1
        prev_eq = tag == "="
    return runs


def _stats(a: list[str], b: list[str], alg: str, context: int = 3) -> tuple[int, int, int, int]:
    """(script length, change runs, hunks at context 3, lines of unified diff body)"""
    ops = ALGORITHMS[alg](a, b)
    hunks = make_hunks(a, b, ops, context)
    body = format_hunks(hunks)
    n_lines = len(body.splitlines()) - 2 if body else 0
    return script_length(ops), change_runs(ops), len(hunks), n_lines


# ---------------------------------------------------------------- sections

def edit_script_sizes(seed: int = 11, cases: int = 300, n: int = 60) -> dict:
    out = {}
    for style in ("unique", "dup"):
        rng = random.Random(seed)
        sizes = {k: [] for k in ALGS}
        worse = Counter()
        for _ in range(cases):
            a = make_lines(rng, n, style)
            b = random_edits(rng, a, rng.randint(1, 6), "new", style)
            s = {alg: _stats(a, b, alg)[0] for alg in ALGS}
            for alg in ALGS:
                sizes[alg].append(s[alg])
                if s[alg] > s["myers"]:
                    worse[alg] += 1
        out[style] = {alg: (statistics.mean(sizes[alg]), worse[alg]) for alg in ALGS}
        out[style]["cases"] = cases
    return out


def moved_block_study(seed: int = 21, cases: int = 200) -> dict:
    """Two families: boilerplate-heavy bodies (unique_frac 0) and mixed (0.5)."""
    out = {}
    for name, frac in (("boilerplate-heavy", 0.0), ("mixed", 0.5)):
        rng = random.Random(f"{seed}-{name}")
        tot = {k: [0, 0, 0, 0] for k in ALGS}
        vs = Counter()
        worst = None
        for _ in range(cases):
            a, b = moved_block_pair(rng, 6, frac)
            res = {alg: _stats(a, b, alg) for alg in ALGS}
            for alg in ALGS:
                for t in range(4):
                    tot[alg][t] += res[alg][t]
            my, pa = res["myers"], res["patience"]
            vs["patience fewer runs" if pa[1] < my[1] else "patience more runs" if pa[1] > my[1] else "same runs"] += 1
            vs["patience fewer diff lines" if pa[3] < my[3] else "patience more diff lines" if pa[3] > my[3] else "same diff lines"] += 1
            if pa[0] > my[0]:
                vs["patience larger script"] += 1
            if pa[1] > my[1] and (worst is None or pa[1] - my[1] > worst[0]):
                worst = (pa[1] - my[1], my, pa)
        out[name] = {"cases": cases, "mean": {k: [x / cases for x in v] for k, v in tot.items()}, "vs": vs, "worst": worst}
    return out


def _gitdiff_body(a: list[str], b: list[str], context: int = 0) -> str:
    return oracle.git_diff(_j(a), _j(b), context=context)


def git_diff_study(seed: int = 31, cases: int = 150) -> dict | None:
    if not oracle.git_available():
        return None
    rng = random.Random(seed)
    same_len = same_text = tot = 0
    for _ in range(cases):
        style = rng.choice(["unique", "dup"])
        a = make_lines(rng, rng.randint(5, 40), style)
        b = random_edits(rng, a, rng.randint(1, 5), "new", style)
        if a == b:
            continue
        tot += 1
        g = oracle.git_diff(_j(a), _j(b))
        mine = unified_diff(a, b)
        mine_body = mine[mine.index("@@"):]
        glen = sum(1 for ln in g.splitlines() if ln[:1] in "+-")
        mlen = sum(1 for ln in mine_body.splitlines() if ln[:1] in "+-")
        same_len += glen == mlen
        same_text += g == mine_body
    return {"cases": tot, "same_len": same_len, "same_text": same_text}


def _projections(text: str) -> tuple[list[str], list[str]] | None:
    """(ours view, theirs view) of merge-style output; None if malformed."""
    ours: list[str] = []
    theirs: list[str] = []
    state = "clean"
    for ln in text.splitlines(keepends=True):
        if ln.startswith("<<<<<<< "):
            state = "ours"
        elif ln.startswith("=======") and state == "ours":
            state = "theirs"
        elif ln.startswith(">>>>>>> ") and state == "theirs":
            state = "clean"
        elif state in ("clean", "ours"):
            ours.append(ln)
            if state == "clean":
                theirs.append(ln)
        else:
            theirs.append(ln)
    return (ours, theirs) if state == "clean" else None


def _explain(base: list[str], ours: list[str], theirs: list[str], mine_text: str, git_text: str, both_conflict: bool) -> str:
    """Why do the two merges differ? Check the cheapest explanation first."""
    for side in (ours, theirs):
        g = oracle.git_diff(_j(base), _j(side), context=0)
        m = unified_diff(base, side, context=0)
        m = m[m.index("@@"):] if m else ""
        if g != m:
            return "base->side diff aligned differently (duplicate lines)"
    if both_conflict:
        pm, pg = _projections(mine_text), _projections(git_text)
        if pm is not None and pm == pg:
            return "same conflict, conflict-refinement split differs"
    return "UNEXPLAINED"


def _classify(mine, git_text: str, git_conf: int) -> str:
    mc = mine.has_conflict
    gc = git_conf > 0
    if mc and not gc:
        return "mine conflict / git clean"
    if gc and not mc:
        return "mine clean / git conflict"
    if mine.text != git_text:
        return "both clean, text differs" if not mc else "both conflict, text differs"
    return "agree"


def merge_study(seed: int = 41, per_class: int = 40) -> dict | None:
    if not oracle.git_available():
        return None
    result: dict = {}
    examples: dict[str, tuple] = {}
    for style in ("unique", "dup"):
        rows = {}
        for cls in MERGE_CLASSES:
            rng = random.Random(f"{seed}-{style}-{cls}")
            cnt: Counter = Counter()
            for _ in range(per_class):
                base, ours, theirs = merge_pair(rng, cls, 40, style)
                mine = merge3(base, ours, theirs)
                gtext, gconf = oracle.git_merge(_j(base), _j(ours), _j(theirs))
                kind = _classify(mine, gtext, gconf)
                cnt[kind] += 1
                cnt["mine_conf"] += mine.has_conflict
                cnt["git_conf"] += gconf > 0
                cnt["status_agree"] += mine.has_conflict == (gconf > 0)
                if kind != "agree":
                    why = _explain(base, ours, theirs, mine.text, gtext, mine.has_conflict and gconf > 0)
                    cnt[f"{kind} -> {why}"] += 1
                    key = f"{style}: {kind}"
                    size = len(base) + len(ours) + len(theirs)
                    if key not in examples or size < examples[key][0]:
                        examples[key] = (size, base, ours, theirs, mine.text, gtext, why)
            cnt["n"] = per_class
            rows[cls] = cnt
        result[style] = rows
    rng = random.Random(seed + 1)
    d3: Counter = Counter()
    for _ in range(per_class * 3):
        base, ours, theirs = merge_pair(rng, rng.choice(MERGE_CLASSES), 40, "unique")
        mine = merge3(base, ours, theirs, style="diff3")
        gtext, _gc = oracle.git_merge(_j(base), _j(ours), _j(theirs), diff3=True)
        d3["n"] += 1
        d3["agree"] += mine.text == gtext
        d3["conflicts"] += mine.has_conflict
    result["diff3"] = d3
    result["examples"] = examples
    return result


def fuzz_study(seed: int = 51, cases: int = 300) -> dict:
    out = {}
    for style in ("unique", "dup"):
        for context in (3, 1, 0):
            rng = random.Random(f"{seed}-{style}-{context}")
            c: Counter = Counter()
            for _ in range(cases):
                a = make_lines(rng, 60, style)
                b = random_edits(rng, a, rng.randint(1, 4), "new", style)
                if a == b:
                    continue
                hunks = parse_unified(unified_diff(a, b, context=context))[0].hunks
                k = rng.randint(1, 30)
                pad = [f"pad {rng.randrange(10**6)}\n" for _ in range(k)]
                a2, b2 = pad + a, pad + b
                c["n"] += 1
                ex = apply_hunks(a2, hunks, max_offset=0)
                c["exact_ok"] += ex.ok and ex.lines == b2
                c["exact_wrong"] += ex.ok and ex.lines != b2
                of = apply_hunks(a2, hunks)
                c["offset_ok"] += of.ok and of.lines == b2
                c["offset_wrong"] += of.ok and of.lines != b2
                h0 = hunks[0]
                lead = 0
                while lead < len(h0.lines) and h0.lines[lead][0] == " ":
                    lead += 1
                if lead == 0:
                    continue
                i, j = h0.old_start - 1, h0.new_start - 1
                a3, b3 = list(a2), list(b2)
                a3[k + i] = b3[k + j] = "perturbed context\n"
                c["pert_n"] += 1
                f0 = apply_hunks(a3, hunks)
                f1 = apply_hunks(a3, hunks, fuzz=1)
                c["pert_fuzz0_ok"] += f0.ok
                c["pert_fuzz1_ok"] += f1.ok and f1.lines == b3
                c["pert_fuzz1_wrong"] += f1.ok and f1.lines != b3
            out[(style, context)] = c
    return out


# ------------------------------------------------------------------ report

def _pct(x: int, n: int) -> str:
    return f"{100.0 * x / n:5.1f}%" if n else "  n/a"


def _show_merge_example(title: str, ex: tuple, p) -> None:
    _, base, ours, theirs, mine, git, why = ex
    p(f"  example [{title}] cause: {why}")
    for name, side in (("ours", ours), ("theirs", theirs)):
        d = unified_diff(base, side, context=0, old_name="base", new_name=name)
        for ln in d.splitlines():
            p(f"    {ln}")
    mine_l, git_l = mine.splitlines(), git.splitlines()
    first = next((i for i in range(min(len(mine_l), len(git_l))) if mine_l[i] != git_l[i]), min(len(mine_l), len(git_l)))
    lo = max(0, first - 1)
    p("    mine:", " | ".join(mine_l[lo:first + 6]))
    p("    git: ", " | ".join(git_l[lo:first + 6]))


def run_demo(out=sys.stdout) -> int:
    t0 = time.time()

    def p(*a) -> None:
        print(*a, file=out)

    p(f"diff3lab demo (python {sys.version.split()[0]}; git: {'yes' if oracle.git_available() else 'NOT FOUND, oracle sections skipped'})")

    p("\n[1] Edit-script size (non-equal lines; lower is better), 60-line files, 1-6 random edits")
    es = edit_script_sizes()
    for style, row in es.items():
        p(f"  {style:6s} ({row['cases']} cases): " + "  ".join(
            f"{alg} {row[alg][0]:.2f} (larger than Myers in {row[alg][1]})" for alg in ALGS))

    p("\n[2] Moved-function files (6 functions, one moved, one body line edited), context 3")
    mb = moved_block_study()
    for fam, r in mb.items():
        p(f"  family: {fam} bodies, {r['cases']} cases; mean script / change runs / hunks / diff lines")
        for alg in ALGS:
            s, runs, h, ln = r["mean"][alg]
            p(f"    {alg:9s} script {s:6.2f}   runs {runs:5.2f}   hunks {h:5.2f}   diff lines {ln:6.2f}")
        p("    patience vs myers: " + ", ".join(f"{k} {v}" for k, v in sorted(r["vs"].items())))
        if r["worst"]:
            d, my, pa = r["worst"]
            p(f"    worst case for patience (runs): myers (script,runs,hunks,lines) {my}, patience {pa}")

    g = git_diff_study()
    p("\n[3] Myers vs `git diff --no-index --minimal --no-indent-heuristic` (random edits, small files)")
    if g is None:
        p("  skipped: git not found")
    else:
        p(f"  {g['cases']} cases: same number of +/- lines {g['same_len']}/{g['cases']}; "
          f"byte-identical hunks {g['same_text']}/{g['cases']}")

    ms = merge_study()
    p("\n[4] Three-way merge vs `git merge-file -p` (40-line base, one edit per side unless 'random')")
    if ms is None:
        p("  skipped: git not found")
    else:
        for style in ("unique", "dup"):
            p(f"  base lines: {style}")
            p("    class     n  mine-conflict  git-conflict  status-agree  exact-text-equal")
            tot: Counter = Counter()
            for cls in MERGE_CLASSES:
                r = ms[style][cls]
                tot.update(r)
                p(f"    {cls:9s} {r['n']:2d}  {_pct(r['mine_conf'], r['n'])}        {_pct(r['git_conf'], r['n'])}       "
                  f"{_pct(r['status_agree'], r['n'])}       {_pct(r['agree'], r['n'])}")
            p(f"    ALL       {tot['n']:3d}  {_pct(tot['mine_conf'], tot['n'])}        {_pct(tot['git_conf'], tot['n'])}       "
              f"{_pct(tot['status_agree'], tot['n'])}       {_pct(tot['agree'], tot['n'])}")
            kinds = {k: v for k, v in tot.items() if " -> " in k}
            if not kinds:
                p("    disagreements: none")
            for k, v in sorted(kinds.items()):
                p(f"    disagreement x{v}: {k}")
        d3 = ms["diff3"]
        p(f"  diff3 style (|||||||) vs git --diff3, unique lines, all classes: exact text equal {d3['agree']}/{d3['n']} ({d3['conflicts']} with conflicts)")
        for key in sorted(ms["examples"]):
            _show_merge_example(key, ms["examples"][key], p)

    fz = fuzz_study()
    p("\n[5] Applying a diff(a, b) to a file shifted by 1-30 inserted lines (300 cases per row)")
    p("    lines  ctx   exact-only  offset-search  applied-in-WRONG-place  | one perturbed context line: fuzz0  fuzz1-correct")
    for (style, ctx), c in fz.items():
        pert = (f"{_pct(c['pert_fuzz0_ok'], c['pert_n'])}  {_pct(c['pert_fuzz1_ok'], c['pert_n'])}" if c["pert_n"] else "   n/a    n/a")
        p(f"    {style:6s} {ctx:3d}  {_pct(c['exact_ok'], c['n'])}     {_pct(c['offset_ok'], c['n'])}      "
          f"{c['offset_wrong']:4d} (exact-only: {c['exact_wrong']})        | {pert}")
    p(f"\n(done in {time.time() - t0:.1f}s)")
    return 0
