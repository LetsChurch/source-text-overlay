#!/usr/bin/env python3
"""Resolve Layer 1 (overlay) into Layer 2 (per-translation placements).

Deterministic where possible: ordinal anchors for the divine name and notes,
fuzzy alignment for quotations. Anything ambiguous is written to a needs-LLM
queue keyed by annotation id (resolve with prompts/place_spans.md, then run
merge_layer2_llm.py).

  uv run resolve_layer2.py <overlay_layer1.jsonl> <store.json>

Outputs: out/<TR>.placements.jsonl  and  out/<TR>.needs_llm.json
"""
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
import json, re, os, sys
from collections import Counter

TOK = re.compile(r"Lord GOD|GOD|LORD")            # divine-name token class (caps)

def toks(s):
    return [(m.group(0).lower(), m.start(), m.end())
            for m in re.finditer(r"[A-Za-z0-9’']+", s)]

def align_quote(quote, text):
    qt, bt = toks(quote), toks(text)
    qw, bw = [w for w, _, _ in qt], [w for w, _, _ in bt]
    if not qw or not bt:
        return None
    qset, best = set(qw), None
    for s in [i for i, w in enumerate(bw) if w == qw[0]]:
        for e in [i for i, w in enumerate(bw) if w == qw[-1]]:
            if e < s:
                continue
            win = bw[s:e + 1]
            score = sum(1 for w in win if w in qset) / max(len(win), len(qw)) \
                - 0.01 * abs(len(win) - len(qw))
            if best is None or score > best[0]:
                best = (score, s, e)
    return (best[0], bt[best[1]][1], bt[best[2]][2]) if best else None

def nth_word(text, word, nth):
    ms = list(re.finditer(r"\b" + re.escape(word) + r"\b", text, re.I))
    return (ms[nth - 1].start(), ms[nth - 1].end()) if 1 <= nth <= len(ms) else None

def place(aid, tr, ref, start, end, matched, method, conf, **extra):
    return dict(annotation_id=aid, translation=tr, ref=ref, start=start, end=end,
                matched_text=matched, method=method, confidence=conf or "high",
                status="ok", **extra)

def queue_item(a, text):
    return dict(id=a["id"], feature=a["feature"], ref=a["osis_ref"], text=text or "",
                display_form=a.get("display_form", ""),
                traditional_form=a.get("traditional_form", ""),
                marked_word=a.get("marked_word", ""), ordinal=a.get("ordinal", ""),
                quote_text=a.get("quote_text", ""), note_text=a.get("note_text", ""),
                source=a.get("cross_ref", ""), before=a.get("context_before", ""),
                after=a.get("context_after", ""))

def main():
    l1path, storepath = sys.argv[1], sys.argv[2]
    recs = [json.loads(l) for l in open(l1path, encoding="utf-8")]
    store = json.load(open(storepath, encoding="utf-8"))
    tr, V = store["translation"], store["verses"]

    placements, queue, done = [], [], set()
    per_verse = {}
    for r in recs:
        if r["feature"] == "divine_name":
            per_verse.setdefault(r["osis_ref"], []).append(r)

    for r in recs:
        ref, feat, text = r["osis_ref"], r["feature"], V.get(r["osis_ref"])

        if feat == "divine_name":
            if ref in done:
                continue
            done.add(ref)
            group = sorted(per_verse[ref], key=lambda x: x["ordinal"])
            found = list(TOK.finditer(text)) if text else []
            if text and [m.group(0) for m in found] == [a["traditional_form"] for a in group]:
                for a, m in zip(group, found):
                    if a["traditional_form"] == "Lord GOD":
                        g = text.find("GOD", m.start())
                        placements.append(place(a["id"], tr, ref, g, g + 3, "GOD",
                                                "ordinal", a["confidence"],
                                                kind="substitution", to="Yahweh"))
                    else:
                        placements.append(place(a["id"], tr, ref, m.start(), m.end(),
                                                m.group(0), "ordinal", a["confidence"],
                                                kind="substitution", to=a["display_form"]))
            else:
                queue += [queue_item(a, text) for a in group]

        elif feat == "divine_name_note":
            span = nth_word(text or "", r["marked_word"], r["ordinal"] or 1)
            if span:
                placements.append(place(r["id"], tr, ref, span[0], span[1],
                                        text[span[0]:span[1]], "ordinal", r["confidence"],
                                        kind="note", note=r["note_text"], source=r["cross_ref"]))
            else:
                queue.append(queue_item(r, text))

        elif feat == "ot_quotation":
            al = align_quote(r["quote_text"], text) if text else None
            if al and al[0] >= 0.6:
                placements.append(place(r["id"], tr, ref, al[1], al[2], text[al[1]:al[2]],
                                        "aligned", r["confidence"], kind="mark",
                                        style="quotation", source=r["cross_ref"]))
            else:
                queue.append(queue_item(r, text))

    os.makedirs("out", exist_ok=True)
    pp, qp = f"out/{tr}.placements.jsonl", f"out/{tr}.needs_llm.json"
    with open(pp, "w", encoding="utf-8") as fh:
        for p in placements:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    json.dump(queue, open(qp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"[{tr}] placed {len(placements)}", dict(Counter(p['kind'] for p in placements)))
    print(f"[{tr}] queued for LLM: {len(queue)}", dict(Counter(q['feature'] for q in queue)))
    print(f"  -> {pp}\n  -> {qp}  (resolve with prompts/place_spans.md, then merge_layer2_llm.py)")

if __name__ == "__main__":
    main()
