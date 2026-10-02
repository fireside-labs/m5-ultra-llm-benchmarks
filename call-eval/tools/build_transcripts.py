#!/usr/bin/env python3
"""Build the synthetic call transcripts from hand-written sources.

Sources live in tools/src/Cxx.txt (hand-written core dialogue containing every
planted fact) and tools/pools/*.txt (neutral filler: holds, small talk, screen
navigation, troubleshooting chatter). Filler is inserted ONLY at `#fill` slots
until the call reaches its @target token count, which is how the long calls
get long: the planted facts end up buried among realistic but irrelevant talk.

Filler blocks were written to be fact-neutral (no symptoms, no amounts, no
dates, no promises, no names), so they cannot create or contradict gold labels.

Deterministic: same sources + same seed => byte-identical transcripts.

Usage:  python tools/build_transcripts.py            # writes transcripts/*.txt
        python tools/build_transcripts.py --check    # only print token counts
"""
import argparse
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "src"
POOLS = ROOT / "tools" / "pools"
OUT = ROOT / "transcripts"

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("o200k_base")

    def ntok(s):
        return len(_ENC.encode(s))
except Exception:  # pragma: no cover
    def ntok(s):
        return len(s) // 4

CHOICE_RE = re.compile(r"\{([^{}]*\|[^{}]*)\}")


def expand(text, rng):
    """Expand {a|b|c} alternatives."""
    while True:
        m = CHOICE_RE.search(text)
        if not m:
            return text
        opt = rng.choice(m.group(1).split("|"))
        text = text[: m.start()] + opt + text[m.end():]


def load_pools():
    pools = {}
    for p in sorted(POOLS.glob("*.txt")):
        blocks, cur = [], []
        for line in p.read_text().splitlines():
            if line.strip() == "===":
                if cur:
                    blocks.append(cur)
                cur = []
            elif line.strip() and not line.startswith("//"):
                cur.append(line.rstrip())
        if cur:
            blocks.append(cur)
        pools[p.stem] = blocks
    return pools


def parse_source(path):
    meta, body, in_body = {}, [], False
    speakers, speaker_desc = {}, []
    for line in path.read_text().splitlines():
        if not in_body:
            if line.strip() == "---":
                in_body = True
                continue
            if line.startswith("@speaker "):
                # @speaker A AGENT = Scheduling representative (Priya)
                m = re.match(r"@speaker (\w+) (\S+) = (.*)", line)
                speakers[m.group(1)] = m.group(2)
                speaker_desc.append(f"{m.group(2)} = {m.group(3)}")
            elif line.startswith("@"):
                k, _, v = line[1:].partition(" ")
                meta[k] = v.strip()
            continue
        if line.strip() and not line.startswith("//"):
            body.append(line.rstrip())
    meta["speakers"] = speakers
    meta["speaker_desc"] = speaker_desc
    return meta, body


def fmt_ts(sec):
    sec = int(sec)
    return f"[{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}]"


def render(meta, lines, rng_seed):
    """Render body lines (already with filler spliced in) to transcript text."""
    rng = random.Random(rng_seed)
    spk = meta["speakers"]
    t = float(rng.randint(1, 4))
    out = [
        "CALL TRANSCRIPT",
        f"Call ID: {meta['id']}",
        f"Date/time: {meta['date']}",
        f"Line: {meta['line']}",
        f"Direction: {meta['direction']}",
        "Speakers: " + "; ".join(meta["speaker_desc"]),
        "Source: automatic speech-to-text with speaker diarization; timestamps are "
        "call-relative. [inaudible], [crosstalk] and [background] marks are from the "
        "transcription service.",
        "-" * 60,
    ]
    for line in lines:
        if line.startswith("#hold"):
            secs = int(line.split()[1])
            out.append(f"{fmt_ts(t)} [caller placed on hold]")
            t += secs
            out.append(f"{fmt_ts(t)} [hold ended - {secs // 60}m{secs % 60:02d}s]")
            t += 1
            continue
        if line.startswith("#pause"):
            t += int(line.split()[1])
            continue
        if line.startswith("#note"):
            out.append(f"{fmt_ts(t)} [{line[6:].strip()}]")
            continue
        m = re.match(r"(\w+): (.*)", line)
        if not m or m.group(1) not in spk:
            raise ValueError(f"{meta['id']}: bad line: {line!r}")
        who, text = spk[m.group(1)], m.group(2)
        out.append(f"{fmt_ts(t)} {who}: {text}")
        words = len(text.split())
        t += words / rng.uniform(2.3, 2.9) + rng.uniform(0.4, 1.6)
    out.append(f"{fmt_ts(t)} [call ended]")
    return "\n".join(out) + "\n"


def build(path, pools):
    meta, body = parse_source(path)
    seed = int(meta.get("seed", "0")) or sum(map(ord, meta["id"]))
    target = int(meta.get("target", "0"))
    rng = random.Random(seed)

    slots = [i for i, l in enumerate(body) if l.startswith("#fill")]
    slot_pools = {i: [a for a in body[i].split()[1:] if not a.startswith("@")] for i in slots}
    # "@A=S" remaps pool speaker letter A to source speaker S for that slot
    slot_remap = {i: dict(a[1:].split("=") for a in body[i].split()[1:] if a.startswith("@"))
                  for i in slots}
    fills = {i: [] for i in slots}
    used = set()

    def assemble():
        lines = []
        for i, l in enumerate(body):
            if l.startswith("#fill"):
                for blk in fills[i]:
                    lines.extend(blk)
            else:
                lines.append(expand(l, random.Random(seed + i)))
        return lines

    text = render(meta, assemble(), seed)
    cur = ntok(text)
    reused = 0
    exhausted = set()
    k = 0
    while target and slots and cur < target * 0.98:
        slot = slots[k % len(slots)]
        k += 1
        if slot in exhausted:
            continue
        pool_names = slot_pools[slot]
        cands = [(pn, bi) for pn in pool_names for bi in range(len(pools[pn]))
                 if (pn, bi) not in used]
        if not cands:  # pools for this slot exhausted: never repeat a block within a call
            exhausted.add(slot)
            if len(exhausted) == len(slots):
                reused = 1
                break
            continue
        pn, bi = rng.choice(cands)
        used.add((pn, bi))
        blk = [expand(l, rng) for l in pools[pn][bi]]
        remap = slot_remap[slot]
        if remap:
            blk = [re.sub(r"^(\w+):", lambda m: remap.get(m.group(1), m.group(1)) + ":", l)
                   for l in blk]
        fills[slot].append(blk)
        cur += ntok("\n".join(blk)) + 6 * len(blk)
        if k % 10 == 0:
            cur = ntok(render(meta, assemble(), seed))
    text = render(meta, assemble(), seed)
    return meta, text, reused


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    pools = load_pools()
    OUT.mkdir(exist_ok=True)
    total = 0
    for src in sorted(SRC.glob("C*.txt")):
        meta, text, reused = build(src, pools)
        n = ntok(text)
        total += n
        flag = "  (filler pools exhausted before target)" if reused else ""
        print(f"{meta['id']}: {n:6d} tokens (target {meta.get('target', '-')}){flag}")
        if not args.check:
            (OUT / f"{meta['id']}.txt").write_text(text)
    print(f"total: {total} tokens")


if __name__ == "__main__":
    sys.exit(main())
