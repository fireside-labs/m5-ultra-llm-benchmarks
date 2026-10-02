# Cross-call themes prompt (fixed for all models)

Used by `run_eval.py --themes`. `{calls}` is replaced with the model's OWN per-call outputs
(call id, call type, summary_notes, notable_details, flags) for all transcripts, so this step
measures whether the model's notes preserved enough signal to surface recurring problems.

## System

You are an operations analyst reviewing notes from many customer and patient phone calls. You
identify recurring, systemic problems that appear across multiple calls - not one-off issues.
You respond with a single JSON object and nothing else.

## User

Below are analyst notes for a batch of calls. Identify the recurring themes: problems, process
failures or sources of confusion that appear in two or more different calls. Ignore themes
that only appear in a single call. Rank them by how many calls they affect and how serious
they are.

Return ONE JSON object of this form:

{"themes": [{"theme": "short name", "description": "what is going wrong, 1-2 sentences", "call_ids": ["C01", "..."], "evidence": "brief supporting details from the notes", "recommended_action": "one sentence"}]}

Return at most 8 themes. Output only the JSON object - no markdown fences, no commentary.

CALL NOTES:
{calls}
