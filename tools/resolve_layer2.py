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

# --- Strong's heuristic ------------------------------------------------------
# When the store carries per-word Strong's numbers (the optional `tokens` map,
# §4), resolution can anchor by Strong's instead of surface wording — robust
# across translations regardless of how each renders a word. Two uses:
#   * divine name: find the n-th token whose Strong's is YHWH (works even when a
#     translation renders it "Yahweh"/"Jehovah" with no LORD-caps convention);
#   * quotation: align the annotation's `strongs` sequence to the verse tokens.

YHWH = {"H3068", "H3069"}  # YHWH (H3069 = YHWH pointed as Elohim, KJV "GOD")

def norm_strong(s):
    return re.sub(r"^([GH])0+(\d)", r"\1\2", s) if s else s

def vtokens(tokens, ref):
    """Per-verse [(strong, start, end)] from the store's optional token map."""
    return [(norm_strong(t[0]), t[1], t[2]) for t in tokens.get(ref, [])]

def align_strongs(seq, vt, min_cov=0.5):
    """LCS-align an annotation's Strong's sequence `seq` to a verse's Strong's
    tokens `vt`; return (start, end) of the matched run, or None when coverage is
    too weak. Robust to wording/word-order differences between translations."""
    a = [norm_strong(s) for s in seq if s]
    b = [(s, st, en) for s, st, en in vt if s]
    if not a or not b:
        return None
    bs = [s for s, _, _ in b]
    n, m = len(a), len(bs)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            dp[i][j] = dp[i + 1][j + 1] + 1 if a[i] == bs[j] \
                else max(dp[i + 1][j], dp[i][j + 1])
    i = j = 0
    matched = []
    while i < n and j < m:
        if a[i] == bs[j]:
            matched.append(j)
            i += 1
            j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    if len(matched) < max(2, int(len(a) * min_cov)):
        return None
    return (b[matched[0]][1], b[matched[-1]][2])

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
    TOKENS = store.get("tokens", {})  # optional per-word Strong's (§4)

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
            # Strong's heuristic: anchor each divine name to the n-th YHWH-tagged
            # token. Works for any translation (incl. ones that render "Yahweh"),
            # not just those using the LORD-caps convention the regex below needs.
            yhwh = [(st, en) for s, st, en in vtokens(TOKENS, ref) if s in YHWH]
            if text and len(yhwh) == len(group):
                for a, (st, en) in zip(group, yhwh):
                    placements.append(place(a["id"], tr, ref, st, en, text[st:en],
                                            "strongs", a["confidence"],
                                            kind="substitution", to=a["display_form"]))
                continue
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
            # Strong's heuristic first: if the annotation carries the quoted words'
            # Strong's sequence and the store has tokens, align by Strong's (robust
            # to differing wording). Fall back to surface-word alignment otherwise.
            sp = align_strongs(r["strongs"], vtokens(TOKENS, ref)) \
                if r.get("strongs") else None
            if sp:
                placements.append(place(r["id"], tr, ref, sp[0], sp[1],
                                        text[sp[0]:sp[1]], "strongs", r["confidence"],
                                        kind="mark", style="quotation",
                                        source=r["cross_ref"]))
                continue
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
