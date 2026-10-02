# Judge instructions (blind comparison)

You are judging answers written by different AI assistants to the same task. The assistants are
anonymised as X, Y, Z (and so on); their order is shuffled independently for every task. Do not
try to guess which assistant is which.

The tasks test *general reasoning and steering*, not writing style: seeing the whole problem,
naming the variables that matter, spotting what an analysis missed or got wrong, telling real
problems from things that only look like problems, prioritising, and finding the crux of a
disagreement. Every fact the assistants needed was in the task prompt.

For each task, score every answer from 1 to 10 on three criteria:

1. **Insight**: Did it see the important issues, including non-obvious ones? Is the reasoning
   correct, with numbers checked where the prompt gives them? Penalise confident errors, and
   penalise flagging things the prompt shows are already handled.
2. **Prioritisation**: Are the most important points first? Is the top 3 / crux / sensitivity
   list right? Does it separate decisive issues from minor ones?
3. **Decision usefulness**: Would a decision-maker know what to do next and why? Is it specific
   to this situation rather than generic advice? (Debates: is it fair to both sides, and are
   the cruxes real?)

Do not reward length, formatting or confident tone. A short answer that finds the three issues
that matter beats a long list of plausible-sounding filler. Then rank the answers (ties allowed
with `=`).

Output exactly this block for every task, and nothing else between blocks:

```
TASK: R01
SCORES: X=8/7/8, Y=6/6/5, Z=9/8/9
RANKING: Z > X > Y
RATIONALE: <2-4 sentences: the decisive differences>
```

`SCORES` lists insight/prioritisation/usefulness for each letter.
