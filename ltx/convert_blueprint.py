#!/usr/bin/env python3
"""Flatten a ComfyUI subgraph blueprint into API-format JSON using live /object_info.
Usage: convert_blueprint.py BLUEPRINT OUT.json [--prompt TEXT] [--seed N] [--unet F] [--clip F] [--server URL]"""
import argparse, json, urllib.request

CONTROL = {"fixed", "increment", "decrement", "randomize"}
WIDGET_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO", "COMFY_DYNAMICCOMBO_V3"}

def is_widget(spec):
    t = spec[0]
    if isinstance(t, list):
        return True
    opts = spec[1] if len(spec) > 1 else {}
    if t in WIDGET_TYPES:
        return True
    if isinstance(t, str) and "," in t and opts.get("widgetType"):
        return True
    return False

def widget_names(inputs_def, values, prefix=""):
    """Walk required+optional in order; returns list of (name, value) consuming values."""
    out = []
    i = 0
    def walk(defs, pre):
        nonlocal i
        for sect in ("required", "optional"):
            for name, spec in (defs.get(sect) or {}).items():
                if not is_widget(spec):
                    continue
                if i >= len(values):
                    return
                full = pre + name
                v = values[i]; i += 1
                out.append((full, v))
                opts = spec[1] if len(spec) > 1 else {}
                if (opts.get("control_after_generate") or name in ("seed", "noise_seed")) \
                        and i < len(values) and values[i] in CONTROL:
                    i += 1
                if spec[0] == "COMFY_DYNAMICCOMBO_V3":
                    for o in opts["options"]:
                        if o["key"] == v:
                            walk(o.get("inputs", {}), full + ".")
    walk(inputs_def, prefix)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("blueprint"); ap.add_argument("out")
    ap.add_argument("--prompt"); ap.add_argument("--seed", type=int)
    ap.add_argument("--unet"); ap.add_argument("--clip")
    ap.add_argument("--server", default="http://127.0.0.1:8188")
    ap.add_argument("--prefix", default="ltx/ltx25_t2v")
    a = ap.parse_args()
    oi = json.load(urllib.request.urlopen(a.server + "/object_info"))
    bp = json.load(open(a.blueprint))
    outer = bp["nodes"][0]
    sg = {s["id"]: s for s in bp["definitions"]["subgraphs"]}[outer["type"]]
    outer_vals = dict(outer["widgets_values_named"])
    if a.prompt is not None: outer_vals["text"] = a.prompt
    if a.seed is not None: outer_vals["noise_seed"] = a.seed
    if a.unet: outer_vals["unet_name"] = a.unet
    if a.clip: outer_vals["clip_name"] = a.clip
    sg_in_names = [x["name"] for x in sg["inputs"]]
    links = {l["id"]: l for l in sg["links"]}
    api = {}
    for n in sg["nodes"]:
        if n.get("mode", 0) in (2, 4):
            raise SystemExit(f"node {n['id']} muted/bypassed: not handled")
        d = oi[n["type"]]
        inputs = {}
        for name, v in widget_names(d["input"], n.get("widgets_values") or []):
            inputs[name] = v
        for inp in n.get("inputs", []):
            lid = inp.get("link")
            if lid is None: continue
            l = links[lid]
            if l["origin_id"] == -10:
                inputs[inp["name"]] = outer_vals[sg_in_names[l["origin_slot"]]]
            else:
                inputs[inp["name"]] = [str(l["origin_id"]), l["origin_slot"]]
        if a.seed is not None:
            for k in list(inputs):
                if k.split(".")[-1] in ("seed", "noise_seed") and not isinstance(inputs[k], list):
                    inputs[k] = a.seed
        api[str(n["id"])] = {"class_type": n["type"], "inputs": inputs,
                             "_meta": {"title": n.get("title", n["type"])}}
    # blueprint's VIDEO output goes to the subgraph boundary; add a SaveVideo
    for l in sg["links"]:
        if l["target_id"] == -20:
            api["9000"] = {"class_type": "SaveVideo", "inputs": {
                "video": [str(l["origin_id"]), l["origin_slot"]],
                "filename_prefix": a.prefix, "format": "auto", "format.codec": "auto"},
                "_meta": {"title": "Save Video"}}
    json.dump(api, open(a.out, "w"), indent=2)
    print(f"wrote {a.out}: {len(api)} nodes")

if __name__ == "__main__":
    main()
