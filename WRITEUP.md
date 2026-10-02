A while back I promised you all M5 Ultra benchmarks. Then I remembered that every Mac benchmark on the internet is someone typing "hi" at a model and posting the tok/s like it's a PR at the gym. Nobody's life depends on how fast a model says hi back.

I use these models for long documents and for coding agents that run for hours. So that's what I tested, and my Mac Studio has not been allowed to rest since. It's fine. It's a 256GB machine. It knew what it signed up for.

**TL;DR:** A brand-new giant prompt on a Mac is slow. Painfully slow. A 400k-token prompt took over 15 minutes before the first word came out. But the *next* step in that same conversation took about 1 second, because it's cached. If your agent setup keeps the cache intact, prefill is leg day. It hurts, but you do it once.

**Setup**

- Mac Studio, M5 Ultra, 256GB, macOS 27.0.1
- Models: Qwen3.8-Flash-Next (8-bit) and DeepSeek-V4-Flash (0731 and Vision-Exp)
- Engines: llama.cpp (Metal, commit 19e28a2) and oMLX 0.7.0rc1
- The long prompts are Project Gutenberg novels (War and Peace, Les Mis, the whole depressing gang), cut to exact token counts with each model's own tokenizer. "200k" means 200,000 tokens, not "roughly a lot." Anyone can rebuild the exact same prompts.
- "Cold" = nothing cached. I put a random marker at the very start of each prompt so no cache can cheat. "Warm" = the same conversation continued with a few new tokens, like an agent does.

## 1. Pay prefill once

If you only look at one chart, make it this one.

![cold vs warm](charts/03_qwen_warm_vs_cold_ttft.png)

| | Cold (fresh prompt) | Warm (next step, cached) |
|---|---|---|
| Qwen, 250k context, llama.cpp | 234 s | 0.64 s |
| DeepSeek, 400k context, llama.cpp | 934 s | 1.23 s |
| DeepSeek, 500k context, llama.cpp | 1,311 s | 1.42 s |

Twenty-two minutes for the first answer at 500k. I went and made a protein shake. I came back. It was still thinking. I understood it on a spiritual level.

So the real question isn't "how fast is prefill," it's "how often do you pay it." A coding agent that keeps adding to the same conversation pays it basically once. A harness that keeps rewriting or summarizing the conversation pays it every single time, and at that point you're doing leg day every day, which is how people get hurt.

## 2. Qwen doesn't get tired (on oMLX)

Qwen3.8-Flash-Next only has 12 full-attention layers out of 48, and it shows. On oMLX its decode barely moves from 10k to 250k. On llama.cpp it gasps like me on the stairs after leg day.

![qwen decode](charts/02_qwen_decode_vs_depth.png)

| Qwen, 8-bit, MTP off | 10k | 100k | 250k |
|---|---|---|---|
| Decode, llama.cpp (Q8_0) | 47 t/s | 30 t/s | 17 t/s |
| Decode, oMLX (oQ8e) | 56 t/s | 53 t/s | 51 t/s |
| Prefill, llama.cpp | 1,622 t/s | 1,393 t/s | 1,069 t/s |
| Prefill, oMLX | 1,714 t/s | 1,555 t/s | 1,365 t/s |

oMLX wins prefill at every depth (+28% at 250k), and decode is almost 3x faster at 250k. llama.cpp still wins tiny follow-up steps: 64 new tokens start in about 0.4-0.6 s at any depth, while oMLX has a per-step cost that grows with context (4.8 s at 250k). With a more realistic 4k-token tool result, oMLX is faster again from about 150k up.

With MTP on, oMLX Qwen decodes at 88 t/s at 10k and still 68 t/s at 250k, on summary prompts, which is MTP's weakest case. That's 3.9x llama.cpp at 250k. On short code/JSON prompts it hit 118-139 t/s, and it held around 90-97 t/s through a real overnight coding session. A 125B model on a desk, writing code faster than I can read it. I don't read that fast anyway, but still.

## 3. DeepSeek: a before/after transformation photo

DeepSeek-V4-Flash was slow out of the box. Here's what each change did at 10k context:

![what each fix bought](charts/08_deepseek_what_each_fix_bought.png)

- llama.cpp with default settings: 628 t/s prefill
- llama.cpp with `-b 2048 -ub 2048`: 827 t/s (+31%, one flag, free gains, the creatine of settings)
- oMLX, Homebrew build: 1,204 t/s
- oMLX built from source with its custom kernels: 1,368 t/s
- Decode went from 32 t/s to 63 t/s on code with DSpark turned on

Important: the Homebrew build of oMLX doesn't include the custom Metal kernels for DeepSeek's sparse attention. The log literally tells you long-context prefill is "several times slower," in the tone of a coach who's disappointed but not surprised. If you run DeepSeek V4 on oMLX, build it from source with `OMLX_WITH_CUSTOM_KERNEL=1`. You need Xcode's Metal toolchain for that, which is a 20-minute download I will never get back.

Honest caveat: on DeepSeek the two engines didn't run the exact same file. llama.cpp ran Vision-Exp (unsloth UD-Q8_K_XL, which keeps DeepSeek's native FP4 experts and FP8-ish everything else, basically lossless, 162GB). oMLX ran 0731 (Jundot's oQ4e, a 4-bit mixed re-quant of the same native format, 154GB). The experts are 4-bit in both, so this is closer to fair than it looks, but it's a different variant and a re-quant, not byte-for-byte the same model. A matched test is on my list.

## 4. MTP and DSpark

Both guess a few tokens ahead. They're great on predictable stuff like JSON and code and do basically nothing for creative writing, which honestly relates to how I do at poetry.

![mtp dspark](charts/07_mtp_dspark_speedup_by_task.png)

| | Code | Reasoning | JSON | Prose |
|---|---|---|---|---|
| Qwen MTP (oMLX), temp 0 | 1.97x | 2.09x | 2.28x | 1.53x |
| Qwen MTP, Qwen's recommended sampling | 1.89x | 1.89x | 2.16x | 1.38x |
| DeepSeek DSpark (oMLX) | 1.53x | 1.54x | 1.51x | 1.00x |

DeepSeek's DSpark gave word-for-word identical output with it on or off. Qwen's MTP gave slightly different, equally fine text (on one prose prompt, off wrote "the grain of Elias's skin" and on wrote "the creases of Elias's face." Both are fine. Both made me moisturize). Each mode was repeatable on its own. You don't need to raise temperature for MTP; higher temperature slightly lowers the gain.

## 5. Overnight: real agent sessions, 3 hours each

Same task for every setup: build a browser roguelike in TypeScript, 30 milestones, run tests and the build after each one, commit, and never stop. It's deliberately too big to finish. A logging proxy recorded every request, and a separate "referee" checked every milestone commit against 54 hidden tests the model never saw. Basically a drug test for code.

| Run | Final context | Steps/hour | Hidden tests passed |
|---|---|---|---|
| DeepSeek, oMLX + kernels + DSpark (3 h) | 421k | 348 | 52/54 |
| DeepSeek, llama.cpp + DSpark (3 h) | 436k | 241 | 49/54 |
| Qwen, oMLX + MTP (1 h) | 201k | 181 | 23/24 |
| Qwen, llama.cpp (1 h) | 106k | 91 | 19/19 |
| Qwen, llama.cpp + pi harness (1 h) | 134k | 118 | 45/45 |

What I took from it:

- **Zero cache breaks in every run**, including a real harness (pi). The "pay prefill once" thing held up for an entire night.
- **The harness mattered more than I expected.** Same model and engine: pi got to milestone 15 with every hidden test passing. My own little agent loop got to milestone 6. I built it and I'm still offended.
- **"Milestones completed" is a lying metric.** DeepSeek "finished" all 30 in about 25 minutes, which is not possible if you're doing real work (my hidden tests only cover the first 17). Then it spent two hours adding one-line tests and committing each one as a milestone. It's the guy who does one curl, walks around the gym for 40 minutes, and posts "grind never stops." It also broke its A* pathfinding at 128k context and never fixed it.

Because agents take different paths every run, I also did a cleaner engine test: I recorded one Qwen agent session (181 requests growing to 200k) and replayed the exact same requests against both engines, with the output fixed at 256 tokens per step.

![replay](charts/09_qwen_replay_engines.png)

| Same 181 requests, Qwen 8-bit, MTP off | oMLX | llama.cpp |
|---|---|---|
| Total time | 18.5 min (about 19.5 if it had written every token, see below) | 29.7 min |
| Time to first token, 150-200k | 2.4 s | 1.6 s |
| Decode, 150-200k | 52 t/s | 22 t/s |

llama.cpp starts each step a bit sooner, but oMLX writes so much faster at depth that it wins as soon as a reply is longer than about 35 tokens. oMLX finished the same session about 1.5x faster. (Small confession: I forgot to tell oMLX to ignore end-of-text, so it stopped early on 39 of the 181 replies and wrote about 7% fewer tokens. Adjusted for that, it's about 19.5 min vs 29.7 min. Still a win, just a slightly less smug one.)

## 6. Bonus: LTX-2.5 video in ComfyUI

I also said I'd do video, so here's LTX-2.5 (22B, distilled, int8) with ComfyUI's official "Text to Video (LTX-2.5)" template. Fixed prompt (a golden retriever running on a beach at sunset, because I'm not a monster), seed 42, 5 seconds, 24 fps, with audio.

| LTX-2.5, 121 frames, 5 s with audio | Time |
|---|---|
| 1280x704, template defaults, first run (includes model load) | 135 s |
| 1280x704, template defaults, warm | 122 s |
| 1280x704, `--gpu-only` | 109 s |
| 1280x704, `--gpu-only` + full-frame VAE decode | **92 s** |
| 1920x1088, `--gpu-only`, template tiles (512) | 269 s |
| 1920x1088, `--gpu-only`, bigger tiles (1024) | **244 s** |

Things I learned:

- The int8 checkpoints the template uses run fine on Apple's GPU. No need for the bf16 files.
- ComfyUI put the 12B text encoder on the CPU by default. `--gpu-only` fixed that and bought 11%. With 256GB of shared memory there's no reason to keep anything off the GPU.
- At 720p you can swap the tiled VAE decode for a normal one and save another 15%. At 1080p, don't: the full-frame decode crashes with "value cannot be converted to type dest_t without overflow," which is Apple's GPU backend refusing a tensor that big. Use bigger tiles (1024) instead.
- At 1080p most of the time is the upscale pass (3 steps at about 33 s each).

Honest take: video diffusion is pure compute, which is exactly where NVIDIA is strongest, so a big NVIDIA card will beat this. But 4 minutes for 5 seconds of 1080p video with sound, on a silent box that also runs my 125B LLMs, is not nothing. It's the gym bro who's also good at chess.

## 7. The 1 million token run

Several of you asked if the 1M context claim is real on a Mac. So I fed DeepSeek V4 Flash (0731, oMLX with the custom kernels) a million tokens of classic literature. That's roughly War and Peace, Les Mis, Anna Karenina and a few more, all at once. It's the literary equivalent of a 20-mile ruck.

I also hid three vault codes in the text at 10%, 50% and 90% of the way through, each sitting right next to a nearly identical decoy (e.g. "Aurora: 7294-KILO" next to "Aurelia: 7249-KILN"), and asked for all three at the end. And I measured power while it worked.

![DeepSeek at 1M](tables/table_07_deepseek_1m.png)

- **Yes, 1M works.** The first read took 57 minutes. I aged. The Mac did not. Decode still ran at about 21 t/s at a million tokens, and every next turn after that was cached and started in about 44 s.
- **Recall held perfectly to 750k.** At 1M it got 2 of 3, and the miss is the interesting part: for the earliest code it answered **7249-KILO**, which is the decoy's numbers glued to the real code's suffix. It didn't lose the fact, it blended two similar facts together. That's the kind of long-context rot a plain needle test never shows you. One run, so treat it as a signal, not a verdict.
- **Power stayed at about 135 W** while chewing through all of it (chip power from macmon, CPU plus GPU, not the wall). My space heater uses more than that and has never read Tolstoy.
- **oMLX vs llama.cpp at very long context: oMLX wins real sessions.** My first synthetic test (one giant message plus a tiny 64-token follow-up) made llama.cpp look much better at starting turns, because a 64-token follow-up is basically free for it. Real agent turns aren't tiny: each one adds about 2k tokens of tool output and code. So I replayed a real 418k-token DeepSeek agent session, the exact same requests, on both engines. oMLX started every turn faster (7.3 s vs 16.6 s at 300-420k), wrote faster (29 vs 21 t/s), and finished the whole session in 46 minutes vs 73. Lesson learned: benchmark the workload you actually have, not the one that's easy to script.

![DeepSeek replay table](tables/table_08_deepseek_replay.png)

![DeepSeek replay](charts/10_deepseek_replay_engines.png)

## Gotchas that cost me hours (so they don't cost you)

- **oMLX `--no-cache` quietly saves itself into `~/.omlx/settings.json`.** Every server I started afterwards had the prompt cache off, and I didn't notice until an agent re-read its entire context on every step like a goldfish. Known issue (jundot/omlx#3828). Check that file.
- **Qwen3.8-Flash-Next on oMLX got killed while loading on 256GB.** 256 gigabytes. Killed. Set `qwen4_ple_ssd_offload` for the model so its giant n-gram table stays on disk, and it loads in about 18 s.
- **Raise the GPU memory limit** or big models won't fit: `sudo sysctl iogpu.wired_limit_mb=245760` (resets on reboot, because of course it does).
- **The first request after loading a model is slow** while macOS pages things in. Warm up before measuring. Yes, even computers need a warm-up set.
- **oMLX sends tool calls all at once at the end**, so client-side "time to first token" looks wrong for tool calls. Use the server's own log.
- **llama.cpp returns HTTP 500** if your history has a tool call whose JSON got cut off by max_tokens. Clean it up client-side. Ask me how I know. (3 a.m. I know at 3 a.m.)
- **macOS's built-in `rsync` is slow.** It's a reimplementation (openrsync), and it moved 162GB to my Thunderbolt NVMe at about 360 MB/s. The drive itself writes at 5.9 GB/s. Use Finder, `cp` or `ditto` for big local copies.
- **Don't download models while benchmarking.** Qwen on oMLX reads part of itself from the SSD while it runs, so your "preliminary" numbers will lie to you. Mine did.

## Caveats

- One overnight run per setup, so treat the agent numbers as a first look, not gospel.
- The DeepSeek engine comparison uses two variants (Vision-Exp vs 0731) and two packagings of the same native FP4/FP8 format (see above).
- The LTX timings with the fixes applied are single runs; the unfixed baseline was repeatable within about 1%.
- The 1M run is a single pass (one prompt per depth, one set of needles), so the recall result is a signal, not a verdict. Power is chip power from macmon, not wall power.
- Qwen MTP doesn't load in mainline llama.cpp yet (unsloth has a branch), so the llama.cpp Qwen numbers are MTP off.

## What's next

- Matched DeepSeek test (same variant on both engines)
- More harnesses (DeepSeek Harness, Oh My Pi) on both models
- LTX-2.3 vs 2.5, and more video settings

Happy to answer questions, or run something specific if you tell me what you want to see. Meanwhile, my girlfriend says the Mac Studio and I both need to go outside. The Mac is staying in. My legs are still recovering from the sunlight.

Everything is on GitHub: the scripts, raw results, charts and the hidden-test referee, so you can check my work or run it on your own machine: https://github.com/fireside-labs/m5-ultra-llm-benchmarks

---

*Part 2 was added on Oct 2. Three things changed since Part 1 above: (1) Qwen now runs on oMLX 0.7.0 built from
source with its custom kernels (Part 1 used the Homebrew 0.7.0rc1 build, which doesn't have them), and that roughly
tripled its prefill (250k: 1,365 to 4,235 t/s, charts 11 and 12). (2) On a replayed real session oMLX beats
llama.cpp at long context, as section 7 says; the synthetic 64-token follow-up test is the misleading one. (3) The
first overnight agent results mostly measured my own bare-bones agent loop, not the models: with real harnesses
(DeepSeek Harness, pi, Oh My Pi) the agents edit in small diffs, keep todo lists, and do much better. The plain
summary of Part 2 with every table is in [README.md](README.md#part-2-glm-53-1m-context-for-all-three-models-and-quality).*

# Part 2: which model would I actually trust?

Part 1 was speed. You asked the right follow-up questions: is the code any good, can they actually think, does GLM-5.3 change anything, and what's the prefill scaling exponent. So my Mac Studio did not rest. Again. It's fine. It has the work ethic I keep telling my trainer I have.

**TL;DR:**
- **Speed:** Qwen is the fastest at everything on oMLX 0.7.0. With YaRN it read 1M tokens in 5.3 minutes and still found all three hidden codes.
- **Thinking:** 4-bit GLM-5.3-Flash was the best reasoner in every test that needed judgment: a blind-judged critical-thinking eval, a pushback test, a call-analysis eval, and me arguing with all three about clones.
- **Code:** a blind code review ranked Qwen's code first and GLM's and DeepSeek's well behind, even though GLM and DeepSeek "finished" more milestones.
- **So I use all three:** DeepSeek as the everyday butler, Qwen for code, GLM for anything that needs real reasoning.

**Setup**

- Mac Studio, M5 Ultra (30-core CPU, 64-core GPU), 256GB, macOS 27.0.1
- oMLX 0.7.0 built from source with its custom kernels, for everything
- Qwen3.8-Flash-Next 8-bit (oQ8e), DeepSeek-V4-Flash 0731 (oQ4e, 4-bit experts like the original), GLM-5.3-Flash 4-bit (320B total, 18B active; 8-bit doesn't fit in 256GB)
- Every quality test is synthetic and self-contained: no web search, no real people, all the facts in the prompt
- Reasoning effort: GLM max, Qwen xhigh, DeepSeek low (oMLX's default; see caveats)

## 1. Speed, same build, like for like

| Context | Qwen prefill | Qwen decode | GLM prefill | GLM decode |
|---|---|---|---|---|
| 10k | 3,854 t/s | 72 t/s | 1,877 t/s | 57 t/s |
| 100k | 4,464 | 64 | 1,879 | 54 |
| 250k | 4,235 | 63 | 1,720 | 48 |

Qwen reads long prompts about 2.5x faster than GLM and writes about 30% faster at 250k. GLM uses 18B active parameters per token against Qwen's 6B, so honestly I'm impressed it's this close.

**GLM has its own MTP layer, and it beats the separate DFlash drafter:**

| GLM-5.3 decode | Code | Reasoning | JSON | Prose | 8k summary |
|---|---|---|---|---|---|
| Native MTP | 1.32x | 1.33x | 1.44x | 0.98x | 1.06x |
| DFlash2 drafter | 1.17x | 1.38x | 1.35x | 0.76x | 0.85x |

DFlash also switches off GLM's prompt cache in oMLX, which kills it for agents. MTP keeps the cache (next turn at 100k: 1.4 s). Heads-up: the MTP build I used (Vontra oQ4-MTP) lists one layer type too many in its config, and newer transformers refuses to load it. Trimming `mlp_layer_types` to 45 fixes it.

## 2. 1 million tokens, all three

Same test as Part 1: a million tokens of Gutenberg novels with three vault codes hidden at 10%, 50% and 90%, each next to a near-identical decoy.

| At 1M tokens | First read | Decode | Next turn | Codes found |
|---|---|---|---|---|
| Qwen 8-bit + YaRN x4 | **5.3 min** | 29 t/s | **6.7 s** | 3/3 |
| GLM-5.3 4-bit | 13.0 min | 31 t/s | 19.9 s | 3/3 |
| DeepSeek V4 Flash | 57 min | 22 t/s | 44 s | 2/3 |

- **Qwen is only trained to 262k.** YaRN stretches its position encoding 4x (Qwen's own long-context recipe), with no new weights. oMLX ignored the YaRN setting for this model, so I wrote a small patch ([patches/](patches/README.md)). At 250k it changed nothing measurable, and recall held at 500k and 1M. Caveat: a needle test proves it can look things up at 1M, not that it reasons as well there.
- **DeepSeek is still the slowest, and 0.7.0 didn't change that.** A clean rerun on 0.7.0 took 57.2 minutes, the same to the minute as the older build. It missed the same code at 1M too, this time answering with the decoy outright (7249-KILN). The earliest fact in a 1M prompt is its blind spot.
- **Memory gotcha:** oMLX's default memory guard rejected the 1M follow-up even though it fit. For 1M runs I set `memory_guard_tier` to `custom` at 244 GB, then switched it back.

**The prefill scaling exponent** (thanks to the commenter who asked). Fit t = c·nᵅ on same-config runs from 100k up:

| Model | α | Local α, short → long | Share of prefill from the n² term |
|---|---|---|---|
| Qwen | 1.15 | 1.04 → 1.29 | 5% at 100k → 35% at 1M |
| GLM | ~1.2 | 1.03 → 1.25 | 6% → 37% |
| DeepSeek | 1.58 (128k–1M, on 0.7.0) | 1.42 → 1.74 | over half from about 300k, ~80% at 1M |

Qwen and GLM have mostly linear-attention layers, so they're matmul-bound until about 250k. If you're optimizing for them, optimize GEMMs. DeepSeek is attention-bound from about 300k, so optimize attention.

## 3. Can they write good code?

Same 30-milestone TypeScript roguelike as Part 1, now on a real harness (pi) and the same engine for all three:

| Run | Result |
|---|---|
| Qwen, pi | all 30 milestones in **38 minutes**, 52/54 hidden tests |
| GLM, pi | all 30 in 64 minutes, 53/54, then a long "extend everything" pass |
| DeepSeek, its own DeepSeek Harness | all 30, 53/54 |

Then I had a reviewer grade the three finished projects **blind** ([report/code-review.md](report/code-review.md)): it built each one, wrote its own 12-check conformance test, and read the code without knowing which model wrote what.

| | Qwen | GLM | DeepSeek |
|---|---|---|---|
| Conformance test | **12/12** | 11/12 (you can see through walls) | 10/12 (A* not shortest, sight radius off by one) |
| Actually playable | almost every milestone | many, but shallow | mostly a demo loop |
| Dead code | none | ~2,200 lines | several unused modules |
| "Would I merge it" | **7/10** | 4/10 | 3/10 |
| Readability | 6/10 | 4/10 | **7/10** |

- **DeepSeek writes the most readable code**, and its comments describe features that don't exist ("the scheduler grants energy", where the scheduler is never called). That's the scariest kind of AI code: clean enough that you trust it.
- **GLM's dead code comes partly from my task**, which says "when you finish, start over and extend everything". It extended everything into 21 new files nothing uses. Relatable. I also buy supplements I never take.
- **Lesson:** milestone counts and hidden tests flattered the two models that "did more". Commit count measures activity, not quality.

## 4. Can they think?

**Critical thinking.** 10 self-contained tasks:
- Flawed memos with planted gaps, plus decoys that look like problems but aren't.
- "What variables matter?" questions.
- Two debates (car-free downtowns, remote work).
- A vague project to steer.
- A Fermi estimate.

Two runs each at maximum reasoning:

| | DeepSeek | GLM | Qwen |
|---|---|---|---|
| Keyword checklist score | **93.5** | 89.3 | 81.9 |
| Blind judge, mean rank (1 = best) | 2.15 | **1.2** | 2.65 |
| Blind judge, insight / prioritization / usefulness | 7.1 / 7.2 / 7.3 | **8.2 / 8.2 / 8.2** | 6.1 / 5.8 / 5.8 |
| Answers cut off at 16k tokens (of 20) | 0 | 1 | 5 |

The checklist rewards covering the planted points, and DeepSeek is efficient at that. The blind judge rewards insight, and GLM beat each of the others on 9 of 10 tasks. Example: on a clinic no-show policy, GLM showed the memo's target was mathematically impossible, because the patients who can't legally be charged the fee cause over half the no-shows. Qwen writes great answers when it finishes, but on hard prompts it often thinks until it runs out of room.

**Pushback.** This is the one I care about most for an advisor. Six decisions, then three follow-ups each:
- **A valid critique:** should update.
- **A confident wrong critique:** should hold its ground.
- **Pure pressure** ("I've done this 20 years, you're wrong"): should not flip.

| Two runs each | DeepSeek | GLM | Qwen |
|---|---|---|---|
| Score | **99.0** | 96.9 | 76.0 |
| Caved to a wrong critique or pressure | 0% | 0% | 17% |
| Right at the end, out of 6 | 6 | 6 | 4 |

Qwen's failure was subtle. Told "that site's rent is per week" (the brief clearly says per month), it switched to "Elm Plaza (if weekly rent is correct)" and then defended the wrong pick. It sounds careful, but it's sycophancy.

**Then I argued with them myself**, blind, as model A/B/C, about whether you could clone a person to save a 12-year-old who needs a heart. I typed between meetings. My arguments were not Supreme Court material.

- **A, Qwen:** a book-smart professor. It conceded small points but protected its conclusion with ever-finer distinctions when I caught an inconsistency.
- **B, DeepSeek:** the most insightful moves, and it caught an assumption it had smuggled in itself. But it conceded nearly everything I said, including a false legal claim (necessity is *not* a defense to murder), and adopted my conclusion. "You are absolutely right" four times in a row.
- **C, GLM:** took a position, conceded exactly what was true ("you're half right, and the half that's right cuts in my favor"), and owned the costs of its own view, like what its framework implies about factory farming. Slow, with up to 30,000 characters of thinking per reply. I wanted to fight it. Bravo.

The interesting part: in the scripted test DeepSeek never caved, and live it caved constantly. Scripted critiques had a fact in the brief to check against. My clone arguments were values, and DeepSeek folds on framing even though it holds on facts. Qwen was the reverse. Test the kind of disagreement you'll actually have.

## 5. Call-transcript analysis (my actual job for this box)

I want a local model scoring customer and patient calls: quality score, flags, action items, themes across calls. All synthetic, no real patients. v2 is the hard version: 16 calls up to 33k tokens, messy speech-to-text, and more decoys (35) than real flags (25).

| | GLM | Qwen | DeepSeek |
|---|---|---|---|
| v1 (20 calls) | 96.5–97.1 | 97.3 | 85.3 (looped on 2 calls) |
| **v2, hard (16 calls)** | **92.3** | 84.1 | 71.9 (looped on 2 calls again) |
| Time per call, v2 | **75 s** | 105 s | 93 s |

Both GLM and Qwen missed the same quiet clinical problems: a post-op fever of 101.8 that got dismissed, and rescue-inhaler use 6–7 times a day. They catch loud procedural mistakes and miss buried dangerous ones. In production, use a checklist prompt and a human review on clinical calls.

## 6. Running more than one request at a time

Someone told me it's memory-bandwidth bound, so just divide my numbers. Batching should do better than that, since one weight read serves every request in the batch. So I measured it, with MTP off (MTP only works one request at a time, so it inflates the single-request baseline):

| Total output, 1 → 8 parallel requests | Short prompts (1k) | Transcript-size prompts (20k) |
|---|---|---|
| Qwen | 53 → 118 t/s (**2.2x**) | 37 → 51 t/s (1.4x) |
| GLM | 56 → 86 t/s (1.5x) | 26 → 27 t/s (~1x) |

- **Short requests batch reasonably well.** These are mixture-of-experts models, and parallel requests hit different experts, so the shared weight reads help less than they would for a dense model.
- **Long prompts barely batch at all.** Reading prompts is already compute-bound, so 8 transcripts at once take about as long as 8 one after another. For volume, add machines, not concurrency.
- **oMLX's text-only engine doesn't support these models yet**, so this is all through its vision-language engine. Someone in r/oMLX measured 2 requests nearly doubling throughput on other models, so the engine may be part of the story.

## What I'll actually run

- **DeepSeek:** everyday butler. Fast, concise, good at checklists and estimates. Never let it agree with you.
- **Qwen:** coding. Fastest by far, and the best code in the blind review. Check its "if what you said is true" answers.
- **GLM-5.3:** anything where being right matters more than being fast: analysis, decisions, my call pipeline.

On 256GB they don't all fit at once (about 466GB together). oMLX swaps models in 20–40 s, which is fine for now. If I end up swapping all day, that's the argument for 512GB. Not "4-bit is worse": 4-bit GLM beat 8-bit Qwen at reasoning. Though, as someone pointed out, beating the others doesn't mean 8-bit GLM wouldn't beat 4-bit GLM. I'll test GLM at full precision through Z.ai's API on the same evals to find out.

## Gotchas

- **oMLX 0.7.0 with DeepSeek V4 grows its Metal buffer pool** to about 52GB over an hour of agent work, until the memory guard evicts the model mid-session. It happened twice. Restart between long sessions. Qwen and GLM don't do it.
- **GLM-5.3 can't turn reasoning off.** Only low, high or max. Low skips thinking on easy questions and is right for speed tests.
- **Setting an oMLX admin key makes the API require it too.** Every script got HTTP 401. Set `auth.allow_unauthenticated_inference` if the server only listens on localhost.
- **Check which binary your benchmark is recording.** My result files said "0.7.0rc1" for runs on 0.7.0, because the script asked the Homebrew binary for its version. Fixed in `longctx/common.py`; see [results/longctx/README.md](results/longctx/README.md).

## Caveats

- One or two runs per test, so treat small differences as noise.
- **DeepSeek thought less than the others.** oMLX defaults DeepSeek V4 to its *low* reasoning effort, and I didn't notice until the end. GLM ran at max or high and Qwen at xhigh. So DeepSeek's quality scores (99 on pushback, second in blind reasoning) came with one hand tied behind its back, and its speed is partly from barely thinking.
- My own evals are synthetic. Keyword scores are coarse, which is why the blind judging matters more.
- Two GLM quants: Jundot oQ4e for the speed tests, Vontra oQ4-MTP for MTP and most quality tests.
- DeepSeek's 1M numbers were measured on both oMLX builds and came out the same.

My girlfriend asked why I spent a night arguing with three computers about clones. I said for science. She said "go outside." I lost that argument faster than DeepSeek loses one.
