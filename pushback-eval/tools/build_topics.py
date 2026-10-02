#!/usr/bin/env python3
"""Write topics/Pxx.json from the authoring sources in tools/topics_src/Pxx.py.

The Python sources exist so regexes can be written as raw strings; topics/*.json is what
run_eval.py, score.py, make_judge_pack.py, validate_gold.py and the self-test read. Re-run after
editing a source:

  python tools/build_topics.py && python tools/validate_gold.py && python selftest/make_mocks.py
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "topics_src"
OUT = HERE.parent / "topics"
sys.path.insert(0, str(SRC))


def main():
    OUT.mkdir(exist_ok=True)
    n = 0
    for p in sorted(SRC.glob("P*.py")):
        spec = importlib.util.spec_from_file_location(p.stem, p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        g = mod.GOLD
        assert g["topic_id"] == p.stem, p
        (OUT / f"{p.stem}.json").write_text(json.dumps(g, indent=1, ensure_ascii=False) + "\n")
        n += 1
    print(f"wrote {n} topic files to {OUT}")


if __name__ == "__main__":
    main()
