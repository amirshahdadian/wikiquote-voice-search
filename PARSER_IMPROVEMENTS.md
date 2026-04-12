# Wikiquote Parser Improvements

## Overview

This document describes the changes made to the Step 1 Wikiquote parsing pipeline
(`backend/app/cli/ingest.py`, `backend/app/core/settings.py`). The goal was to bring a 1.3M-quote bloated
corpus down to a high-quality, correctly-attributed dataset suitable for the autocomplete
and voice search system.

---

## Before vs. After

| Metric | Before | After |
|--------|--------|-------|
| Total quotes | 1,300,000 | **364,017** |
| `author == source` | ~tens of thousands | **326 (0.09%)** |
| `source_locator == source` | widespread | **0** |
| TV/film transcript quotes | ~500,000+ | **0** (taglines only) |
| Films misclassified as literary works | many (at 150-quote cap) | **fixed** (at 25-quote cap) |
| Min words per quote | 3 | **5** |
| Near-duplicate rows (same quote, different sub-section) | many | **eliminated** |

---

## Root Causes of the 1.3M Inflation

### 1. TV and Film Transcript Extraction
Every colon-prefixed dialogue line (`:`) on TV and film pages was being extracted as a
quote. A single TV season page (e.g. *The Simpsons* Season 3) could yield hundreds of
lines like `Homer: D'oh.` The academic baseline for English Wikiquote
([QuoteKG, arXiv:2207.09562](https://arxiv.org/abs/2207.09562)) reports ~271K quote
mentions — our 1.3M was nearly **5× higher**.

### 2. No Per-Page Cap
There was no limit on how many quotes could be extracted from a single page, allowing
transcript-heavy pages to dominate the entire corpus.

### 3. `min_words = 3`
A 3-word threshold let short TV filler lines like `"Come on"`, `"I don't know"`, and
`"What is it"` pass through validation.

### 4. Broken Translation Detection
The `_looks_like_translation` method used a length-similarity heuristic: if a `**`
sub-bullet was similar in length to the parent quote, it was treated as a translation
and **swapped into the quote field**, corrupting both the quote text and its attribution.

### 5. Occurrence Key Too Granular
The deduplication key included `citation`, `context`, and `source_locator`. This meant
the same Einstein quote appearing in a `=== 1930s ===` sub-section and a `=== 1940s ===`
sub-section counted as two separate entries.

### 6. `source_locator` Repeating `source`
The sub-bullet parser wrote the same work title into `source`, `work`, and
`source_locator` simultaneously, producing three identical fields on most quotes.

### 7. Films Misclassified as Literary Works
Many film pages (e.g. *Casablanca*, *Aliens*, *The Princess Bride*) matched the
`_looks_like_literary_work_page` heuristic before reaching the film check, because
their intros contained phrases like `"based on the 1973 novel"` or `"is a romantic drama"`.
These were extracted at the **150-quote person cap** instead of the correct **25-quote
film cap**.

### 8. Year-Qualified Titles Not Detected as Film/TV
Titles like `"Around the World in 80 Days (2004 film)"` and `"Danger Mouse (1981 TV series)"`
didn't match the patterns `\(film\)` or `\(tv series\)`. They fell through to the
person-page heuristic which fired on their intros (mentioning actor roles or multiple
years), misclassifying them as person pages.

### 9. Theme Pages: Unattributed Quotes Duplicating Person Pages
Theme pages (Love, Courage, Freedom…) contain bullet quotes without `**` attribution
sub-bullets. These are anonymous duplicates of quotes already on person pages, with no
additional provenance.

### 10. Author = Work Title on Literary Work Pages
When author-inference failed (no `"by Author"` pattern in the intro), the page title was
used as the fallback `default_author`. This produced Author nodes like
`author="Human, All Too Human"` — a Nietzsche work used as a person's name.

---

## Changes Made

### `backend/app/core/settings.py`
- **`QUOTE_MIN_WORDS`: 3 → 5**
  Eliminates short filler lines that are not meaningful quotes.

---

### `backend/app/cli/ingest.py`

#### TV/Film: Taglines-Only Extraction
```
Before: All sections extracted (Season 1, Season 2, episode sub-sections,
        every colon-line of dialogue)
After:  Only == Taglines == sections extracted from tv_show and film pages
```
This single change accounts for the majority of the corpus reduction.

#### Per-Page Quote Cap
```
Before: No limit
After:  person / literary_work / theme → 150 quotes max
        film / tv_show                 → 25 quotes max
```

#### Colon-Line Guard on TV/Film (Defence in Depth)
Even if a TV/film page slips through the section whitelist, colon-prefixed
dialogue lines are now explicitly skipped for `tv_show` and `film` page types.

#### `_looks_like_translation` — Explicit Markers Only
```
Before: Triggered when a sub-bullet was similar in length to the parent quote
        (length-similarity heuristic) → swapped attribution into quote field

After:  Only triggers on explicit markers: "translation:", "trans:", "english:",
        "meaning:"
```

#### `_build_occurrence_key` — Simplified Deduplication
```
Before: MD5 of (fingerprint + page_title + source + source_locator + citation + context)
After:  MD5 of (fingerprint + page_title + source)
```
Removed `citation`, `context`, and `source_locator` from the key. Including them
created 3–5× near-duplicate rows for the same quote appearing in different
sub-sections of the same page.

#### `_finalize_quote` — Clear Redundant `source_locator`
```
Before: source="Mein Weltbild", work="Mein Weltbild", source_locator="Mein Weltbild"
After:  source="Mein Weltbild", work="Mein Weltbild", source_locator=None
```

#### `_finalize_quote` — Clear Author When It Equals Page Title (Literary Works)
```
Before: author="Human, All Too Human", source="Human, All Too Human"
After:  author="",                      source="Human, All Too Human"
```
The work title is already captured in `source` and `page_title`. Using it as the
author created spurious Author nodes in Neo4j.

#### `_classify_page` — Film/TV Checks Before Person Heuristic
The classification order was restructured so that:

1. **Title-based film/TV patterns** are checked first (unambiguous)
2. Person heuristic runs second
3. Intro/content-based film/TV detection runs after person
4. Literary work detection runs last

```
Before order: person → literary_work → tv_show → film
After order:  film/tv (title) → person → tv_show → film → literary_work
```

#### `_classify_page` — Broader Film/TV Title Patterns
```
Before: \((?:film|movie)\)           → matches "(film)" only
After:  \([^)]*\b(?:film|movie)\b[^)]*\)  → matches "(film)", "(2004 film)",
                                             "(1942 American film)", etc.

Before: \((?:tv|television)\s+series\)          → matches "(TV series)" only
After:  \([^)]*\b(?:tv|television)\s+series\b[^)]*\)  → matches "(1981 TV series)", etc.
```

#### `_apply_header_context` — Structural Labels Not Treated as Speakers
```
Before: "Taglines" header → current_author = "Taglines"
        → all tagline bullets rejected by _looks_like_structural_author

After:  Structural labels (Taglines, Cast, …) skipped in speaker detection
        → tagline bullets attributed to the page title (the film/show name)
```

#### `_emit_pending` — Theme Pages Require Attribution
```
Before: Every bullet quote on theme pages was emitted (anonymous duplicates of
        person-page quotes, no added provenance)

After:  Bullet quotes on theme pages are only emitted if they received at least
        one ** attribution sub-bullet
```

---

## Final Corpus Breakdown

| Page type | Quote count | Notes |
|-----------|-------------|-------|
| `person` | 261,083 | Highest quality — proper author + source citations |
| `theme` | 52,062 | Each quote has at least one attribution sub-bullet |
| `literary_work` | 45,000 | Character quotes with work as source |
| `film` | 5,712 | Taglines only |
| `tv_show` | 160 | Taglines only |
| **Total** | **364,017** | |

| Quote type | Count |
|------------|-------|
| `sourced` | 253,387 |
| `attributed` | 109,596 |
| `about` | 611 |
| `blockquote` | 217 |
| `template` | 206 |

---

## Sample Quality Comparison

### Before
```json
{
  "quote": "What do you mean?",
  "author": "Around the World in 80 Days (2004 film)",
  "source": "Around the World in 80 Days (2004 film)",
  "source_locator": "Around the World in 80 Days (2004 film)",
  "page_type": "person"
}
```

### After
```json
{
  "quote": "The mass of a body is a measure of its energy content.",
  "author": "Albert Einstein",
  "source": "Does the inertia of a body depend upon its energy content?",
  "page_type": "person",
  "quote_type": "sourced"
}
```
