#!/usr/bin/env python3
"""Blind side-by-side reader for the isekai test. Labels shuffled to Story A/B/C; a button reveals the models."""
import json, os, pathlib, random, sys

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
RES = pathlib.Path(os.environ.get("BENCH_RESULTS", REPO / "results")).expanduser() / "creative-eval"
NAMES = {"glm53": "GLM-5.3-Flash (4-bit, effort high)", "qwen38": "Qwen3.8-Flash-Next (8-bit, effort medium)",
         "dsv4": "DeepSeek-V4-Flash (effort low, oMLX default)"}
out = sys.argv[1]
labels = [l for l in NAMES if (RES / l / "ch1.md").exists()]
random.SystemRandom().shuffle(labels)
stories = []
for letter, lab in zip("ABC", labels):
    meta = json.loads((RES / lab / "meta.json").read_text())
    stories.append({"letter": letter, "model": NAMES[lab],
                    "ch1": (RES / lab / "ch1.md").read_text(), "ch2": (RES / lab / "ch2.md").read_text(),
                    "secs": round(sum(m.get("total_s") or 0 for m in meta.values())),
                    "words": sum(m.get("words") or 0 for m in meta.values())})
tpl = (pathlib.Path(__file__).parent / "viewer_template.html").read_text()
pathlib.Path(out).write_text(tpl.replace("/*__DATA__*/[]", json.dumps(stories).replace("</", "<\\/")))
print("wrote", out, [s["letter"] for s in stories])
