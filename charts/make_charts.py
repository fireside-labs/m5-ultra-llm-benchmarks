#!/usr/bin/env python3
"""Regenerate every benchmark chart from the raw JSONL files.

Usage:  python charts/make_charts.py      (from the repo root; BENCH_RESULTS overrides the input dir)

Reads   results/longctx/*.jsonl, results/mtp/*.jsonl (labels starting "test-" ignored;
        the newest file wins when a label appears in more than one file) and the newest
        results/replay/*-qwen-replay-{omlx,llama}.jsonl
Writes  01_*.png ... 09_*.png next to this script, at 2x (figsize in inches x 200 dpi).
Pure CPU / file reading - never contacts a server.
"""
import glob
import hashlib
import json
import os
import statistics
import textwrap
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter  # noqa: E402

ROOT = os.environ.get("BENCH_RESULTS", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results"))
OUT = os.path.dirname(os.path.abspath(__file__))
DPI = 200  # 2x

# ---------------------------------------------------------------- palette ---
# dataviz reference palette (light). Slots 1-3 are validated all-pairs for CVD and normal vision.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
C_LLAMA, C_OMLX, C_MTP = BLUE, ORANGE, AQUA  # colour follows the engine in every depth chart

LW = 1.5    # 2 px line at 1x
MS = 6.5    # ~9 px marker
RING = 1.5  # 2 px surface ring round markers

plt.rcParams.update({
    "font.family": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 10,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS,
    "axes.linewidth": 0.75,
    "axes.labelcolor": INK2,
    "axes.labelsize": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.axisbelow": True,
    "grid.color": GRID,
    "grid.linewidth": 0.75,
    "grid.linestyle": "-",
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "xtick.labelcolor": INK2,
    "ytick.labelcolor": INK2,
    "xtick.major.size": 0,
    "ytick.major.size": 0,
    "xtick.minor.size": 0,
    "ytick.minor.size": 0,
    "legend.frameon": False,
    "legend.fontsize": 9,
    "legend.labelcolor": INK2,
})

HW = ("Apple M5 Ultra Mac Studio, 256 GB unified memory, macOS 27.0.1 · llama.cpp 19e28a2 (Metal, flash attention on, "
      "batch/ubatch 2048) · oMLX 0.7.0rc1")
PROMPTS = ("Prompts: Project Gutenberg novels cut to exact token counts. Cold = unique prefix, nothing cached; "
           "warm = same conversation continued with 64 new tokens. Temperature 0. Medians across reps.")


# ------------------------------------------------------------------- data ---
def read_jsonl(path):
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def latest_by_label(subdir):
    """label → (path, rows), keeping the newest file (filenames start with a timestamp)."""
    files = {}
    for path in sorted(glob.glob(os.path.join(ROOT, subdir, "*.jsonl"))):
        rows = read_jsonl(path)
        for lab in {r.get("label") for r in rows if r.get("label")}:
            if not lab.startswith("test-"):
                files[lab] = (path, rows)
    return files


LONG = latest_by_label("longctx")
MTP = latest_by_label("mtp")


def by_depth(label, kind, field, step=None, src=None):
    """{depth: median(field)} over rows of this type (and warm step size)."""
    rows = src if src is not None else LONG[label][1]
    acc = defaultdict(list)
    for r in rows:
        if r.get("type") == kind and (step is None or r.get("step") == step):
            acc[r["depth"]].append(r[field])
    return {d: statistics.median(v) for d, v in sorted(acc.items())}


def xy(d):
    ks = sorted(d)
    return [k / 1000 for k in ks], [d[k] for k in ks]


def fname(label):
    return os.path.basename(LONG[label][0])


# ----------------------------------------------------------------- layout ---
def fill_no_orphan(text, width):
    """textwrap.fill, but never leave a lone word or short stub (< 25 chars) on the last line."""
    w = width
    lines = textwrap.wrap(text, w, break_on_hyphens=False)
    while len(lines) > 1 and (" " not in lines[-1] or len(lines[-1]) < 25) and w > width * 0.7:
        w -= 1
        lines = textwrap.wrap(text, w, break_on_hyphens=False)
    return "\n".join(lines)


def wrap(text, width):
    return "\n".join(fill_no_orphan(p, width) for p in text.split("\n"))


def frame(fig, axes, title, subtitle, foot, legend_rows=0, ax_titles=False, left=0.95, right=0.3,
          wspace=0.3, xlabel_band=0.62):
    """Fixed-inch header (title, subtitle, optional figure legend) and footer (source notes)."""
    W, H = fig.get_size_inches()
    title = wrap(title, int(W * 9.6))
    subtitle = wrap(subtitle, int(W * 14.8))
    foot = wrap(foot, int(W * 19.3))
    y = H - 0.22
    fig.text(0.2 / W, y / H, title, ha="left", va="top", fontsize=13.5, weight="bold", color=INK, linespacing=1.2)
    y -= 0.25 * (title.count("\n") + 1) + 0.1
    fig.text(0.2 / W, y / H, subtitle, ha="left", va="top", fontsize=9.5, color=INK2, linespacing=1.4)
    y -= 0.19 * (subtitle.count("\n") + 1) + 0.12
    legend_y = y / H
    y -= 0.21 * legend_rows + (0.08 if legend_rows else 0)
    y -= 0.32 if ax_titles else 0.12
    n_foot = foot.count("\n") + 1
    fig.text(0.2 / W, 0.14 / H, foot, ha="left", va="bottom", fontsize=7, color=MUTED, linespacing=1.45)
    bottom = 0.14 + 0.145 * n_foot + 0.12 + xlabel_band
    fig.subplots_adjust(top=y / H, bottom=bottom / H, left=left / W, right=1 - right / W, wspace=wspace)
    return legend_y


def line(ax, d, color, label, marker="o", hollow=False, z=3):
    x, y = xy(d)
    ax.plot(x, y, color=color, lw=LW, solid_capstyle="round", solid_joinstyle="round", zorder=z,
            marker=marker, ms=MS, mfc=SURFACE if hollow else color, mec=color if hollow else SURFACE,
            mew=RING, label=label)
    return x, y


def note(ax, x, y, text, dx=6, dy=0, ha="left", va="center", size=8.5):
    ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points", ha=ha, va=va,
                fontsize=size, color=INK2, zorder=6)


def kfmt(ax):
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}k" if v else "0"))


def comma(ax, axis="y"):
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))


def log_seconds(ax):
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(LogLocator(base=10, subs=(1.0, 3.0)))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f} s" if v >= 1 else f"{v:g} s"))


def rhalf(v):
    return int(v + 0.5)


def px_per_unit(ax):
    (x0, y0), (x1, y1) = ax.transData.transform([(0, 0), (1, 1)])
    return abs(x1 - x0), abs(y1 - y0)


def rbarh(ax, y, width, height, color, r_px=8):
    """Horizontal bar: 4 px (x2) rounded data-end, square at the baseline. Call after layout + limits."""
    ppx, ppy = px_per_unit(ax)
    r = min(r_px / ppx, width / 2)
    ax.add_patch(FancyBboxPatch((0, y - height / 2), width, height, boxstyle=f"round,pad=0,rounding_size={r}",
                                mutation_aspect=ppx / ppy, fc=color, ec="none", zorder=3))
    ax.add_patch(Rectangle((0, y - height / 2), max(width - r, 0), height, fc=color, ec="none", zorder=3))


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    print("wrote", path)


# ----------------------------------------------------------------- labels ---
QL, QO, QM = "qwen-q8-llama", "qwen-oq8e-omlx", "qwen-oq8e-omlx-mtp-on"
DL = "dsv4v-q8kxl-llama-prelim"
DK_SHORT, DK_DEPTH = "ds0731-oq4e-omlxsrc-short", "ds0731-oq4e-omlxsrc-depth"
DK_HOT, DK_NOC = "ds0731-oq4e-omlxsrc-hot32", "ds0731-oq4e-omlxsrc-nocache"
DH, DH_MTP = "ds0731-oq4e-omlx-short", "ds0731-oq4e-omlx-short-mtp"

QWEN_SETUP = ("Qwen3.8-Flash-Next · llama.cpp Q8_0 vs oMLX oQ8e (Homebrew build, block cache on, MTP off).\n"
              "Both final runs: 3 reps on a quiet machine.")
DS_SETUP = ("DeepSeek-V4-Flash · llama.cpp: Vision-Exp UD-Q8_K_XL (PRELIMINARY, 1 rep) vs oMLX kernel build: "
            "0731 oQ4e.")
DS_CAVEAT = ("Different model variant (Vision-Exp vs 0731) and quant (8-bit vs 4-bit): this compares "
             "engine + quant, not engine alone.")
DS_BUILD = ('oMLX "kernel build" = built from source with OMLX_WITH_CUSTOM_KERNEL=1. '
            "llama.cpp run ended at 500k (planned to 1M).")


# ------------------------------------------------------------- the charts ---
def chart1():
    ll, om = by_depth(QL, "cold", "prefill_tps"), by_depth(QO, "cold", "prefill_tps")
    fig, ax = plt.subplots(figsize=(8, 5.4))
    x1, y1 = line(ax, ll, C_LLAMA, "llama.cpp Q8_0")
    x2, y2 = line(ax, om, C_OMLX, "oMLX oQ8e")
    note(ax, x1[-1], y1[-1], f"llama.cpp  {y1[-1]:,.0f} t/s", dy=-6)
    note(ax, x2[-1], y2[-1], f"oMLX  {y2[-1]:,.0f} t/s", dy=6)
    ax.set_xlim(0, 330)
    ax.set_ylim(0, max(y1 + y2) * 1.15)
    kfmt(ax)
    comma(ax)
    ax.set_xlabel("Context depth (prompt tokens, cold)")
    ax.set_ylabel("Prefill speed (tokens/s)")
    ax.legend(loc="lower left", ncol=2)
    lead, lead0 = y2[-1] / y1[-1], y2[0] / y1[0]
    frame(fig, ax, f"Qwen prefill: oMLX leads at every depth, from {(lead0 - 1) * 100:.0f}% at 10k to "
                   f"{(lead - 1) * 100:.0f}% at 250k",
          QWEN_SETUP + "\nCold prefill = prompt tokens / time to first token, nothing cached.",
          f"{HW}\n{PROMPTS}\nllama.cpp rep 0 at 10k was a warm-up outlier ({LONG[QL][1][1]['prefill_tps']:,.0f} t/s); "
          f"median of 3 shown.\n"
          f"Source: {fname(QL)}, {fname(QO)}")
    save(fig, "01_qwen_prefill_vs_depth.png")


def chart2():
    ll, om, mt = (by_depth(k, "cold", "decode_tps") for k in (QL, QO, QM))
    fig, ax = plt.subplots(figsize=(8, 5.4))
    x1, y1 = line(ax, ll, C_LLAMA, "llama.cpp Q8_0")
    x2, y2 = line(ax, om, C_OMLX, "oMLX oQ8e, MTP off")
    x3, y3 = line(ax, mt, C_MTP, "oMLX oQ8e, MTP on")
    note(ax, x1[-1], y1[-1], f"llama.cpp  {y1[-1]:.1f} t/s")
    note(ax, x2[-1], y2[-1], f"oMLX  {y2[-1]:.1f} t/s  ({y2[-1] / y1[-1]:.1f}x)")
    note(ax, x3[-1], y3[-1], f"oMLX + MTP  {y3[-1]:.1f} t/s  ({y3[-1] / y1[-1]:.1f}x)")
    ax.set_xlim(0, 350)
    ax.set_ylim(0, max(y3) * 1.18)
    kfmt(ax)
    ax.set_xlabel("Context depth (prompt tokens)")
    ax.set_ylabel("Decode speed (tokens/s)")
    ax.legend(loc="upper right")
    w64 = by_depth(QO, "warm", "decode_tps", 64)[250000] / by_depth(QL, "warm", "decode_tps", 64)[250000]
    frame(fig, ax, f"Qwen decode at 250k: oMLX {y2[-1] / y1[-1]:.1f}x faster; llama.cpp loses "
                   f"{(1 - y1[-1] / y1[0]) * 100:.0f}% of its speed",
          QWEN_SETUP + f"\nDecode of up to 256 tokens after a cold prompt. On warm agent steps at 250k the gap is "
                       f"{w64:.1f}x.",
          f"{HW}\n{PROMPTS}\nMTP on = Lightning MTP (depth 3); 3 reps, quiet machine.\n"
          f"Source: {fname(QL)}, {fname(QO)}, {fname(QM)}")
    save(fig, "02_qwen_decode_vs_depth.png")


def chart3():
    lc, lw = by_depth(QL, "cold", "ttft_s"), by_depth(QL, "warm", "ttft_s", 64)
    oc, ow = by_depth(QO, "cold", "ttft_s"), by_depth(QO, "warm", "ttft_s", 64)
    fig, ax = plt.subplots(figsize=(8, 5.6))
    xa, ya = line(ax, lc, C_LLAMA, "llama.cpp, cold", marker="s", hollow=True)
    xb, yb = line(ax, oc, C_OMLX, "oMLX, cold", marker="s", hollow=True)
    xc, yc = line(ax, lw, C_LLAMA, "llama.cpp, warm step")
    xd, yd = line(ax, ow, C_OMLX, "oMLX, warm step")
    log_seconds(ax)
    ax.set_ylim(0.2, 700)
    ax.set_xlim(0, 345)
    kfmt(ax)
    note(ax, xa[-1], ya[-1], f"cold: {ya[-1]:.0f} s (llama.cpp)", dy=6)
    note(ax, xb[-1], yb[-1], f"cold: {yb[-1]:.0f} s (oMLX)", dy=-6)
    note(ax, xd[-1], yd[-1], f"warm: {yd[-1]:.1f} s (oMLX)")
    note(ax, xc[-1], yc[-1], f"warm: {yc[-1]:.2f} s (llama.cpp)")
    ax.set_xlabel("Context depth (tokens already in the conversation)")
    ax.set_ylabel("Time to first token (seconds, log scale)")
    ax.legend(loc="upper left", ncol=2)
    so = (yd[-1] - yd[0]) / (xd[-1] - xd[0]) * 1000
    sl = (yc[-1] - yc[0]) / (xc[-1] - xc[0]) * 1000
    frame(fig, ax, f"Pay prefill once: at 250k a warm step starts in {yc[-1]:.2f} s, not {ya[-1]:.0f} s",
          QWEN_SETUP + f"\nHollow squares = cold prompt; filled circles = warm step (+64 tokens). oMLX warm steps "
                       f"grow ~{so:.0f} ms per 1k tokens of context, llama.cpp ~{sl:.1f} ms.",
          f"{HW}\n{PROMPTS}\nSource: {fname(QL)}, {fname(QO)}")
    save(fig, "03_qwen_warm_vs_cold_ttft.png")


def ds_omlx(field, kind="cold", step=None):
    d = by_depth(DK_SHORT, kind, field, step)
    d.update(by_depth(DK_DEPTH, kind, field, step))
    return d


def chart4():
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.5, 5.8))
    for ax, field, ylab, name in ((a1, "prefill_tps", "Cold prefill (tokens/s)", "Prefill"),
                                  (a2, "decode_tps", "Decode (tokens/s)", "Decode")):
        ll, om = by_depth(DL, "cold", field), ds_omlx(field)
        x1, y1 = line(ax, ll, C_LLAMA, "llama.cpp Vision-Exp UD-Q8_K_XL (prelim.)")
        x2, y2 = line(ax, om, C_OMLX, "oMLX kernel build, 0731 oQ4e")
        ax.set_ylim(0, max(y1 + y2) * 1.18)
        ax.set_xlim(0, 540)
        kfmt(ax)
        comma(ax)
        ax.set_xlabel("Context depth (prompt tokens)")
        ax.set_ylabel(ylab)
        fmt = "{:,.0f}" if field == "prefill_tps" else "{:.1f}"
        for xs, ys in ((x1, y1), (x2, y2)):
            note(ax, xs[-1], ys[-1], fmt.format(ys[-1]), dx=0, dy=9, ha="center", va="bottom")
        ax.set_title(name, loc="left", fontsize=10.5, color=INK, weight="bold")
    ly = frame(fig, (a1, a2), "DeepSeek: oMLX (4-bit) beats llama.cpp (8-bit) at every depth both engines ran",
               DS_SETUP + "\n" + DS_CAVEAT,
               f"{HW}\n{PROMPTS}\n{DS_BUILD} oMLX: 1k-10k = 2 reps, 50k-200k = 1 rep; the kernel-build long run "
               f"stopped at 200k.\nSource: {fname(DL)}, {fname(DK_SHORT)}, {fname(DK_DEPTH)}",
               legend_rows=1, ax_titles=True, wspace=0.32)
    h, lab = a1.get_legend_handles_labels()
    fig.legend(h, lab, loc="upper left", bbox_to_anchor=(0.2 / 8.5, ly), ncol=2, borderaxespad=0)
    save(fig, "04_deepseek_prefill_decode_vs_depth.png")


def chart5():
    ll = by_depth(DL, "warm", "ttft_s", 64)
    om = ds_omlx("ttft_s", "warm", 64)
    om.pop(1000, None)  # at 1k oMLX never hit its block cache (cached_tokens=0): warm == full re-prefill
    hot = by_depth(DK_HOT, "warm", "ttft_s", 64)
    fig, ax = plt.subplots(figsize=(8, 5.6))
    x1, y1 = line(ax, ll, C_LLAMA, "llama.cpp Vision-Exp Q8_K_XL (prelim.)")
    x2, y2 = line(ax, om, C_OMLX, "oMLX kernel build, 0731 oQ4e")
    hx, hy = xy(hot)
    ax.plot(hx, hy, ls="none", marker="o", ms=MS + 6, mfc="none", mec=INK2, mew=1.0, zorder=4,
            label="oMLX + 32 GB hot cache (same curve)")
    n = len(x2)
    mx, my = sum(x2) / n, sum(y2) / n
    slope = sum((a - mx) * (b - my) for a, b in zip(x2, y2)) / sum((a - mx) ** 2 for a in x2)
    icpt = my - slope * mx
    ax.plot([0, 520], [icpt, icpt + slope * 520], color=MUTED, lw=0.75, zorder=2)
    ax.text(330, icpt + slope * 330 - 2.2, f"oMLX linear fit: +{slope * 1000:.0f} ms per 1k tokens\n"
                                           f"(would be ~{icpt + slope * 400:.0f} s at 400k if the trend holds)",
            ha="left", va="top", fontsize=8.5, color=INK2)
    note(ax, x1[-1], y1[-1], f"{y1[-1]:.2f} s", dx=0, dy=9, ha="center", va="bottom")
    note(ax, x2[-1], y2[-1], f"{y2[-1]:.1f} s", dx=12)
    ax.set_xlim(0, 540)
    ax.set_ylim(0, 25)
    kfmt(ax)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g} s"))
    ax.set_xlabel("Context depth (tokens already in the conversation)")
    ax.set_ylabel("Warm-step time to first token (s)")
    ax.legend(loc="upper left")
    hot_dev = max(abs(hot[d] / om[d] - 1) for d in hot) * 100
    noc = by_depth(DK_NOC, "warm", "ttft_s", 64)
    frame(fig, ax, f"DeepSeek warm step: llama.cpp <{max(y1) + 0.05:.1f} s to 500k, oMLX +{slope * 1000:.0f} ms "
                   f"per 1k tokens",
          DS_SETUP + "\nWarm step = same conversation + 64 new tokens. A 32 GB hot cache did not change the oMLX "
                     f"curve (within {hot_dev:.0f}%, i.e. run-to-run noise).",
          f"{HW}\n{PROMPTS}\n{DS_CAVEAT} {DS_BUILD} With the oMLX block cache off the warm step re-prefills "
          f"everything ({noc[50000]:.0f}\u00a0s at 50k, {noc[100000]:.0f}\u00a0s at 100k). oMLX 1k point omitted: no cache hit "
          f"at that size.\nSource: {fname(DL)}, {fname(DK_SHORT)}, {fname(DK_DEPTH)}, {fname(DK_HOT)}, {fname(DK_NOC)}")
    save(fig, "05_deepseek_warm_ttft_vs_depth.png")


def ratio(cold, warm):
    return {d: cold[d] / warm[d] for d in cold if d in warm}


def chart6():
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.5, 5.8), sharey=True)
    q_l = ratio(by_depth(QL, "cold", "ttft_s"), by_depth(QL, "warm", "ttft_s", 64))
    q_o = ratio(by_depth(QO, "cold", "ttft_s"), by_depth(QO, "warm", "ttft_s", 64))
    dcl, dwl = by_depth(DL, "cold", "ttft_s"), by_depth(DL, "warm", "ttft_s", 64)
    d_l = ratio(dcl, dwl)
    d_o = ratio(ds_omlx("ttft_s"), ds_omlx("ttft_s", "warm", 64))
    d_o.pop(1000, None)
    for ax, ll, om, name, xmax in ((a1, q_l, q_o, "Qwen3.8-Flash-Next", 290), (a2, d_l, d_o, "DeepSeek-V4-Flash", 560)):
        x1, y1 = line(ax, ll, C_LLAMA, "llama.cpp")
        x2, y2 = line(ax, om, C_OMLX, "oMLX")
        ax.set_yscale("log")
        ax.set_ylim(1, 3000)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}x"))
        ax.yaxis.set_minor_formatter(NullFormatter())
        ax.set_xlim(0, xmax)
        kfmt(ax)
        ax.set_xlabel("Context depth (tokens)")
        ax.set_title(name, loc="left", fontsize=10.5, color=INK, weight="bold")
        note(ax, x1[-1], y1[-1], f"{y1[-1]:,.0f}x", dx=0, dy=9, ha="center", va="bottom")
        note(ax, x2[-1], y2[-1], f"{y2[-1]:,.0f}x", dx=0, dy=-9, ha="center", va="top")
    a1.set_ylabel("Cold TTFT ÷ warm-step TTFT (log scale)")
    a2.annotate(f"400k: {dcl[400000]:,.0f} s cold\nvs {dwl[400000]:.2f} s warm", (400, d_l[400000]),
                xytext=(0, -34), textcoords="offset points", ha="center", va="top", fontsize=8.5, color=INK2,
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.75, shrinkA=2, shrinkB=5))
    ly = frame(fig, (a1, a2), f"Continuing a conversation starts up to {max(d_l.values()):,.0f}x faster than "
                              f"re-sending it cold",
               "How many times faster a warm 64-token agent step starts than a cold prompt of the same depth. "
               "Higher = better cache reuse.",
               f"{HW}\n{PROMPTS}\nQwen oMLX = oQ8e Homebrew build (3 reps). DeepSeek llama.cpp = Vision-Exp "
               f"UD-Q8_K_XL (preliminary, 1 rep); DeepSeek oMLX = 0731 oQ4e kernel build.\nSource: {fname(QL)}, "
               f"{fname(QO)}, {fname(DL)}, {fname(DK_SHORT)}, {fname(DK_DEPTH)}",
               legend_rows=1, ax_titles=True, wspace=0.08)
    h = [Line2D([], [], color=c, lw=LW, marker="o", ms=MS, mec=SURFACE, mew=RING) for c in (C_LLAMA, C_OMLX)]
    fig.legend(h, ["llama.cpp", "oMLX"], loc="upper left", bbox_to_anchor=(0.2 / 8.5, ly), ncol=2, borderaxespad=0)
    save(fig, "06_cold_vs_warm_ttft_ratio.png")


TASKS = ["code", "prose", "reasoning", "json", "summary_8k"]


def mtp_stats(label):
    dec, content = defaultdict(list), defaultdict(list)
    for r in MTP[label][1]:
        if r.get("prompt") is None:
            continue
        dec[r["prompt"]].append(r["decode_tps"])
        content[r["prompt"]].append(hashlib.md5((r.get("content") or "").encode()).hexdigest())
    return {k: statistics.median(v) for k, v in dec.items()}, content


def chart7():
    pairs = [("Qwen MTP, temp 0", "qwen-omlx-mtp-off", "qwen-omlx-mtp-on", BLUE),
             ("Qwen MTP, temp 1.0 / top-k 20 / top-p 0.95", "qwen-omlx-mtp-off-sampled", "qwen-omlx-mtp-on-sampled",
              ORANGE),
             ("DeepSeek-0731 DSpark, temp 0", "ds0731-omlx-dspark-off", "ds0731-omlx-dspark-on", AQUA)]
    data = []
    for name, off, on, col in pairs:
        d_off, c_off = mtp_stats(off)
        d_on, c_on = mtp_stats(on)
        data.append(dict(name=name, col=col, sp={t: d_on[t] / d_off[t] for t in TASKS},
                         same={t: c_off[t][0] == c_on[t][0] for t in TASKS},
                         off_reps_same=all(len(set(c_off[t])) == 1 for t in TASKS)))
    ds_sp, q_sp = data[2]["sp"], data[0]["sp"]
    fig, ax = plt.subplots(figsize=(8, 6.4))
    sampled_note = (" The temp-1.0 MTP-off run returned identical text on every rep, so sampling may not have been "
                    "applied to it; treat the orange bars with caution." if data[1]["off_reps_same"] else "")
    ly = frame(fig, ax, f"MTP roughly doubles Qwen decode; DSpark: up to {max(ds_sp.values()):.2f}x, "
                        f"identical output",
               "oMLX 0.7.0rc1 Homebrew build · Qwen3.8-Flash-Next oQ8e, DeepSeek-V4-Flash-0731 oQ4e · short prompts, "
               "512-token completions.\nPredictable text gains most (json, reasoning, code); prose gains least "
               f"(Qwen {q_sp['prose']:.2f}x, DSpark {ds_sp['prose']:.2f}x).",
               f"{HW}\nSpeedup = median decode t/s with speculation on ÷ off (2 reps; sampled runs 3 reps). "
               "'Identical' compares the rep-0 text of on vs off. DSpark on/off text is byte-identical on every task. "
               "Qwen MTP on/off diverges early on all but json; the Qwen 'temp 0' requests sent no temperature field "
               "(server default), and MTP-on summary_8k differed between its two reps." + sampled_note +
               "\nSource: results/mtp/ " + ", ".join(os.path.basename(MTP[l][0]) for _, a, b, _ in pairs
                                                              for l in (a, b)),
               legend_rows=1, left=1.05, right=1.55, xlabel_band=0.55)
    fig.legend([Rectangle((0, 0), 1, 1, fc=d["col"]) for d in data], [d["name"] for d in data], loc="upper left",
               bbox_to_anchor=(0.2 / 8, ly), ncol=3, handlelength=1.0, fontsize=8.5, borderaxespad=0,
               columnspacing=1.2)
    ax.set_xlim(0, 2.6)
    ax.set_ylim(len(TASKS) - 0.45, -0.55)
    ppx, ppy = px_per_unit(ax)
    bh = min(0.24, 48 / ppy)  # <= 24 px at 1x
    gap = 4 / ppy             # 2 px surface gap at 1x
    for i, d in enumerate(data):
        for j, t in enumerate(TASKS):
            y = j + (i - 1) * (bh + gap)
            rbarh(ax, y, d["sp"][t], bh, d["col"])
            ax.text(d["sp"][t] + 0.025, y, f"{d['sp'][t]:.2f}x", va="center", fontsize=8, color=INK2)
    ax.axvline(1.0, color=INK2, lw=0.75, zorder=4)
    ax.set_yticks(range(len(TASKS)))
    ax.set_yticklabels([t.replace("_", " ") for t in TASKS], color=INK)
    ax.grid(axis="y", visible=False)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.1f}x"))
    ax.set_xlabel("Decode speedup, speculation on ÷ off (1.0x = no gain)")
    tr = ax.get_yaxis_transform()
    ax.text(1.03, -0.5, "Same text as\nspec off?", transform=tr, ha="left", va="bottom", fontsize=8, color=INK,
            weight="bold")
    for j, t in enumerate(TASKS):
        ax.text(1.03, j, f"DSpark: {'yes' if data[2]['same'][t] else 'NO'}\n"
                         f"Qwen temp 0: {'yes' if data[0]['same'][t] else 'no'}",
                transform=tr, ha="left", va="center", fontsize=8, color=INK2, linespacing=1.4)
    save(fig, "07_mtp_dspark_speedup_by_task.png")


def chart8():
    # The ubatch-512 figure is the first (superseded) llama.cpp run under the same label (19:08); the run was
    # restarted with ubatch 2048 at 19:13. ubatch is not recorded in the JSONL itself.
    first = sorted(glob.glob(os.path.join(ROOT, "longctx", f"*-{DL}.jsonl")))[0]
    ub512 = read_jsonl(first)
    p512 = by_depth(DL, "cold", "prefill_tps", src=ub512)[10000]
    d512 = by_depth(DL, "cold", "decode_tps", src=ub512)[10000]
    p2048, d2048 = by_depth(DL, "cold", "prefill_tps")[10000], by_depth(DL, "cold", "decode_tps")[10000]
    ph, dh = by_depth(DH, "cold", "prefill_tps")[10000], by_depth(DH, "cold", "decode_tps")[10000]
    pk, dk = by_depth(DK_SHORT, "cold", "prefill_tps")[10000], by_depth(DK_SHORT, "cold", "decode_tps")[10000]
    dm = by_depth(DH_MTP, "cold", "decode_tps")[10000]
    code_on = mtp_stats("ds0731-omlx-dspark-on")[0]["code"]
    pre = [("llama.cpp, ubatch 512", p512, C_LLAMA), ("llama.cpp, ubatch 2048", p2048, C_LLAMA),
           ("oMLX, Homebrew build", ph, C_OMLX), ("oMLX, kernel build", pk, C_OMLX)]
    dec = [("llama.cpp, ubatch 512", d512, C_LLAMA), ("llama.cpp, ubatch 2048", d2048, C_LLAMA),
           ("oMLX, Homebrew build", dh, C_OMLX), ("oMLX, kernel build", dk, C_OMLX),
           ("oMLX + DSpark, 10k book text", dm, C_MTP), ("oMLX + DSpark, code task", code_on, C_MTP)]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.5, 5.9))
    frame(fig, (a1, a2), f"DeepSeek at 10k, one fix at a time: prefill {rhalf(p512)} → "
                         f"{rhalf(pk):,} t/s, decode {d2048:.0f} → {code_on:.0f} t/s",
          "DeepSeek-V4-Flash · llama.cpp: Vision-Exp UD-Q8_K_XL (prelim., 1 rep) · oMLX: 0731 oQ4e (2 reps). "
          "Multipliers are vs the first bar.\nEach step changes one thing, except llama.cpp → oMLX, which also "
          "switches variant and quant (8-bit → 4-bit).",
          f"{HW}\nubatch 512 = first llama.cpp run, {os.path.basename(first)} (superseded by the ubatch 2048 run under the "
          "same label; ubatch itself is not recorded in the JSONL). Probes in results/probes give 824 t/s "
          "(ubatch 2048) and 840 t/s (ubatch 4096) at 10k. DSpark 10k = cold 10k book prompt; DSpark code = short code "
          "prompt, 512 tokens, Homebrew build.\nSource: "
          f"{fname(DL)}, {fname(DH)}, {fname(DK_SHORT)}, {fname(DH_MTP)}, "
          f"mtp/{os.path.basename(MTP['ds0731-omlx-dspark-on'][0])}",
          ax_titles=True, left=1.95, right=0.2, wspace=0.95)
    for ax, rows, xmax, xl in ((a1, pre, 1900, "Cold prefill (tokens/s)"), (a2, dec, 88, "Decode (tokens/s)")):
        n = len(rows)
        ax.set_xlim(0, xmax)
        ax.set_ylim(n - 0.45, -0.55)
        _, ppy = px_per_unit(ax)
        bh = min(0.62, 48 / ppy)
        for i, (lab, v, c) in enumerate(rows):
            rbarh(ax, i, v, bh, c)
            txt = f"{rhalf(v):,}" if xmax > 100 else f"{v:.1f}"
            if i:
                txt += f"  ({v / rows[0][1]:.2f}x)"
            ax.text(v + xmax * 0.015, i, txt, va="center", fontsize=8.5, color=INK2)
        ax.set_yticks(range(n))
        ax.set_yticklabels([r[0] for r in rows], color=INK, fontsize=9)
        ax.grid(axis="y", visible=False)
        ax.set_xlabel(xl)
        comma(ax, "x")
    a1.set_title("Prefill", loc="left", fontsize=10.5, color=INK, weight="bold")
    a2.set_title("Decode", loc="left", fontsize=10.5, color=INK, weight="bold")
    save(fig, "08_deepseek_what_each_fix_bought.png")


def replay_rows(engine):
    path = sorted(glob.glob(os.path.join(ROOT, "replay", f"*-qwen-replay-{engine}.jsonl")))[-1]
    return path, [r for r in read_jsonl(path) if r.get("type") == "replay"]


def rolling_median(xs, ys, win=15):
    h = win // 2
    return [statistics.median(ys[max(0, i - h):i + h + 1]) for i in range(len(ys))]


def band(rows, field, lo=150000, hi=200000):
    return statistics.median(r[field] for r in rows if lo <= r["prompt_tokens"] <= hi)


def chart9():
    eng = [("llama", "llama.cpp Q8_0", C_LLAMA), ("omlx", "oMLX oQ8e", C_OMLX)]
    data = {}
    for key, name, col in eng:
        path, rows = replay_rows(key)
        rows.sort(key=lambda r: r["i"])
        x = [r["prompt_tokens"] / 1000 for r in rows]
        cum, t = [], 0.0
        for r in rows:
            t += r["total_s"]
            cum.append(t / 60)
        data[key] = dict(path=path, rows=rows, x=x, cum=cum, name=name, col=col)
    L, O = data["llama"], data["omlx"]
    n = len(O["rows"])
    fig, axes = plt.subplots(1, 3, figsize=(10, 5.6))
    short_o = sum(1 for r in O["rows"] if r["completion_tokens"] < 256)
    out_o = sum(r["completion_tokens"] for r in O["rows"])
    out_l = sum(r["completion_tokens"] for r in L["rows"])
    ly = frame(fig, axes, f"Replaying one agent session: oMLX finishes in {O['cum'][-1]:.1f} min, llama.cpp in "
                          f"{L['cum'][-1]:.1f} min",
               f"Qwen3.8-Flash-Next, MTP off · the same {n} recorded agent requests (context growing to "
               f"{max(O['x'] + L['x']):.0f}k tokens, up to 256 output tokens each) sent in order to each engine.\n"
               f"At 150-200k llama.cpp starts sooner ({band(L['rows'], 'ttft_s'):.1f} vs "
               f"{band(O['rows'], 'ttft_s'):.1f} s TTFT) but oMLX decodes {band(O['rows'], 'decode_tps'):.0f} vs "
               f"{band(L['rows'], 'decode_tps'):.0f} t/s.",
               f"{HW}\nDots = individual requests; lines = rolling median over 15 consecutive requests. Both servers "
               f"start with an empty cache; each request reuses the previous request's prefix. oMLX was not sent "
               f"ignore_eos and stopped early on {short_o} of {n} requests ({out_o:,} vs {out_l:,} output tokens; at its "
               f"own decode speed the rest would add ~"
               f"{sum((256 - r['completion_tokens']) / r['decode_tps'] for r in O['rows']) / 60:.0f} min).\nSource: results/replay/"
               f"{os.path.basename(L['path'])}, {os.path.basename(O['path'])}",
               legend_rows=1, ax_titles=True, left=0.6, right=0.75, wspace=0.34)
    panels = [("ttft_s", "Time to first token", lambda v, _: f"{v:g} s", (0, 7)),
              ("decode_tps", "Decode speed", lambda v, _: f"{v:.0f} t/s", (0, 65))]
    for ax, (field, title, fmt, ylim) in zip(axes[:2], panels):
        for d in (L, O):
            ys = [r[field] for r in d["rows"]]
            ax.plot(d["x"], ys, ls="none", marker="o", ms=3, mfc=d["col"], mec="none", alpha=0.3, zorder=2)
            rm = rolling_median(d["x"], ys)
            ax.plot(d["x"], rm, color=d["col"], lw=LW, solid_capstyle="round", solid_joinstyle="round", zorder=3)
            fs = "{:.1f} s" if field == "ttft_s" else "{:.0f} t/s"
            note(ax, d["x"][-1], rm[-1], fs.format(rm[-1]), dx=4)
        ax.set_ylim(*ylim)
        ax.yaxis.set_major_formatter(FuncFormatter(fmt))
        ax.set_title(title, loc="left", fontsize=10.5, color=INK, weight="bold")
    ax = axes[2]
    for d in (L, O):
        ax.plot(d["x"], d["cum"], color=d["col"], lw=LW, solid_capstyle="round", solid_joinstyle="round", zorder=3)
        ax.plot(d["x"][-1], d["cum"][-1], marker="o", ms=MS, mfc=d["col"], mec=SURFACE, mew=RING, zorder=4)
        note(ax, d["x"][-1], d["cum"][-1], f"{d['cum'][-1]:.1f} min", dx=6)
    ax.set_ylim(0, 33)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f} min"))
    ax.set_title("Cumulative elapsed time", loc="left", fontsize=10.5, color=INK, weight="bold")
    for ax in axes:
        ax.set_xlim(0, 240)
        ax.set_xticks([0, 50, 100, 150, 200])
        kfmt(ax)
        ax.set_xlabel("Prompt tokens")
    h = [Line2D([], [], color=d["col"], lw=LW) for d in (L, O)]
    fig.legend(h, [L["name"], O["name"]], loc="upper left", bbox_to_anchor=(0.2 / 10, ly), ncol=2,
               borderaxespad=0)
    save(fig, "09_qwen_replay_engines.png")


if __name__ == "__main__":
    for fn in (chart1, chart2, chart3, chart4, chart5, chart6, chart7, chart8, chart9):
        fn()
