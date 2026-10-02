#!/usr/bin/env python3
"""Build the synthetic call transcripts from hand-written sources.

Sources live in tools/src/Cxx.txt (hand-written core dialogue containing every
planted fact) and tools/pools/*.txt (neutral filler: holds, small talk, screen
navigation, troubleshooting chatter). Filler is inserted ONLY at `#fill` slots
until the call reaches its @target token count, which is how the long calls
get long: the planted facts end up buried among realistic but irrelevant talk.

Filler blocks were written to be fact-neutral (no symptoms, no amounts, no
dates, no promises, no names), so they cannot create or contradict gold labels.

v2 additions (ASR realism):
  * filler blocks get deterministic speech-to-text noise (fillers, stutters, [inaudible],
    [crosstalk]); noise is applied ONLY to filler, never to hand-written core lines, so
    gold evidence quotes are never altered;
  * `@diar_drop P` (per call): probability that a whole filler block is rendered with the
    speaker label lost (`SPEAKER ?:`);
  * `#diar off` / `#diar on` in a source: core lines in between are rendered as `SPEAKER ?:`
    (diarization failure), so the reader must infer who is talking;
  * core lines can also be written with a deliberately wrong speaker letter.

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


FILLERS = ["um,", "uh,", "so,", "like,", "you know,", "I mean,", "uh-", "mm,"]


def asr_noise(line, rng):
    """Deterministic speech-to-text noise for a FILLER line (never applied to core lines)."""
    m = re.match(r"(\w+): (.*)", line)
    if not m:
        return line
    who, words = m.group(1), m.group(2).split(" ")
    out = []
    depth = 0
    for i, w in enumerate(words):
        r = rng.random()
        inside = depth > 0 or w.startswith("[")
        depth += w.count("[") - w.count("]")
        if inside or "]" in w:                 # never touch [stage directions]
            out.append(w)
            continue
        if r < 0.025 and len(w) > 3:
            out.append("[inaudible]")
            continue
        if r < 0.05:
            out.append(rng.choice(FILLERS))
        elif r < 0.065 and w.isalpha():
            out.append(w + " " + w)            # stutter / repeated word
            continue
        out.append(w)
    text = " ".join(out)
    if rng.random() < 0.04:
        text = "[crosstalk] " + text
    if rng.random() < 0.15:
        text = text[0].lower() + text[1:] if text else text   # ASR casing drift
    return f"{who}: {text}"


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
        "transcription service. Speech-to-text errors (misheard words, numbers and drug "
        "names) are not corrected. 'SPEAKER ?' = diarization could not attribute the "
        "speaker; speaker labels may occasionally be wrong.",
        "-" * 60,
    ]
    diar = True
    for line in lines:
        if line.startswith("#diar"):
            diar = line.split()[1] == "on"
            continue
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
        lost = line.startswith("\x00")
        line = line.lstrip("\x00")
        m = re.match(r"(\w+): (.*)", line)
        if not m or m.group(1) not in spk:
            raise ValueError(f"{meta['id']}: bad line: {line!r}")
        who, text = spk[m.group(1)], m.group(2)
        if lost or not diar:
            who = "SPEAKER ?"
        out.append(f"{fmt_ts(t)} {who}: {text}")
        words = len(text.split())
        t += words / rng.uniform(2.3, 2.9) + rng.uniform(0.4, 1.6)
    out.append(f"{fmt_ts(t)} [call ended]")
    return "\n".join(out) + "\n"


def build(path, pools):
    meta, body = parse_source(path)
    seed = int(meta.get("seed", "0")) or sum(map(ord, meta["id"]))
    target = int(meta.get("target", "0"))
    diar_drop = float(meta.get("diar_drop", "0.12"))
    rng = random.Random(seed)

    slots = [i for i, l in enumerate(body) if l.startswith("#fill")]
    slot_pools = {i: [a for a in body[i].split()[1:] if not a.startswith("@")] for i in slots}
    for i, names in slot_pools.items():
        missing = [n for n in names if n not in pools]
        if missing:
            print(f"  warning {meta['id']}: unknown pool(s) {missing} ignored", file=sys.stderr)
            slot_pools[i] = [n for n in names if n in pools]
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
        blk = [asr_noise(l, rng) for l in blk]
        if rng.random() < diar_drop:
            blk = ["\x00" + l if re.match(r"\w+: ", l) else l for l in blk]
        remap = slot_remap[slot]
        if remap:
            blk = [re.sub(r"^(\x00?)(\w+):", lambda m: m.group(1) + remap.get(m.group(2), m.group(2)) + ":", l)
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
    ap.add_argument("--only", help="comma-separated call ids to build, e.g. C03,C11")
    args = ap.parse_args()
    pools = load_pools()
    OUT.mkdir(exist_ok=True)
    total = 0
    for src in sorted(SRC.glob("C*.txt")):
        if args.only and src.stem not in args.only.split(","):
            continue
        meta, text, reused = build(src, pools)
        n = ntok(text)
        total += n
        flag = "  (filler pools exhausted before target)" if reused else ""
        core = ntok(render(meta, [l for l in parse_source(src)[1] if not l.startswith("#fill")], 0))
        print(f"{meta['id']}: {n:6d} tokens (target {meta.get('target', '-')}, core {core}){flag}")
        if not args.check:
            (OUT / f"{meta['id']}.txt").write_text(text)
    print(f"total: {total} tokens")


if __name__ == "__main__":
    sys.exit(main())
