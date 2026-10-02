# Blind code review of the finished agent projects

Three projects that reached all 30 milestones of `agentic/TASK.md` (the "Deepdelve" TypeScript roguelike) were
reviewed blind. The reviewer saw them as A, B and C, without knowing which model or harness produced which, and the
key was revealed only after the grades were written down.

| Letter | Model | Harness / engine | Wall time | Hidden tests (referee) |
|---|---|---|---|---|
| A | GLM-5.3-Flash 4-bit (Vontra oQ4-MTP, MTP on) | pi, oMLX 0.7.0 kernel build | 2 h (all 30 milestones at 64 min) | 53/54 |
| B | Qwen3.8-Flash-Next 8-bit (oQ8e, MTP on) | pi, oMLX 0.7.0 kernel build | 38 min | 52/54 |
| C | DeepSeek-V4-Flash-Vision-Exp (UD-Q8_K_XL + DSpark) | DeepSeek Harness, llama.cpp | 3 h | 53/54 |

Run data: `results/agentic/runs/20261001-034857-glm-omlx070-pi*`, `20261001-065428-qwen-omlx070-pi*` and
`20260930-193242-dsv4v-llama-dspark-dsh*` (referee JSONL, git log, file line counts, filtered harness log).

## Method

1. Build each project (`npm ci`, `npm test`, `npm run build`).
2. Run an independent 12-check conformance test written by the reviewer against the milestone spec
   ([code-review/conform.test.ts](code-review/conform.test.ts)): RNG determinism, map JSON round-trip, dungeon
   connectivity over 50 seeds, movement, field of view (walls lit, nothing visible behind walls, radius),
   A* optimality on random dungeons, scheduler fairness, combat, inventory, levels, save/load and status effects.
3. Run each build and read the code.
4. A follow-up readability pass with static metrics (function length, cyclomatic complexity, nesting, comment
   ratio, magic numbers; [code-review/metrics.cjs](code-review/metrics.cjs), run with the project's own TypeScript).

## Results

| | GLM (A) | Qwen (B) | DeepSeek (C) |
|---|---|---|---|
| Conformance test (12 checks) | 11/12 (FOV leaks through walls) | **12/12** | 10/12 (FOV radius off by one, A* not shortest) |
| Source / test lines | 7,588 / 7,214 | 4,817 / 3,476 | 3,778 / 4,012 |
| Unreachable code | about 2,170 lines (21 `*-extended` modules nothing imports) | none | levels, save and settings modules not wired in |
| Correctness / completeness / quality / tests (1-10) | 4 / 5 / 4 / 5 | 7 / 8 / 6 / 7 | 3 / 3 / 5 / 4 |
| Overall ("would I merge it", 1-10) | 4 | **7** | 3 |
| Readability (1-10, follow-up pass) | 4 | 6 | **7** |

Notes per project:

- **GLM (A):** wide but shallow. Levels respawn, poison death doesn't end the game, and 723 tests missed the FOV
  leak. `npm ci` fails because the lockfile is out of date. The core turn loop is clear, but there are unreachable
  `*-extended` copies of modules, comments that contradict the code (`return changed || true`), and a 178-line
  switch with cyclomatic complexity 61. Context for the dead code: GLM finished milestone 30 after 64 minutes and
  then followed TASK.md's "when you finish, start again and extend" instruction by adding 21 separate
  `*-extended` modules (the commit log shows them after 05:09) instead of changing the existing ones. The task
  invited the extension pass; the strategy was poor.
- **Qwen (B):** most milestones are actually playable. Bugs: loading a save drops gold, XP and level, and skills
  and potions cost no turn. Comments explain why, and there is a real save-migration chain, but the engine is a
  1,082-line class with copy-pasted branches and a `this.turn--` hidden in 7 branches. One commit per milestone,
  no revisit passes.
- **DeepSeek (C):** monsters deal double damage, every run has identical levels from depth 2, and most late
  milestones are isolated modules that the game never calls. It has the most readable code (small flat functions,
  clearest naming), but its comments describe features that aren't wired up, e.g. "the scheduler grants energy"
  where the scheduler is never called. Clean code with wrong comments is easy to trust by mistake.

## Takeaways

- The hidden tests (milestones 1-17) and milestone counts overstated GLM and DeepSeek. Commit count measures
  activity, not quality. Qwen's 38-minute run produced the best code.
- One run per model and one reviewer; the grades are a first look, not a ranking with error bars.
