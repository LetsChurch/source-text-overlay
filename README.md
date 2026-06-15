# Source Text Overlay

A reusable, **translation-independent** set of scripture annotations that surface
the underlying source text, plus the tooling to apply them to any Bible
translation. It is one concrete overlay built on the generic model in
[`SPEC.md`](SPEC.md).

The overlay carries three kinds of annotation (7,502 total), each connecting the
printed translation back to its source text:

| Feature (`feature`) | Count | What it marks |
|---------------------|------:|---------------|
| `divine_name` | 6,888 | Where the Hebrew has the divine name — render it (`Yahweh` / `Lord Yahweh` / `Yah`) in place of a translation's `LORD` / `Lord GOD`. |
| `ot_quotation` | 506 | Old Testament text quoted inside the New Testament — a span to style, with the source passage. |
| `divine_name_note` | 108 | Places where the New Testament's "Lord" stands for the divine name in the Old Testament — a footnote with the source. |

Nothing here is tied to a particular translation: the annotations are anchored to
verses and to *positions described abstractly* (which divine-name slot, which OT
source, which word), then **resolved** to exact offsets per translation.

## Layout

```
SPEC.md                       generic two-layer overlay specification
overlay/
  overlay_layer1.jsonl        Layer 1 — the annotations (source of truth, one per line)
  overlay.sqlite              Layer 1 — same data, compiled & indexed for queries
tools/
  build_text_store.py         build a per-translation text store (from a helloao complete.json)
  resolve_layer2.py           Layer 1 + a translation -> Layer 2 placements (+ an LLM queue)
  merge_layer2_llm.py         fold LLM placement results back into Layer 2
prompts/
  place_spans.md              the prompt for the LLM placement step
```

Scripts are pure Python stdlib (no dependencies) and `uv`-runnable.

## The two layers (see SPEC.md for the full spec)

- **Layer 1** — these annotations, keyed by OSIS verse ref, with **no character
  offsets**. Authored once; reused for every translation.
- **Layer 2** — per-translation *placements*: each annotation resolved to a
  concrete `[start, end)` range in that translation's verse text. Always derived,
  never hand-authored.

### Layer 1 record fields (`overlay/overlay_layer1.jsonl`)

`id`, `osis_ref`, `book`, `chapter`, `verse`, `testament`, `feature`, `ordinal`
(which slot/occurrence in the verse), `display_form` & `traditional_form`
(`divine_name`), `marked_word` & `note_text` (`divine_name_note`), `quote_text`
(`ot_quotation`), `cross_ref` (the OT source) & `cross_ref_method`
(`footnote` = authored, `inferred` = derived), `confidence`,
`context_before` / `context_after` (hints for re-anchoring).

## Apply to a translation

```sh
# 1. build a normalized text store for the translation
uv run tools/build_text_store.py path/to/<translation>_complete.json ESV
#    -> out/stores/ESV.store.json     (or pass your own store, see SPEC.md §4)

# 2. resolve Layer 1 -> Layer 2 (deterministic part)
uv run tools/resolve_layer2.py overlay/overlay_layer1.jsonl out/stores/ESV.store.json
#    -> out/ESV.placements.jsonl      deterministic placements
#    -> out/ESV.needs_llm.json        the ambiguous tail

# 3. resolve the tail with an LLM using prompts/place_spans.md over
#    out/ESV.needs_llm.json (batches of ~35), producing result JSON files

# 4. merge those results in
uv run tools/merge_layer2_llm.py ESV result_0.json result_1.json ...
#    -> appends to out/ESV.placements.jsonl
```

What's deterministic vs. LLM-assisted:

- **`divine_name`** resolves by *ordinal anchor* — the n-th divine-name token —
  which is fixed by the underlying Hebrew, so any translation that marks its
  divine name (`LORD` / `Lord GOD`) resolves with no LLM. Typically ~97%; the
  tail is where a translation uses a pronoun or omits the name.
- **`divine_name_note`** resolves by the n-th occurrence of the marked word.
- **`ot_quotation`** resolves by fuzzy alignment of the quotation; the rest go to
  the LLM, since wording varies between translations.

`tools/build_text_store.py` reads the JSON shape published by
`bible.helloao.org` (`/api/<TR>/complete.json`); for any other source, emit a
store in the SPEC.md §4 format and skip step 1.

## Rendering (standoff)

Keep the translation text untouched; store placements separately; splice markup
at render time (SPEC.md §6). Because it's standoff, feature toggles
(show-divine-name, mark-quotations, footnotes) are pure view state and one
payload serves every combination. A `mark`/`note`/`substitution` placement
carries everything a renderer needs: range, kind, and (`to` / `source` / `note`).
