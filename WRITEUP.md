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

![cold vs warm](03_qwen_warm_vs_cold_ttft.png)

| | Cold (fresh prompt) | Warm (next step, cached) |
|---|---|---|
| Qwen, 250k context, llama.cpp | 234 s | 0.64 s |
| DeepSeek, 400k context, llama.cpp | 934 s | 1.23 s |
| DeepSeek, 500k context, llama.cpp | 1,311 s | 1.42 s |

Twenty-two minutes for the first answer at 500k. I went and made a protein shake. I came back. It was still thinking. I understood it on a spiritual level.

So the real question isn't "how fast is prefill," it's "how often do you pay it." A coding agent that keeps adding to the same conversation pays it basically once. A harness that keeps rewriting or summarizing the conversation pays it every single time, and at that point you're doing leg day every day, which is how people get hurt.

## 2. Qwen doesn't get tired (on oMLX)

Qwen3.8-Flash-Next only has 12 full-attention layers out of 48, and it shows. On oMLX its decode barely moves from 10k to 250k. On llama.cpp it gasps like me on the stairs after leg day.

![qwen decode](02_qwen_decode_vs_depth.png)

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

![what each fix bought](08_deepseek_what_each_fix_bought.png)

- llama.cpp with default settings: 628 t/s prefill
- llama.cpp with `-b 2048 -ub 2048`: 827 t/s (+31%, one flag, free gains, the creatine of settings)
- oMLX, Homebrew build: 1,204 t/s
- oMLX built from source with its custom kernels: 1,368 t/s
- Decode went from 32 t/s to 63 t/s on code with DSpark turned on

Important: the Homebrew build of oMLX doesn't include the custom Metal kernels for DeepSeek's sparse attention. The log literally tells you long-context prefill is "several times slower," in the tone of a coach who's disappointed but not surprised. If you run DeepSeek V4 on oMLX, build it from source with `OMLX_WITH_CUSTOM_KERNEL=1`. You need Xcode's Metal toolchain for that, which is a 20-minute download I will never get back.

Honest caveat: on DeepSeek the two engines didn't run the exact same file. llama.cpp ran Vision-Exp (unsloth UD-Q8_K_XL, which keeps DeepSeek's native FP4 experts and FP8-ish everything else, basically lossless, 162GB). oMLX ran 0731 (Jundot's oQ4e, a 4-bit mixed re-quant of the same native format, 154GB). The experts are 4-bit in both, so this is closer to fair than it looks, but it's a different variant and a re-quant, not byte-for-byte the same model. A matched test is on my list.

## 4. MTP and DSpark

Both guess a few tokens ahead. They're great on predictable stuff like JSON and code and do basically nothing for creative writing, which honestly relates to how I do at poetry.

![mtp dspark](07_mtp_dspark_speedup_by_task.png)

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

![replay](09_qwen_replay_engines.png)

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
- Qwen MTP doesn't load in mainline llama.cpp yet (unsloth has a branch), so the llama.cpp Qwen numbers are MTP off.

## What's next

- Matched DeepSeek test, and the full 600k to 1M run
- More harnesses (DeepSeek Harness, Oh My Pi) on both models
- LTX-2.3 vs 2.5, and more video settings

Happy to answer questions, or run something specific if you tell me what you want to see. Meanwhile, my girlfriend says the Mac Studio and I both need to go outside. The Mac is staying in. My legs are still recovering from the sunlight.

Everything is on GitHub: the scripts, raw results, charts and the hidden-test referee, so you can check my work or run it on your own machine: https://github.com/fireside-labs/m5-ultra-llm-benchmarks
