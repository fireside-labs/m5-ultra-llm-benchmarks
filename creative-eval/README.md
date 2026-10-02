# creative-eval

A single creative-writing prompt, not a scored eval: the opening two chapters of an isekai light novel, written as
one conversation (chapter 1, then chapter 2 with the same characters and rules).

- `run.py --url ... --model <served-name> --label <label> [--extra-body '{...}']` writes
  `results/creative-eval/<label>/{ch1,ch2}.md`, the reasoning text and `meta.json` (timing, words). Defaults:
  temperature 0.8, top_p 0.95, 16,384 max tokens per chapter.
- `tools/make_viewer.py out.html` builds a blind side-by-side reader: the stories are shuffled to A/B/C and a button
  reveals the models.
- `replay_chat.py` replays the user turns of an exported oMLX chat against another model and saves the fresh replies
  to `results/live-replay/<label>.json` (used to rerun a live conversation at a different reasoning effort).

`BENCH_RESULTS` overrides the `results/` folder. The published outputs are in `../results/creative-eval/`
(GLM-5.3 at effort high, Qwen at effort medium, DeepSeek at oMLX's default low effort).
