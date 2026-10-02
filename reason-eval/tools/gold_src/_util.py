"""Tiny helpers for authoring gold files (see tools/build_gold.py)."""


def item(id, text, match, paraphrases, importance="normal", negatives=(), side=None, note=None):
    d = {"id": id, "text": text, "importance": importance, "match": match,
         "paraphrases": list(paraphrases)}
    if negatives:
        d["negatives"] = list(negatives)
    if side:
        d["side"] = side
    if note:
        d["note"] = note
    return d


def decoy(id, text, why_not, match, paraphrases):
    return {"id": id, "text": text, "why_not": why_not, "match": match, "paraphrases": list(paraphrases)}
