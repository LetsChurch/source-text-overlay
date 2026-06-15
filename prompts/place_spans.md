# Prompt: resolve overlay anchors to spans in a translation (Layer 2)

Use this to place the annotations the deterministic resolver (`resolve_layer2.py`)
could not place for a given translation. Run it over batches of
`out/<TRANSLATION>.needs_llm.json` (chunks of ~35 items). The result feeds
`merge_layer2_llm.py`.

---

You are aligning Bible-overlay annotations to a specific translation's wording.

INPUT: a JSON array of items. Each item:
- `id` — unique annotation id (echo it back unchanged)
- `feature` — `divine_name` | `ot_quotation` | `divine_name_note`
- `text` — the translation's verse text (your answer MUST be an exact substring of this)
- `before`, `after` — context around the original location (hints)
- For `divine_name`: `traditional_form` (the form to find, e.g. `LORD` or `Lord GOD`)
  and `display_form` (what to display instead, e.g. `Yahweh`, `Lord Yahweh`, `Yah`)
- For `ot_quotation`: `quote_text` (the quotation as worded in the overlay) and `source`
- For `divine_name_note`: `marked_word` (the word the note attaches to) and `note_text`

TASK: for each item, find the location in `text` and return it as a verbatim substring.

OUTPUT: write a JSON object mapping each `id` to `{"find": "...", "to": ...}`:
- `find` — an EXACT, character-for-character substring of that item's `text`
  (so it can be located programmatically). Copy punctuation/quotes exactly.
- `to`:
  - `feature == "divine_name"`: `find` should be a short, unique substring
    containing the divine-name word; set `to` to that same substring with ONLY
    the divine-name word swapped to `display_form` (`LORD`→`Yahweh`; the `GOD`
    in `Lord GOD`→`Yahweh`, giving `Lord Yahweh`). Change nothing else.
  - `feature == "ot_quotation"`: `find` = the contiguous span that is the
    quotation itself (exclude lead-ins like "as it is written"). Set `to` to `null`.
  - `feature == "divine_name_note"`: `find` = the single word the note attaches
    to (use `before`/`after` to pick the right occurrence). Set `to` to `null`.

RULES:
- If the translation genuinely has no corresponding text (uses a pronoun, omits
  the divine name, or renders the passage too differently), set `find` to `""`
  for that id — it will be skipped.
- Do not paraphrase; do not invent text that is not in `text`.

Write the JSON object to the output path you were given.
