#!/usr/bin/env python3
"""Fold LLM placement results into a translation's Layer-2 placements.

  uv run merge_layer2_llm.py <TRANSLATION_ID> <llm_result.json> [more.json ...]

Each result maps an annotation id -> {"find": "<exact substring of that item's
text>", "to": "<replacement>"|null}. Produced by prompts/place_spans.md over
out/<TR>.needs_llm.json. Appends resolved placements to out/<TR>.placements.jsonl.
"""
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
import json, sys

def diff_span(find, replace):
    n = min(len(find), len(replace)); p = 0
    while p < n and find[p] == replace[p]:
        p += 1
    s = 0
    while s < n - p and find[-1 - s] == replace[-1 - s]:
        s += 1
    return p, len(find) - s, replace[p:len(replace) - s]

def main():
    tr = sys.argv[1]
    queue = {q["id"]: q for q in json.load(open(f"out/{tr}.needs_llm.json", encoding="utf-8"))}
    res = {}
    for f in sys.argv[2:]:
        res.update(json.load(open(f, encoding="utf-8")))

    added = miss = skip = 0
    with open(f"out/{tr}.placements.jsonl", "a", encoding="utf-8") as out:
        for aid, r in res.items():
            q = queue.get(aid)
            if not q:
                continue
            find = (r or {}).get("find", "")
            if not find:
                skip += 1
                continue
            idx = q["text"].find(find)
            if idx < 0:
                miss += 1
                continue
            base = dict(annotation_id=aid, translation=tr, ref=q["ref"],
                        matched_text=find, method="model", confidence="medium", status="ok")
            if q["feature"] == "divine_name":
                a, b, to = diff_span(find, (r.get("to") or find))
                base.update(start=idx + a, end=idx + b, kind="substitution", to=to)
            elif q["feature"] == "divine_name_note":
                base.update(start=idx, end=idx + len(find), kind="note",
                            note=q["note_text"], source=q["source"])
            else:
                base.update(start=idx, end=idx + len(find), kind="mark",
                            style="quotation", source=q["source"])
            out.write(json.dumps(base, ensure_ascii=False) + "\n")
            added += 1
    print(f"[{tr}] merged {added} placements (find-miss {miss}, empty {skip})")

if __name__ == "__main__":
    main()
