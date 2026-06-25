# Scripture Overlay Specification

**Version 1.0**

A format for **overlays**: reusable, translation-independent sets of annotations
that add text-level features (substitutions, span markup, notes/cross-references)
to a Bible translation. One overlay is authored once and can be applied to any
translation. This spec defines two layers:

- **Layer 1 — the overlay** (canonical, translation-independent). *What* to add
  and *conceptually where*, anchored to verses without committing to any
  translation's exact wording.
- **Layer 2 — placements** (per-translation, derived). *Exactly where* each
  Layer-1 annotation lands in a specific translation's text (character/token
  ranges), produced by a resolution pass.

The text of each translation is stored separately and left untouched
("standoff" model); overlays are composed onto it at render time.

---

## 1. Concepts and data model

```
Overlay (Layer 1)                       Translation text store
  └─ Annotation* ──resolved into──►  Placement* (Layer 2) ──renders onto──► verse text
```

- An **Overlay** is a named, versioned collection of **Annotations**.
- An **Annotation** is one atomic feature at one location, described
  translation-independently.
- A **Placement** binds one Annotation to one Translation with concrete offsets.
- Multiple overlays may apply to the same text; each is independently toggleable.

### 1.1 Reference and versification

Every annotation is keyed to a **canonical verse reference** (e.g. OSIS-style
`Book.Chapter.Verse`) expressed in a declared **reference versification**
(an identifier such as `org.example.versification.standard`). Translations that
use a different versification are mapped during resolution (§5.2). References
MAY address sub-verse structure only through anchors (§3), never raw offsets.

---

## 2. Layer 1 — the overlay

### 2.1 Overlay envelope

```json
{
  "overlay_id": "string",          // stable unique id
  "title": "string",
  "version": "semver string",
  "versification": "string",       // reference scheme for all refs below
  "features": [                     // toggle groups (see §6)
    { "id": "string", "title": "string", "default_on": true }
  ],
  "annotations": [ Annotation, ... ]
}
```

### 2.2 Annotation

| Field | Req | Description |
|-------|-----|-------------|
| `id` | yes | Stable unique id (recommended: `<ref>/<kind>/<ordinal>`). |
| `ref` | yes | Canonical verse ref in the overlay's `versification`. |
| `kind` | yes | One of `substitution`, `mark`, `note` (§2.3). |
| `feature` | no | Id of a feature group for toggling (defaults to overlay-wide). |
| `anchor` | yes | How to locate within the verse, translation-independently (§3). |
| `payload` | yes | Kind-specific fields (§2.3). |
| `confidence` | no | `high` \| `medium` \| `low`. |
| `provenance` | no | Free-form source/method note for auditing. |

An annotation MUST NOT contain character offsets — those are Layer 2 only.

### 2.3 Annotation kinds

**`substitution`** — present alternative text in place of the anchored span
(e.g. an alternate rendering of a term). Toggleable.

```json
"payload": {
  "expect": "string|null",   // optional base text expected at the anchor (a check)
  "replace_with": "string",  // text to display instead
  "mode": "replace"          // "replace" | "prefix" | "suffix"
}
```

**`mark`** — apply a semantic style to a span (e.g. a quotation, an emphasized
phrase). Carries an optional reference to related material.

```json
"payload": {
  "style": "string",         // semantic class, e.g. "quotation", "title"
  "attrs": { "source": "string" }   // optional, e.g. a cross-referenced passage
}
```

**`note`** — attach a note to an anchored point or span.

```json
"payload": {
  "note_type": "footnote",   // "footnote" | "cross_reference" | "comment"
  "body": "string",          // human-readable note text (may be empty)
  "targets": ["string"]      // optional list of referenced passages
}
```

---

## 3. Anchoring (translation-independent location)

An anchor says where the annotation applies *without* knowing the translation's
exact wording. Resolution (§5) turns it into offsets. An anchor declares a
`strategy` plus the data that strategy needs; it SHOULD also carry `hints` to
make resolution robust and verifiable.

| `strategy` | Locates | Required data | Resolves deterministically? |
|-----------|---------|---------------|------------------------------|
| `verse` | the whole verse | — | yes |
| `ordinal` | the *n*-th token of a class | `match` (token class/literal/regex), `ordinal` (1-based) | yes, if the translation marks the class |
| `phrase` | a contiguous run matching a reference phrase | `phrase` (reference wording) | partially (fuzzy/model) |
| `source` | the run quoting an external passage | `source` (passage ref) | partially (fuzzy/model) |

```json
"anchor": {
  "strategy": "ordinal",
  "match": "TOKEN_CLASS_OR_LITERAL",
  "ordinal": 1,
  "hints": { "before": "…preceding words…", "after": "…following words…",
             "expected": "the form expected in a typical translation" }
}
```

Notes:
- `ordinal` is the workhorse for token-level features whose position is fixed by
  the underlying (original-language) text: any faithful translation has the same
  ordered occurrences, so the *n*-th maps directly. The `match` value is a
  class name the resolver knows how to detect in a translation (e.g. a tagged
  token, or a casing convention), or a literal/regex.
- `phrase`/`source` anchors are for spans whose wording varies between
  translations; they require alignment (fuzzy match and/or a model) and SHOULD
  always be stored with `hints`.
- `hints.before`/`after` are short context windows used to disambiguate and to
  validate a resolved placement.

---

## 4. Translation text store

Each translation is stored as plain, normalized verse text — the substrate that
offsets are measured against.

```json
{ "translation": "string", "versification": "string",
  "verses": { "Book.Chapter.Verse": "normalized verse text", ... } }
```

**Optional Strong's token layer.** A store MAY carry a `tokens` map alongside
`verses`, giving the per-word Strong's numbers with their offsets into the
normalized verse text:

```json
"tokens": { "Book.Chapter.Verse": [ ["H3068", 4, 8], ["G2424", 12, 19], ... ] }
```

Each entry is `[strong, start, end]` in the store's declared offset unit. This is
the substrate for the **Strong's heuristic** in resolution (§5.2): because Strong's
numbers are language- and translation-independent, anchoring to them is far more
robust than matching surface wording or a casing convention. The layer is optional
and additive — a text-only store resolves exactly as before. Build it from any
Strong's-tagged source (interlinear, tagged translation); plain text sources simply
omit it.

**Normalization (REQUIRED, declared per store).** Offsets are only meaningful
against an exact byte/character sequence, so the store MUST fix and document:
- whitespace handling (e.g. collapse runs to single spaces, trim ends),
- which inline elements are included/excluded (e.g. translator footnote markers
  excluded; supplied words included),
- Unicode normalization form (NFC recommended).

**Offset unit (REQUIRED).** Declare the unit: **Unicode code points** is
recommended for portability. Implementations in environments that index strings
by UTF-16 code units (e.g. JavaScript) MUST convert, or the store MUST publish
offsets in UTF-16 units. For text in the Basic Multilingual Plane the two
coincide; declaring the unit avoids ambiguity for any astral characters.

---

## 5. Layer 2 — placements (resolution)

### 5.1 Placement record

| Field | Req | Description |
|-------|-----|-------------|
| `annotation_id` | yes | FK to the Layer-1 annotation. |
| `translation` | yes | Translation id. |
| `ref` | yes | Verse ref in the *translation's* versification (post-mapping). |
| `start`, `end` | yes* | Half-open offset range into the normalized verse text (`*` omit/zero-length for whole-verse or pure-point notes). |
| `matched_text` | no | The base substring matched (for audit/validation). |
| `method` | yes | `ordinal` \| `strongs` \| `aligned` \| `model` \| `manual`. |
| `confidence` | no | `high` \| `medium` \| `low`. |
| `status` | yes | `ok` \| `needs_review` \| `unresolved`. |

A placement is purely derived data; it can always be regenerated from Layer 1 +
the translation text store.

### 5.2 Resolution pipeline (overlay + translation → placements)

For each annotation:

1. **Map versification.** Translate `ref` from the overlay's versification to the
   translation's; if a verse is merged/split/absent, record the adjusted `ref`
   or mark `unresolved`.
2. **Resolve the anchor** to `[start, end)`:
   - `verse` → whole verse.
   - `ordinal` → the *n*-th occurrence of `match` in the verse text. Deterministic
     when the translation exposes the token class. **Strong's heuristic:** when the
     store has a `tokens` layer (§4) and the class is a Strong's number (e.g. the
     divine name as the *n*-th YHWH-tagged token, `H3068`/`H3069`), anchor to that
     token directly — robust even when a translation renders it "Yahweh"/"Jehovah"
     with no LORD-caps convention.
   - `phrase` / `source` → fuzzy-align the reference phrase / quoted passage to a
     contiguous span; if alignment is weak, fall back to a model, then to manual.
     **Strong's heuristic:** when the annotation carries the quoted words' Strong's
     sequence and the store has a `tokens` layer, align by Strong's (LCS) instead of
     surface words — robust to wording/word-order differences between translations.
3. **Validate** against `hints` and `payload.expect`; downgrade `confidence` or set
   `status = needs_review` on mismatch.
4. **Emit** a placement. Unresolvable anchors get `status = unresolved` (the
   feature is simply not shown for that translation/verse).

Recommended ordering: try deterministic (`ordinal`) first; reserve model/manual
effort for `phrase`/`source` spans and the deterministic tail that fails
validation. Adding a translation is re-running this pipeline — Layer 1 is never
re-authored.

---

## 6. Rendering (placements + text → output)

Render = take the normalized verse text and splice in markup for the placements
whose `feature` is enabled. Because data is standoff, feature toggles are pure
view state and a single stored payload serves every combination.

Algorithm (single forward pass; handles disjoint ranges with nested points):
1. Collect, per enabled placement: an **open** marker at `start`, a **close**
   marker at `end`, point **inserts** (for notes) at their position, and—for
   `substitution`—a replacement of `[start,end)`.
2. Walk the text; at each position emit closes, then point inserts, then opens;
   for a substitution range, emit the replacement instead of the original span.
3. Markers are output-specific (HTML spans/footnote refs, USFM/OSIS tags, etc.).

**Overlap rules.** Within one verse, ranges of the same overlay SHOULD be
disjoint; point annotations MAY fall inside a range. If two overlays produce
overlapping ranges, the renderer MUST define a deterministic precedence (e.g.
overlay order) and MAY split one range to keep markup well-formed.

---

## 7. Serialization & storage

- **Source of truth (Layer 1):** newline-delimited JSON (**JSONL**), one
  annotation per line, in version control. Diff-friendly, hand-editable,
  language-agnostic. The overlay envelope (§2.1) is a companion file.
- **Runtime (Layer 1 + Layer 2):** a relational store (e.g. SQLite/SQL) compiled
  from the JSONL — never hand-edited — with indexes on `(translation, ref)` and
  `feature`.
- **Do not** use inline scripture markup formats (USFM/OSIS and similar) for
  Layer 1: those embed markup in one specific text and are the wrong shape for a
  translation-independent, standoff overlay. They are appropriate as *export*
  targets of a rendered (placed) translation.

### 7.1 Web delivery (read-only data)

Overlay + text is small and read-only, so precompute and serve **static
per-book or per-chapter payloads** from a CDN; no live database is required on
the request path. A payload carries the base verse text plus the resolved
placements as offset ranges, so the client applies feature toggles itself:

```json
{ "translation": "T", "code": "BBB", "chapters": [
  { "c": 1, "verses": [
    { "v": 1, "text": "…base verse text…",
      "ann": [ { "t": "substitution", "s": 12, "e": 19, "to": "…" },
               { "t": "mark", "s": 40, "e": 78, "style": "quotation", "src": "…" },
               { "t": "note", "s": 74, "e": 78, "note_type": "footnote", "body": "…" } ] }
  ] } ] }
```

Verses with no annotations carry only `text`. Offsets are into `text` under the
store's declared offset unit (§4).

---

## 8. Worked examples (generic)

**Substitution** — show an alternate rendering of a term, as the 1st occurrence
of a marked token class:

```json
{ "id": "Book.3.5/substitution/1", "ref": "Book.3.5", "kind": "substitution",
  "feature": "alt-term",
  "anchor": { "strategy": "ordinal", "match": "TERM_CLASS", "ordinal": 1,
              "hints": { "before": "…", "after": "…", "expected": "Term" } },
  "payload": { "expect": "Term", "replace_with": "Alternate", "mode": "replace" } }
```

**Mark** — style a quotation span and record its source:

```json
{ "id": "Book.7.2/mark/1", "ref": "Book.7.2", "kind": "mark", "feature": "quotations",
  "anchor": { "strategy": "source", "source": "Other.40.3",
              "hints": { "before": "as written,", "after": "— so it is." } },
  "payload": { "style": "quotation", "attrs": { "source": "Other.40.3" } } }
```

**Note** — attach a cross-reference footnote to the 2nd occurrence of a token:

```json
{ "id": "Book.7.2/note/1", "ref": "Book.7.2", "kind": "note", "feature": "xrefs",
  "anchor": { "strategy": "ordinal", "match": "WORD", "ordinal": 2,
              "hints": { "before": "…", "after": "…" } },
  "payload": { "note_type": "cross_reference", "body": "see Other.40.3",
               "targets": ["Other.40.3"] } }
```

---

## 9. Conformance

An implementation is conformant if it:
1. stores Layer 1 with no character offsets and Layer 2 as derivable placements;
2. keeps translation text standoff (unmodified) with a declared normalization and
   offset unit;
3. resolves anchors per §5 and renders per §6, honoring feature toggles;
4. can regenerate all Layer-2 data for a translation from Layer 1 + that
   translation's text alone.
```
