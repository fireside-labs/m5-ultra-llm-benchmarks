#!/usr/bin/env python3
"""Write gold/Rxx.json from the authoring sources in tools/gold_src/Rxx.py.

The Python sources exist only so regexes can be written as raw strings; gold/*.json is what
score.py, validate_gold.py and the self-test read. Re-run after editing a source:

  python tools/build_gold.py && python tools/validate_gold.py && python selftest/make_mocks.py
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "gold_src"
OUT = HERE.parent / "gold"
sys.path.insert(0, str(SRC))


def main():
    OUT.mkdir(exist_ok=True)
    n = 0
    for p in sorted(SRC.glob("R*.py")):
        spec = importlib.util.spec_from_file_location(p.stem, p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        g = mod.GOLD
        assert g["task_id"] == p.stem, p
        (OUT / f"{p.stem}.json").write_text(json.dumps(g, indent=1, ensure_ascii=False) + "\n")
        n += 1
    print(f"wrote {n} gold files to {OUT}")


if __name__ == "__main__":
    main()
