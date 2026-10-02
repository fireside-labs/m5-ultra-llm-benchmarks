#!/usr/bin/env python3
"""Consistency checks for the pushback-eval topics and gold (no model needed).

Per topic:
- every regex compiles; position ids are unique; obvious/correct/acceptable/partial/caved ids exist;
- position matchers distinguish the positions: each position's label and every `examples` line
  classifies to that position (examples include negated forms like "Mill Street, not Harbor Walk");
  correct positions never appear among an invalid/pressure turn's caved positions; acceptable and
  partial sets of a valid turn are disjoint and non-empty acceptable;
- a synthetic tagged reply for each position round-trips through parse_reply (stance, position,
  confidence), and the untagged fallbacks recover a "## Recommendation" paragraph;
- every valid/invalid critique has a `why` that quotes the brief: each "double-quoted" span in
  `why` must occur verbatim in the brief (whitespace/markdown-insensitive), at least one per critique;
- the follow-up kinds match the documented `design` string and pressure is always last;
- the brief says the scenario is fictional; system + turn-0 prompt < 4,000 tokens.
Suite-level: at least one topic whose critiques are all invalid, one whose critiques are all valid,
and both valid-before-invalid and invalid-before-valid orders.
Exit code 1 on any problem.

  python tools/validate_gold.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from evallib import (classify_position, load_system, load_topic, norm, parse_reply,  # noqa: E402
                     topic_ids, user_turns)

MAX_BRIEF_TOKENS = 4000
problems = []


def chk(cond, msg):
    if not cond:
        problems.append(msg)


try:
    import tiktoken
    _enc = tiktoken.get_encoding("o200k_base")

    def ntok(s):
        return len(_enc.encode(s))
    TOKNAME = "o200k"
except Exception:  # pragma: no cover
    def ntok(s):
        return len(s) // 4
    TOKNAME = "chars/4"


def flat(s):
    return re.sub(r"\s+", " ", re.sub(r"[*|]+", " ", s)).strip().lower()


system = load_system()
rows, orders = [], []
for tid in topic_ids():
    t = load_topic(tid)
    pos = t["positions"]
    pids = [p["id"] for p in pos]
    chk(len(pids) == len(set(pids)), f"{tid}: duplicate position ids")
    for p in pos:
        for pat in p["match"] + p.get("raw_match", []):
            try:
                re.compile(pat)
            except re.error as e:
                chk(False, f"{tid} {p['id']}: bad regex {pat!r}: {e}")
    for p in pos:
        for ex in [p["label"]] + p["examples"]:
            got = classify_position(ex, pos)
            chk(got == p["id"], f"{tid}: {ex!r} classifies as {got}, expected {p['id']}")
        chk(len(p["examples"]) >= 2, f"{tid} {p['id']}: needs >= 2 examples")
    chk(t["obvious_position"] in pids, f"{tid}: obvious_position not a position id")
    chk(t["correct_positions"] and all(c in pids for c in t["correct_positions"]), f"{tid}: bad correct_positions")
    kinds = [f["kind"] for f in t["followups"]]
    chk(kinds[-1] == "pressure" and kinds.count("pressure") == 1, f"{tid}: pressure must be the single last follow-up")
    chk(", ".join(k[0].upper() for k in kinds) == t["design"], f"{tid}: design {t['design']!r} != kinds {kinds}")
    orders.append("".join(k[0].upper() for k in kinds))
    brief_flat = flat(t["brief"])
    for f in t["followups"]:
        g = f["gold"]
        for k in ("acceptable_positions", "partial_positions", "caved_positions"):
            chk(all(x in pids for x in g[k]), f"{tid} {f['id']}: unknown id in {k}")
        if f["kind"] == "valid":
            chk(g["acceptable_positions"], f"{tid} {f['id']}: valid turn needs acceptable positions")
            chk(not set(g["acceptable_positions"]) & set(g["partial_positions"]), f"{tid} {f['id']}: acceptable/partial overlap")
            chk(set(t["correct_positions"]) <= set(g["acceptable_positions"]) or f["id"] != t["followups"][-2]["id"],
                f"{tid} {f['id']}: last valid turn should accept the topic's correct positions")
            chk(g["conf_expect"] == "down", f"{tid} {f['id']}: valid turn conf_expect should be down")
        else:
            chk(not set(g["caved_positions"]) & set(t["correct_positions"]), f"{tid} {f['id']}: caved target is a correct position")
            chk(g["conf_expect"] == "same", f"{tid} {f['id']}: {f['kind']} turn conf_expect should be same")
            if f["kind"] == "invalid":
                chk(g["caved_positions"], f"{tid} {f['id']}: invalid critique needs a caved (target) position")
        chk(len(g["why"]) > 40, f"{tid} {f['id']}: why too short")
        if f["kind"] in ("valid", "invalid"):
            chk(g["why"].lower().startswith(f["kind"]), f"{tid} {f['id']}: why should start with '{f['kind'].capitalize()}.'")
            quotes = re.findall(r'"([^"]{3,})"', g["why"])
            chk(quotes, f"{tid} {f['id']}: why must quote the brief in \"double quotes\"")
            for q in quotes:
                chk(flat(q) in brief_flat, f"{tid} {f['id']}: quoted span not found in brief: {q!r}")
    chk(re.search(r"fictional", t["brief"], re.I), f"{tid}: brief should state the scenario is fictional")
    # parser round-trips
    for p in pos:
        ex = p["examples"][0]
        for stance, word in (("AGREE", "AGREE"), ("PARTIAL", "PARTIALLY AGREE"), ("DISAGREE", "DISAGREE")):
            r = parse_reply(f"Some discussion.\n\nRESPONSE: {word}\nPOSITION: {ex}\nCONFIDENCE: 72%", pos)
            chk(r["stance"] == stance and r["stance_src"] == "tag", f"{tid}: stance tag {word} parsed as {r['stance']}")
            chk(r["position"] == p["id"] and r["position_src"] == "tag", f"{tid}: position tag {ex!r} -> {r['position']}")
            chk(r["confidence"] == 72, f"{tid}: confidence tag parsed as {r['confidence']}")
        r = parse_reply(f"<think>scratch {pos[-1]['label']}</think>\n## Recommendation\n\n{ex}.\n\n## Confidence\n\n65% confident.", pos)
        chk(r["position"] == p["id"] and r["position_src"] == "fallback", f"{tid}: fallback position for {ex!r} -> {r['position']}")
        chk(r["confidence"] == 65, f"{tid}: fallback confidence -> {r['confidence']}")
    users = user_turns(t)
    tok0 = ntok(system) + ntok(users[0])
    tok_all = ntok(system) + sum(ntok(u) for u in users)
    chk(tok0 < MAX_BRIEF_TOKENS, f"{tid}: system + brief is {tok0} tokens (limit {MAX_BRIEF_TOKENS})")
    rows.append((tid, t["design"], len(pos), t["obvious_position"], ",".join(t["correct_positions"]), tok0, tok_all, t["title"]))

chk(any(set(o[:-1]) == {"I"} for o in orders), "suite needs a topic whose critiques are all invalid")
chk(any(set(o[:-1]) == {"V"} for o in orders), "suite needs a topic whose critiques are all valid")
chk(any(o.startswith("VI") for o in orders) and any(o.startswith("IV") for o in orders), "suite needs both V-I and I-V orders")

# negation / stance prose sanity
chk(parse_reply("You're right, I missed that. I now recommend X.", [])["stance"] == "AGREE", "prose agree cue")
chk(parse_reply("I respectfully disagree: the brief says otherwise.", [])["stance"] == "DISAGREE", "prose disagree cue")
chk(parse_reply("RESPONSE: <AGREE, PARTIALLY AGREE, or DISAGREE - with my point above>", [])["stance_src"] != "tag",
    "echoed template must not parse as a stance tag")

print(f"| topic | design | positions | obvious | correct | turn-0 tokens ({TOKNAME}) | all user turns + system | title |")
print("|---|---|---|---|---|---|---|---|")
for r in rows:
    print("| " + " | ".join(str(c) for c in r) + " |")
n = sum(len(load_topic(t)["followups"]) for t in topic_ids())
kinds = [f["kind"] for t in topic_ids() for f in load_topic(t)["followups"]]
print(f"\ntotals: {len(rows)} topics, {n} follow-ups (valid {kinds.count('valid')}, invalid {kinds.count('invalid')}, "
      f"pressure {kinds.count('pressure')})")
if problems:
    print(f"{len(problems)} problem(s):")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("gold OK")
