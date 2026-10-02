#!/usr/bin/env python3
"""Charts for Reddit Part 2. Numbers are the summary values recorded in ~/bench-results/NIGHT2-NOTES.md
(and the blind verdicts it points to); the data-analysis heatmap reads data-eval/blind/verdict.json directly.

Usage:  /Users/loki/bench/.venv/bin/python /Users/loki/bench-results/charts/part2/make_part2_charts.py
Writes  p2_01_*.png ... p2_07_*.png next to this script. Pure file reading - never contacts a server.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import make_charts as mc  # noqa: E402  (palette, rcParams, frame(), helpers)
from make_charts import AQUA, BLUE, GRID, INK, INK2, MUTED, ORANGE, SURFACE, comma, frame, note  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter  # noqa: E402

OUT = os.path.dirname(os.path.abspath(__file__))
mc.OUT = OUT
save = mc.save

QWEN, GLM, DS = "Qwen3.8-Flash-Next 8-bit", "GLM-5.3-Flash 4-bit", "DeepSeek-V4-Flash 0731"
COL = {QWEN: BLUE, GLM: ORANGE, DS: AQUA}  # colour follows the model in every Part 2 chart
SHORT = {QWEN: "Qwen", GLM: "GLM", DS: "DeepSeek"}
HW = "Apple M5 Ultra Mac Studio, 256 GB unified memory, macOS 27.0.1 · oMLX 0.7.0 built from source with custom kernels"
SRC = "Numbers: NIGHT2-NOTES.md in the repo."


def bars(ax, labels, values, colors, fmt="{:g}", width=0.62, top=None):
    xs = range(len(labels))
    ax.bar(xs, values, width=width, color=colors, zorder=3)
    ax.set_xticks(list(xs), labels)
    ax.grid(axis="x", visible=False)
    if top:
        ax.set_ylim(0, top)
    for x, v in zip(xs, values):
        ax.annotate(fmt.format(v), (x, v), xytext=(0, 4), textcoords="offset points", ha="center", va="bottom",
                    fontsize=9, color=INK, weight="bold", zorder=6)


def model_legend(fig, y, models=(QWEN, GLM, DS)):
    handles = [plt.Rectangle((0, 0), 1, 1, fc=COL[m]) for m in models]
    fig.legend(handles, models, loc="upper left", bbox_to_anchor=(0.2 / fig.get_size_inches()[0], y),
               ncol=len(models), handlelength=1.0, columnspacing=1.6)


# ------------------------------------------------------------------- 1 speed ---
def chart1():
    depths = ["10k", "100k", "250k"]
    pre = {QWEN: [3854, 4464, 4235], GLM: [1877, 1879, 1720]}
    dec = {QWEN: [72, 64, 63], GLM: [57, 54, 48]}
    fig, axes = plt.subplots(1, 2, figsize=(9, 5.2))
    w = 0.36
    for ax, data, ttl, f in ((axes[0], pre, "Prefill (reading the prompt), tokens/s", "{:,.0f}"),
                             (axes[1], dec, "Decode (writing the answer), tokens/s", "{:,.0f}")):
        for i, m in enumerate((QWEN, GLM)):
            xs = [k + (i - 0.5) * w for k in range(3)]
            ax.bar(xs, data[m], width=w, color=COL[m], zorder=3)
            for x, v in zip(xs, data[m]):
                ax.annotate(f.format(v), (x, v), xytext=(0, 3), textcoords="offset points", ha="center",
                            va="bottom", fontsize=8, color=INK2)
        ax.set_xticks(range(3), depths)
        ax.set_xlabel("Prompt length")
        ax.set_title(ttl, loc="left", fontsize=10, color=INK, pad=10)
        ax.grid(axis="x", visible=False)
        ax.set_ylim(0, max(max(v) for v in data.values()) * 1.15)
        comma(ax)
    ly = frame(fig, axes, "Qwen reads 2-2.5x faster than GLM and writes ~30% faster at 250k",
               "Same engine build for both, MTP off, cold prompts, 3 reps (medians). GLM uses 18B active "
               "parameters per token vs Qwen's ~6B.",
               f"{HW}\nPrompts: Project Gutenberg novels cut to exact token counts. Temperature 0.\n{SRC}",
               legend_rows=1, ax_titles=True)
    model_legend(fig, ly, (QWEN, GLM))
    save(fig, "p2_01_speed_qwen_vs_glm.png")


# ---------------------------------------------------------------------- 2 1M ---
def chart2():
    rows = [(QWEN + " + YaRN x4", QWEN, 5.3, "6.7 s", "3/3"), (GLM, GLM, 13.0, "19.9 s", "3/3"),
            (DS, DS, 57.2, "44 s", "2/3")]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    ys = list(range(len(rows)))[::-1]
    frame(fig, ax, "Reading 1 million tokens: Qwen 5.3 min, GLM 13 min, DeepSeek 57 min",
          "Cold first read of a 1M-token prompt (Gutenberg novels + 3 hidden vault codes beside decoys). "
          "Labels: next turn in the same conversation (prompt cached) and codes found.",
          f"{HW}\nQwen is trained to 262k; YaRN x4 stretches its positions (repo has the ~40-line oMLX patch). "
          "Needle recall only, not reasoning at 1M. DeepSeek missed the 10% code (answered the decoy).\n"
          "memory_guard_tier custom 244 GB for 1M runs. " + SRC, left=3.0, right=0.4, xlabel_band=0.5)
    ax.set_xlim(0, 62)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    for y, (lab, m, mins, nxt, codes) in zip(ys, rows):
        mc.rbarh(ax, y, mins, 0.58, COL[m])
        txt = f"{mins:g} min   ·   next turn {nxt}   ·   {codes} codes"
        if mins > 40:  # long bar: label inside so it never runs off the right edge
            ax.annotate(txt, (mins, y), xytext=(-12, 0), textcoords="offset points", ha="right", va="center",
                        fontsize=9, color="white", weight="bold", zorder=6)
        else:
            note(ax, mins, y, txt, dx=8, size=9)
    ax.set_yticks(ys, [r[0] for r in rows])
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Minutes to read the 1M-token prompt")
    save(fig, "p2_02_one_million_tokens.png")


# ------------------------------------------------------------- 3 scaling ---
def chart3():
    # prefill seconds = tokens / prefill t/s from the depth runs; 1M from the fresh-server reruns
    # 100k-250k: 50k-step depth curves (3 reps, medians). 300k-1M: night-5 curve run, 1 run per depth on a fresh
    # server (Qwen with YaRN x4). DeepSeek doubling 128k -> 1M on 0.7.0.
    pts = {QWEN: [(100, 22.4), (150, 34.1), (200, 46.3), (250, 59.0), (300, 77.1), (400, 102.6), (500, 133.1),
                  (600, 165.2), (750, 217.2), (1000, 321.4)],
           GLM: [(100, 53.2), (150, 80.9), (200, 111.7), (250, 145.3), (300, 171.2), (400, 241.5), (500, 319.2),
                 (600, 402.1), (750, 537.9), (1000, 780.1)],
           DS: [(128, 134), (256, 357), (512, 1072), (1000, 3434)]}
    alpha = {QWEN: "α 1.15", GLM: "α 1.17", DS: "α 1.58"}
    fig, ax = plt.subplots(figsize=(8, 5.6))
    for m, p in pts.items():
        x, y = zip(*p)
        ax.plot(x, y, color=COL[m], lw=mc.LW, marker="o", ms=mc.MS, mec=SURFACE, mew=mc.RING, zorder=3, label=m)
        note(ax, x[-1], y[-1], f"{SHORT[m]}  {alpha[m]}  ·  {y[-1] / 60:.1f} min", dx=8)
    for a in (ax,):
        a.set_xscale("log")
        a.set_yscale("log")
        a.set_xticks([100, 250, 500, 1000])
        a.xaxis.set_minor_formatter(NullFormatter())
        a.xaxis.set_major_formatter(FuncFormatter(lambda v, _: "1M" if v >= 1000 else f"{v:,.0f}k"))
        mc.log_seconds(a)
    ax.set_xlim(85, 2300)
    ax.set_ylim(15, 6000)
    ax.set_xlabel("Prompt length (log scale)")
    ax.set_ylabel("Time to read the prompt (log scale)")
    frame(fig, ax, "Prefill scaling: DeepSeek's line is steepest (α 1.58), Qwen and GLM stay near-linear",
          "Fit t = c·n^α from 100k up. A straight line on log-log = power law; α 1 is linear, 2 is quadratic.",
          f"{HW}\nPoints: Qwen and GLM 100k-250k every 50k (3 reps), then 300k-1M (1 run each, fresh server; Qwen with YaRN x4, same weights); DeepSeek 128k, 256k, 512k, 1M. Share of prefill from the n² term at 1M: "
          f"Qwen ~34%, GLM ~36%, DeepSeek ~80%.\n{SRC}")
    save(fig, "p2_03_prefill_scaling.png")


# ---------------------------------------------------------------- 4 code ---
def chart4():
    order = (QWEN, GLM, DS)
    panels = [("Conformance test", [12, 11, 10], 12, "{:g}/12"),
              ("“Would I merge it”", [7, 4, 3], 10, "{:g}/10"),
              ("Readability", [6, 4, 7], 10, "{:g}/10")]
    fig, axes = plt.subplots(1, 3, figsize=(9, 4.9), sharey=False)
    for ax, (ttl, vals, top, f) in zip(axes, panels):
        bars(ax, [SHORT[m] for m in order], vals, [COL[m] for m in order], fmt=f, top=top * 1.12)
        ax.set_title(ttl, loc="left", fontsize=10, color=INK, pad=10)
        ax.set_yticks([0, top / 2, top])
    frame(fig, axes, "Blind code review: Qwen's roguelike was the one worth merging",
          "Same 30-milestone TypeScript roguelike, same harness (pi; DeepSeek on its own harness). A reviewer "
          "built each project, wrote a 12-check test and read the code without knowing which model wrote it.",
          "All three finished 30/30 milestones and passed 52-53 of 54 hidden tests. Qwen took 38 min, GLM 64 min.\n"
          "GLM: ~2,200 lines of dead code, can see through walls. DeepSeek: A* not shortest, sight radius off by one, "
          f"comments describing features that don't exist.\n{SRC}", ax_titles=True, wspace=0.35)
    save(fig, "p2_04_blind_code_review.png")


# ------------------------------------------------------------- 5 quality ---
def chart5():
    order = (GLM, QWEN, DS)
    panels = [("Critical thinking\nblind judge, insight /10", [8.2, 6.1, 7.1], 10, "{:g}"),
              ("Pushback\nscore /100", [96.9, 76.0, 99.0], 100, "{:g}"),
              ("Call analysis v2 (hard)\nscore /100", [92.3, 84.1, 71.9], 100, "{:g}"),
              ("Data analysis, false premises\nblind judge /16", [12.5, 12.0, 11.3], 16, "{:g}")]
    fig, axes = plt.subplots(1, 4, figsize=(10, 5.1))
    for ax, (ttl, vals, top, f) in zip(axes, panels):
        bars(ax, [SHORT[m] for m in order], vals, [COL[m] for m in order], fmt=f, top=top * 1.12, width=0.7)
        ax.set_title(ttl, loc="left", fontsize=9.5, color=INK, pad=10, linespacing=1.3)
        ax.set_yticks([0, top / 2, top])
        ax.tick_params(axis="x", labelsize=8.5)
    frame(fig, axes, "The judgment tests: GLM leads three of four, DeepSeek wins pushback",
          "All synthetic and self-contained. GLM at max/high reasoning, Qwen at xhigh/medium. DeepSeek ran at "
          "oMLX's default low effort except data analysis (high x2 + low x1, averaged).",
          "Pushback: DeepSeek and GLM never caved to a wrong critique or pressure; Qwen caved 17% of the time. "
          "Call analysis: DeepSeek looped on 2 of 16 calls (75.2 at max effort).\nData analysis: 2-3 runs each; the "
          f"gap is within noise. 1-2 runs per test overall.\n{SRC}", legend_rows=1, ax_titles=True, wspace=0.45, left=0.6)
    save(fig, "p2_05_judgment_scorecard.png")


# ------------------------------------------------------------ 6 batching ---
def chart6():
    n = [1, 2, 4, 8]
    data = {"Short prompts (1k tokens)": {QWEN: [53.1, 71.1, 92.5, 118.4], GLM: [55.8, 46.4, 66.2, 85.9]},
            "Transcript-size prompts (20k tokens)": {QWEN: [37.1, 39.0, 42.3, 51.3], GLM: [26.2, 22.4, 24.0, 27.2]}}
    fig, axes = plt.subplots(1, 2, figsize=(9, 5.2), sharey=True)
    for ax, (ttl, d) in zip(axes, data.items()):
        for m, ys in d.items():
            ax.plot(n, ys, color=COL[m], lw=mc.LW, marker="o", ms=mc.MS, mec=SURFACE, mew=mc.RING, zorder=3)
            note(ax, n[-1], ys[-1], f"{ys[-1] / ys[0]:.1f}x", dx=8)
        ax.set_xscale("log", base=2)
        ax.set_xticks(n, [str(k) for k in n])
        ax.set_xlim(0.8, 11)
        ax.set_ylim(0, 135)
        ax.set_xlabel("Requests in parallel")
        ax.set_title(ttl, loc="left", fontsize=10, color=INK, pad=10)
    axes[0].set_ylabel("Total output, tokens/s")
    ly = frame(fig, axes, "Batching helps short requests, barely helps long ones",
               "Total tokens/s across all parallel requests, 512 output tokens each, unique cold prompts. "
               "MTP off (it only runs one request at a time). Labels: gain at 8 vs 1.",
               f"{HW}\nBoth models run on oMLX's vision-language engine (the text-only engine rejects them). "
               f"GLM at reasoning low.\nLong prompts are compute-bound in prefill: for volume, add machines, not "
               f"concurrency. {SRC}", legend_rows=1, ax_titles=True)
    model_legend(fig, ly, (QWEN, GLM))
    save(fig, "p2_06_batching.png")


# ---------------------------------------------------------- 7 data eval ---
def chart7():
    root = os.path.expanduser("~/bench-results/data-eval/blind")
    verdict = {v["label"]: v for v in json.load(open(os.path.join(root, "verdict.json")))}
    key = json.load(open(os.path.join(root, "_key.json")))
    names = {"glm53": "GLM run 1", "glm53_r2": "GLM run 2", "qwen38": "Qwen run 1", "qwen38_r2": "Qwen run 2",
             "dsv4": "DeepSeek high, run 1", "dsv4_r2": "DeepSeek high, run 2", "dsv4low": "DeepSeek low"}
    inv = {v: k for k, v in key.items()}
    runs = list(names)
    items = ["Dedupe\ntransfers", "Q2 'drop' =\nlogging change", "Script lift =\nSimpson's", "CSAT only\nafter resolved",
             "Bayview\nis UTC", "Best clinic\n(n, topic mix)", "6-min cap\nconfounded", "Other real\nissues"]
    grid = [verdict[inv[r]]["items"] for r in runs]
    fig, ax = plt.subplots(figsize=(10, 6.2))
    frame(fig, ax, "Data analysis with false premises: everyone caught the big traps, only GLM adjusted for topic",
          "Synthetic clinic call log (6,637 rows) + a director's memo built on 7 false premises. Models ran pandas "
          "in a sandbox, wrote a memo, then got pressured for a number. Blind judge, 0-2 per item.",
          "Pressure turn: “fill in: the new script improved resolution by __ points.” HOLD = refused the false "
          "number; PARTIAL = offered ~1 point with caveats. Nobody gave the naive +5.9.\nTotal = items + "
          "hallucination penalty (−1 per wrong number). Temp 0.6. GLM high, Qwen medium effort.\n"
          "Source: data-eval/blind/verdict.json", legend_rows=2, left=1.9, right=1.9, xlabel_band=0.15)
    cmap = ListedColormap(["#f3d9cc", "#f3ead0", "#cfe9dc"])
    ax.imshow(grid, cmap=cmap, vmin=-0.5, vmax=2.5, aspect="auto")
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    for i, row in enumerate(grid):
        for j, v in enumerate(row):
            ax.text(j, i, str(v), ha="center", va="center", fontsize=11, color=INK, weight="bold" if v == 2 else None)
        v = verdict[inv[runs[i]]]
        ax.text(len(items) - 0.35, i, f"{v['total']}/16   {v['pressure']}", ha="left", va="center", fontsize=9.5,
                color=INK, weight="bold")
    ax.set_xticks(range(len(items)), items, fontsize=8)
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(runs)), [names[r] for r in runs])
    for t, r in zip(ax.get_yticklabels(), runs):
        t.set_color(COL[GLM] if r.startswith("glm") else COL[QWEN] if r.startswith("qwen") else "#12805a")
    ax.set_xticks([x + 0.5 for x in range(len(items) - 1)], minor=True)
    ax.set_yticks([y + 0.5 for y in range(len(runs) - 1)], minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=3)
    ax.tick_params(which="minor", length=0)
    ax.text(len(items) - 0.35, -0.85, "Total, pressure", ha="left", va="center", fontsize=8, color=MUTED)
    save(fig, "p2_07_data_analysis.png")


if __name__ == "__main__":
    for fn in (chart1, chart2, chart3, chart4, chart5, chart6, chart7):
        fn()
