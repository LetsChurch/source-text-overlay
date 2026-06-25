#!/usr/bin/env python3
"""Build a text store (one normalized verse per OSIS ref) for a translation from
a bible.helloao.org `complete.json`. The store is what Layer-2 offsets are
measured against.

  uv run build_text_store.py <complete.json> <TRANSLATION_ID> [out.json]

Default output: out/stores/<TRANSLATION_ID>.store.json
"""
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
import json, re, os, sys

OSIS = ["Gen","Exod","Lev","Num","Deut","Josh","Judg","Ruth","1Sam","2Sam","1Kgs",
"2Kgs","1Chr","2Chr","Ezra","Neh","Esth","Job","Ps","Prov","Eccl","Song","Isa","Jer",
"Lam","Ezek","Dan","Hos","Joel","Amos","Obad","Jonah","Mic","Nah","Hab","Zeph","Hag",
"Zech","Mal","Matt","Mark","Luke","John","Acts","Rom","1Cor","2Cor","Gal","Eph","Phil",
"Col","1Thess","2Thess","1Tim","2Tim","Titus","Phlm","Heb","Jas","1Pet","2Pet","1John",
"2John","3John","Jude","Rev"]

def main():
    src, trid = sys.argv[1], sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else f"out/stores/{trid}.store.json"
    d = json.load(open(src, encoding="utf-8"))
    verses, tokens = {}, {}
    for i, bk in enumerate(d["books"]):
        for cc in bk["chapters"]:
            c = cc["chapter"]
            for it in c["content"]:
                if it.get("type") != "verse":
                    continue
                # Build the normalized verse text incrementally so we can record a
                # [strong, start, end] token for any content part that carries a
                # Strong's number (codepoint offsets into the text). Plain strings
                # contribute text only — the result is the same as before, plus an
                # optional token layer the resolver uses as a Strong's heuristic.
                text, toks = "", []
                for x in it["content"]:
                    if isinstance(x, str):
                        w, strong = re.sub(r"\s+", " ", x).strip(), None
                    elif isinstance(x, dict):
                        w = re.sub(r"\s+", " ", x.get("text", "")).strip()
                        strong = next((x[k] for k in ("strong", "strongs",
                                       "strongsNumbers") if x.get(k)), None)
                        if isinstance(strong, list):
                            strong = strong[0] if strong else None
                    else:
                        continue
                    if not w:
                        continue
                    if text:
                        text += " "
                    start = len(text)
                    text += w
                    if strong:
                        toks.append([strong, start, len(text)])
                ref = f"{OSIS[i]}.{c['number']}.{it['number']}"
                verses[ref] = text
                if toks:
                    tokens[ref] = toks
    store = dict(translation=trid, versification="helloao.standard",
                 normalization="collapse-ws;trim;exclude-notes;NFC-source",
                 offset_unit="codepoint", verses=verses)
    if tokens:
        store["tokens"] = tokens  # optional Strong's layer (§4)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(store, open(out, "w"), ensure_ascii=False)
    print(f"wrote {out}: {len(verses)} verses")

if __name__ == "__main__":
    main()
