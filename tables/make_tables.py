#!/usr/bin/env python3
"""Render the Reddit post's tables as PNGs, in the style of ../charts/make_charts.py.

    python make_tables.py            # render table_NN_*.png from tables.json

Edit numbers in tables.json (cells are the raw markdown: **bold** and `code` are honoured) and re-run.
Winner shading is rule-based (RULES below), so it follows the numbers if they change.
"""
import json
import os
import re
import sys
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
JSON = os.path.join(HERE, "tables.json")
DPI = 200  # 2x
W = 8.4    # inches -> 1680 px

# ---- palette / type: same as charts/make_charts.py (dataviz reference palette, light) ----
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BLUE = "#2a78d6"
ZEBRA = "#f4f3ef"
HILITE = "#e3edf9"  # BLUE at ~12% over SURFACE

plt.rcParams.update({
    "font.family": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "figure.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
})

FOOT = "Apple M5 Ultra Mac Studio, 256 GB · github.com/fireside-labs/m5-ultra-llm-benchmarks"

# Per-table output name, winner rules and key text. Rules:
#   ("colbest", "max"|"min", rows, cols): best among `rows` in each column of `cols`
#   ("rowbest", "max"|"min", row, cols):  best among `cols` in that row
NAMES = ["cold_vs_warm", "qwen_depth", "mtp_dspark", "overnight_agents", "replay_engines", "ltx_video"]
RULES = {
    "qwen_depth": ([("colbest", "max", [0, 1], [1, 2, 3]), ("colbest", "max", [2, 3], [1, 2, 3])],
                   "faster engine at each depth"),
    "overnight_agents": ([("colbest", "max", None, [2])], "most steps/hour"),
    "replay_engines": ([("rowbest", "min", 0, [1, 2]), ("rowbest", "min", 1, [1, 2]),
                        ("rowbest", "max", 2, [1, 2])], "better engine per row"),
    "deepseek_replay": ([("rowbest", "min", r, [1, 3]) for r in range(5)] +
                        [("rowbest", "max", r, [2, 4]) for r in range(4)], "better engine per pair"),
    "ltx_video": ([("colbest", "min", [0, 1, 2, 3], [1]), ("colbest", "min", [4, 5], [1])],
                  "fastest at each resolution"),
}


# ----------------------------------------------------------------- render ---
def clean(cell):
    bold = cell.startswith("**") and cell.endswith("**") and len(cell) > 4
    return cell.strip("*").replace("`", "").replace("**", ""), bold


def number(cell):
    m = re.search(r"-?\d[\d,]*\.?\d*", clean(cell)[0])
    return float(m.group().replace(",", "")) if m else None


def winners(t):
    rules, key = RULES.get(t["name"], ([], None))
    rows, cells = t["rows"], set()
    for kind, sense, sel, cols in rules:
        pick = max if sense == "max" else min
        if kind == "colbest":
            for c in cols:
                cand = [(number(rows[r][c]), r) for r in (sel if sel is not None else range(len(rows)))]
                cand = [x for x in cand if x[0] is not None]
                if cand:
                    best = pick(v for v, _ in cand)
                    if sum(v == best for v, _ in cand) == 1:
                        cells |= {(r, c) for v, r in cand if v == best}
        else:
            cand = [(number(rows[sel][c]), c) for c in cols if number(rows[sel][c]) is not None]
            best = pick(v for v, _ in cand)
            if sum(v == best for v, _ in cand) == 1:
                cells |= {(sel, c) for v, c in cand if v == best}
    return cells, key


def render(t):
    PAD_X, GAP, LEFT = 0.16, 0.10, 0.2       # cell padding, column gap, outer margin (in)
    BODY, HEAD = 10.5, 9.5
    LINE = 0.215                              # inches per text line in a cell
    ncol = len(t["header"])
    fig = plt.figure(figsize=(W, 4), dpi=DPI)
    r = fig.canvas.get_renderer()

    def width(s, size, bold=False):
        tx = fig.text(0, 0, s, fontsize=size, weight="bold" if bold else "normal")
        w = max((tx.get_window_extent(r).width / DPI) if s else 0, 0)
        tx.remove()
        return w

    # wrap long cells, then fit column widths to the content
    avail = W - 2 * LEFT
    maxc = [44 if ncol > 2 else 60] + [30 if ncol > 3 else 42] * (ncol - 1)
    grid = [[clean(c) for c in t["header"]]] + [[clean(c) for c in row] for row in t["rows"]]
    for row in grid:
        for c, (s, b) in enumerate(row):
            row[c] = ("\n".join(textwrap.wrap(s, maxc[c], break_on_hyphens=False)) or s, b)
    need = [max(max(width(l, HEAD if i == 0 else BODY, b or i == 0) for l in s.split("\n"))
                for i, (s, b) in enumerate(col)) + 2 * PAD_X for col in zip(*grid)]
    extra = avail - sum(need)
    if extra > 0:  # label column keeps its size + a little; numbers share the rest
        colw = [need[0] + extra * 0.25] + [w + extra * 0.75 / (ncol - 1) for w in need[1:]]
    else:
        colw = [w * avail / sum(need) for w in need]
    xs = [LEFT]
    for w in colw:
        xs.append(xs[-1] + w)

    hl, key = winners(t)
    heights = [max(s.count("\n") + 1 for s, _ in row) * LINE + 0.17 for row in grid]
    TOP, TITLE_BAND, FOOT_BAND = 0.22, 0.36, 0.38
    H = TOP + TITLE_BAND + sum(heights) + FOOT_BAND
    fig.set_size_inches(W, H)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")

    ax.text(LEFT, TOP, t["title"], ha="left", va="top", fontsize=13.5, weight="bold", color=INK)
    if key and hl:
        kx = W - LEFT - width(key, 8.5)
        ax.text(W - LEFT, TOP + 0.13, key, ha="right", va="center", fontsize=8.5, color=INK2)
        ax.add_patch(FancyBboxPatch((kx - 0.30, TOP + 0.05), 0.20, 0.16, boxstyle="round,pad=0,rounding_size=0.03",
                                    fc=HILITE, ec="none"))
    y = TOP + TITLE_BAND
    for i, row in enumerate(grid):
        h = heights[i]
        if i > 0 and i % 2 == 0:
            ax.add_patch(Rectangle((LEFT, y), avail, h, fc=ZEBRA, ec="none", zorder=0))
        for c, (s, b) in enumerate(row):
            if i > 0 and (i - 1, c) in hl:
                bw = min(colw[c] - 0.08, need[c] + 0.3)
                ax.add_patch(FancyBboxPatch((xs[c + 1] - 0.04 - bw, y + 0.03), bw, h - 0.06,
                                            boxstyle="round,pad=0,rounding_size=0.04", fc=HILITE, ec="none", zorder=1))
            left = c == 0
            ax.text(xs[c] + PAD_X if left else xs[c + 1] - PAD_X, y + h / 2, s,
                    ha="left" if left else "right", va="center_baseline", multialignment="left" if left else "right",
                    fontsize=HEAD if i == 0 else BODY, weight="bold" if (b or i == 0) else "normal",
                    color=INK2 if i == 0 else INK, linespacing=1.35, zorder=2)
        y += h
        ax.plot([LEFT, W - LEFT], [y, y], color=AXIS if i == 0 else GRID, lw=1.0 if i == 0 else 0.6, zorder=3)
    ax.text(LEFT, H - 0.14, FOOT, ha="left", va="bottom", fontsize=7, color=MUTED)

    path = os.path.join(HERE, f"table_{t['n']:02d}_{t['name']}.png")
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    print("wrote", path)


def main():
    for t in json.load(open(JSON, encoding="utf-8")):
        render(t)


if __name__ == "__main__":
    main()
