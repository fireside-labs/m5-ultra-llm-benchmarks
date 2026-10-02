#!/usr/bin/env python3
"""Build a blind side-by-side judge pack from several result labels, and tally the verdicts.

Build (one markdown file per task; answers shuffled per task and labelled X, Y, Z, ...):
  python make_judge_pack.py --labels qwen38,glm53,dsv4
  python make_judge_pack.py --labels a,b,c --root results/reason-eval --out DIR --seed 7
  python make_judge_pack.py --labels a,b,c --with-reference     # append the gold checklist (optional)

Writes to <out> (default <root>/_judge/<labels joined by '+'>):
  JUDGE_INSTRUCTIONS.md   rubric + required verdict format (give this to the judge)
  Rxx.md                  task prompt + anonymised answers for one task
  all_tasks.md            instructions + every task in one file (for a single long-context judge)
  _key.json / _key.md     HIDDEN: letter -> label per task. Do not show these to the judge.

Tally (after the judge has written verdicts in the required format into one or more files):
  python make_judge_pack.py --tally DIR/verdicts.md [--out DIR]
  -> per-label mean rank, Borda points, pairwise wins, mean criterion scores; writes tally.md

Answers are the raw answer channel with <think> blocks removed. Self-identifying model, vendor
and label names are replaced with "[model]". Reasoning streams are never included.
"""
import argparse
import json
import random
import re
import statistics
import sys
from pathlib import Path

from evallib import DEFAULT_RESULTS, load_gold, load_task, strip_think, task_ids

LETTERS = ["X", "Y", "Z", "W", "V", "U", "T", "S"]
VENDOR_RE = re.compile(r"\b(qwen[\w.\-]*|glm[\w.\-]*|chatglm|zhipu|z\.ai|deepseek[\w.\-]*|alibaba|tongyi|moonshot|kimi|"
                       r"openai|chatgpt|gpt-?\d[\w.\-]*|gemini|llama[\w.\-]*|mistral)\b", re.I)

INSTRUCTIONS = """# Judge instructions (blind comparison)

You are judging answers written by different AI assistants to the same task. The assistants are
anonymised as X, Y, Z (and so on); their order is shuffled independently for every task. Do not
try to guess which assistant is which.

The tasks test *general reasoning and steering*, not writing style: seeing the whole problem,
naming the variables that matter, spotting what an analysis missed or got wrong, telling real
problems from things that only look like problems, prioritising, and finding the crux of a
disagreement. Every fact the assistants needed was in the task prompt.

For each task, score every answer from 1 to 10 on three criteria:

1. **Insight**: Did it see the important issues, including non-obvious ones? Is the reasoning
   correct, with numbers checked where the prompt gives them? Penalise confident errors, and
   penalise flagging things the prompt shows are already handled.
2. **Prioritisation**: Are the most important points first? Is the top 3 / crux / sensitivity
   list right? Does it separate decisive issues from minor ones?
3. **Decision usefulness**: Would a decision-maker know what to do next and why? Is it specific
   to this situation rather than generic advice? (Debates: is it fair to both sides, and are
   the cruxes real?)

Do not reward length, formatting or confident tone. A short answer that finds the three issues
that matter beats a long list of plausible-sounding filler. Then rank the answers (ties allowed
with `=`).

Output exactly this block for every task, and nothing else between blocks:

```
TASK: R01
SCORES: X=8/7/8, Y=6/6/5, Z=9/8/9
RANKING: Z > X > Y
RATIONALE: <2-4 sentences: the decisive differences>
```

`SCORES` lists insight/prioritisation/usefulness for each letter.
"""


def scrub(text, labels):
    t = VENDOR_RE.sub("[model]", text)
    for lab in labels:
        if len(lab) >= 3:
            t = re.sub(re.escape(lab), "[model]", t, flags=re.I)
    return t


def reference_block(g):
    lines = ["", "## Reference checklist (for the judge; not exhaustive)", ""]
    for x in g["items"]:
        side = f" [{x['side']}]" if x.get("side") else ""
        lines.append(f"- ({x['importance']}){side} {x['text']}")
    for c in g.get("cruxes", []):
        lines.append(f"- (crux) {c['text']}")
    for d in g.get("decoys", []):
        lines.append(f"- (NOT a real problem - decoy) {d['text']}: {d['why_not']}")
    if "estimate" in g:
        lines.append(f"- (estimate) sane range {g['estimate']['full_credit'][0]}-{g['estimate']['full_credit'][1]} ports; {g.get('notes', '')}")
    return "\n".join(lines)


def build(args):
    labels = [x.strip() for x in args.labels.split(",") if x.strip()]
    if len(labels) < 2:
        sys.exit("need at least 2 labels")
    if len(labels) > len(LETTERS):
        sys.exit(f"at most {len(LETTERS)} labels")
    root = Path(args.root).expanduser()
    for lab in labels:
        if not (root / lab).is_dir():
            sys.exit(f"no results folder {root / lab}")
    out = Path(args.out).expanduser() if args.out else root / "_judge" / "+".join(labels)
    out.mkdir(parents=True, exist_ok=True)
    ids = task_ids()
    if args.tasks:
        ids = [t for t in ids if t in set(args.tasks.split(","))]
    key, blocks = {}, []
    (out / "JUDGE_INSTRUCTIONS.md").write_text(INSTRUCTIONS)
    for t in ids:
        rng = random.Random(f"{args.seed}:{t}")
        order = labels[:]
        rng.shuffle(order)
        key[t] = {LETTERS[i]: lab for i, lab in enumerate(order)}
        parts = [f"# Task {t}", "", "## The task given to every assistant", "", "````markdown", load_task(t), "````", ""]
        for i, lab in enumerate(order):
            p = root / lab / f"{t}.raw.txt"
            ans = strip_think(p.read_text()) if p.exists() else ""
            ans = scrub(ans, labels) if ans else "*(no answer: empty or missing)*"
            # demote the answer's headings so they nest under "## Answer X"
            ans = re.sub(r"^(#{1,5}) ", lambda m: "#" * min(6, len(m.group(1)) + 2) + " ", ans, flags=re.M)
            parts += [f"## Answer {LETTERS[i]}", "", ans, ""]
        if args.with_reference:
            parts.append(reference_block(load_gold(t)))
        md = "\n".join(parts) + "\n"
        (out / f"{t}.md").write_text(md)
        blocks.append(md)
    (out / "all_tasks.md").write_text(INSTRUCTIONS + "\n\n---\n\n" + "\n\n---\n\n".join(blocks))
    (out / "_key.json").write_text(json.dumps({"labels": labels, "seed": args.seed, "key": key}, indent=1))
    (out / "_key.md").write_text("# HIDDEN KEY - do not show to the judge\n\n| task | " + " | ".join(LETTERS[:len(labels)]) + " |\n|"
                                 + "---|" * (len(labels) + 1) + "\n"
                                 + "\n".join(f"| {t} | " + " | ".join(key[t][L] for L in LETTERS[:len(labels)]) + " |" for t in ids) + "\n")
    print(f"judge pack: {out}  ({len(ids)} tasks, {len(labels)} answers each)")
    print(f"  give the judge: {out / 'all_tasks.md'}  (or JUDGE_INSTRUCTIONS.md + one Rxx.md at a time)")
    print(f"  hidden key:     {out / '_key.json'}")
    print(f"  tally later:    python make_judge_pack.py --tally <verdicts.md> --out {out}")


def tally(args):
    vpath = Path(args.tally).expanduser()
    out = Path(args.out).expanduser() if args.out else vpath.parent
    kp = out / "_key.json"
    if not kp.exists():
        sys.exit(f"key not found: {kp} (pass --out <pack dir>)")
    kj = json.loads(kp.read_text())
    key, labels = kj["key"], kj["labels"]
    text = "\n".join(p.read_text() for p in ([vpath] if vpath.is_file() else sorted(vpath.glob("*.md"))))
    ranks = {lab: [] for lab in labels}
    borda = {lab: 0.0 for lab in labels}
    wins = {a: {b: 0.0 for b in labels} for a in labels}
    crit = {lab: [] for lab in labels}
    seen = []
    for m in re.finditer(r"TASK:\s*(R\d+)(.*?)(?=TASK:\s*R\d+|\Z)", text, re.S):
        t, body = m.group(1), m.group(2)
        if t not in key or t in seen:
            continue
        rk = re.search(r"RANKING:\s*([^\n]+)", body)
        if not rk:
            continue
        seen.append(t)
        tiers = [[x.strip().upper() for x in tier.split("=")] for tier in rk.group(1).split(">")]
        pos, place = {}, 1
        for tier in tiers:
            for L in tier:
                if L in key[t]:
                    pos[key[t][L]] = place + (len(tier) - 1) / 2
            place += len(tier)
        n = len(pos)
        for lab, p in pos.items():
            ranks[lab].append(p)
            borda[lab] += n - p
        for a in pos:
            for b in pos:
                if a != b:
                    wins[a][b] += 1.0 if pos[a] < pos[b] else 0.5 if pos[a] == pos[b] else 0.0
        sc = re.search(r"SCORES:\s*([^\n]+)", body)
        if sc:
            for L, a, b, c in re.findall(r"([A-Z])\s*=\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", sc.group(1)):
                if L in key[t]:
                    crit[key[t][L]].append((float(a), float(b), float(c)))
    if not seen:
        sys.exit("no 'TASK: Rxx ... RANKING: ...' blocks found")
    rows = []
    for lab in labels:
        cs = crit[lab]
        rows.append({"label": lab, "tasks": len(ranks[lab]),
                     "mean_rank": round(statistics.mean(ranks[lab]), 2) if ranks[lab] else None,
                     "borda": borda[lab],
                     "insight": round(statistics.mean(c[0] for c in cs), 2) if cs else None,
                     "prioritisation": round(statistics.mean(c[1] for c in cs), 2) if cs else None,
                     "usefulness": round(statistics.mean(c[2] for c in cs), 2) if cs else None})
    rows.sort(key=lambda r: (r["mean_rank"] is None, r["mean_rank"]))
    md = [f"# Blind judge tally ({len(seen)} tasks: {', '.join(seen)})", "",
          "| label | tasks | mean rank (1 = best) | Borda | insight | prioritisation | usefulness |", "|---|---|---|---|---|---|---|"]
    md += [f"| {r['label']} | {r['tasks']} | {r['mean_rank']} | {r['borda']:.1f} | {r['insight']} | {r['prioritisation']} | {r['usefulness']} |" for r in rows]
    md += ["", "Pairwise wins (row beat column; ties = 0.5):", "", "| | " + " | ".join(labels) + " |", "|---" * (len(labels) + 1) + "|"]
    md += [f"| {a} | " + " | ".join("-" if a == b else f"{wins[a][b]:.1f}" for b in labels) + " |" for a in labels]
    (out / "tally.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    print(f"\nwritten: {out / 'tally.md'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", help="comma-separated result labels to compare (2-8)")
    ap.add_argument("--root", default=str(DEFAULT_RESULTS))
    ap.add_argument("--out")
    ap.add_argument("--tasks", help="subset, e.g. R01,R07")
    ap.add_argument("--seed", default="0", help="shuffle seed (letters are reshuffled per task)")
    ap.add_argument("--with-reference", action="store_true", help="append the gold checklist to each task file")
    ap.add_argument("--tally", help="verdicts file (or dir of .md files) written by the judge")
    args = ap.parse_args()
    if args.tally:
        tally(args)
    elif args.labels:
        build(args)
    else:
        ap.error("give --labels to build a pack, or --tally to score verdicts")


if __name__ == "__main__":
    main()
