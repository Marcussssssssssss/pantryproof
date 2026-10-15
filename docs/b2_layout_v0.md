# PantryProof B2 Layout Graph Version 0

Status: `PROVISIONAL_IMPLEMENTATION`. Extractor identifier:
`B2-layout-graph-v0`.

This document records the behavior currently implemented in
`pipeline/layout_b2.py`. It is a development specification, not a held-out
evaluation freeze and not an accuracy claim.

## Scope and public boundary

B2 is a deterministic, pure-Python geometry-aware extractor. Its public API is:

```python
extract_b2(source_evidence: ReceiptSourceEvidence) -> B2ExtractionResult
```

The function accepts only the existing Contract V0 source-evidence package. It
does not accept a gate callback, retailer identity, external price evidence,
ground truth, correction candidates, thresholds supplied at runtime, or a
persistence service.

- `INSUFFICIENT` source evidence returns no `ReceiptOutput` and records
  `FALLBACK_NO_UPDATE` in a `PreResolutionDisposition` that retains the same
  recorded gate result.
- `SUFFICIENT` source evidence permits one extraction attempt. It returns a
  pre-review `ReceiptOutput` and no pre-resolution decision, review event,
  correction event, commit, or persistence record.

B2 consumes the recorded gate result; it cannot call
`sourceEvidenceSufficient()` a second time. As with Contract V0, record
validation cannot independently prove how many times an external gate function
executed before the package was constructed.

## Immutable source evidence and layout views

Every usable `OcrSourceToken` is represented internally by an immutable layout
view containing:

- the original token object, identifier, trimmed matching text, and input index;
- axis-aligned polygon extent, width, height, and horizontal/vertical centre;
- extent and centre coordinates normalized to the observed usable-token
  envelope;
- lexical flags for alphabetic text, a complete amount, a complete quantity,
  a multiplier, a supported date, and a generic summary anchor.

The original token text, polygon, raw confidence, token identifier, and source
package are not modified. Trimming and line joining are matching operations
only. B2 does not manufacture OCR tokens or word-level coordinates.

A token is unavailable to layout analysis when its trimmed text is empty, any
polygon coordinate is non-finite, or its axis-aligned extent has non-positive
width or height. The token remains present in the immutable source package but
cannot support an extracted field. With no usable tokens, the internal envelope
and median height use `1.0` fallbacks so extraction fails safely rather than
dividing by zero.

Normalization uses the minimum and maximum observed usable-token coordinates.
Contract V0 has no image dimensions, so the configured header, date, and footer
zones are relative to the observed OCR envelope, not the full source image.

## Provisional constants and boundary semantics

All comparisons use `NUMERIC_TIE_EPSILON = 1e-9` as shown below. Equality is
accepted at minimum and maximum boundaries. Horizontal overlap becomes
ambiguous only when it is strictly greater than its limit plus the epsilon.

| Exported constant | Value | Implemented use and boundary |
|---|---:|---|
| `LINE_MIN_VERTICAL_OVERLAP` | `0.50` | Same-line overlap divided by the smaller height; accepted when `overlap_ratio + epsilon >= 0.50`. |
| `LINE_MAX_CENTER_DISTANCE` | `0.50` | Absolute vertical-centre distance divided by the larger height; accepted when `distance <= 0.50 + epsilon`. |
| `HORIZONTAL_OVERLAP_AMBIGUITY` | `0.10` | Adjacent-cell overlap divided by the smaller width; ambiguous only when `ratio > 0.10 + epsilon`. |
| `HORIZONTAL_ADJACENCY_MAX_GAP_HEIGHTS` | `8.0` | First part of the maximum horizontal gap: `8.0 * median_height`. |
| `HORIZONTAL_ADJACENCY_MAX_GAP_WIDTH_FRACTION` | `0.70` | Second part of the maximum horizontal gap: `0.70 * observed_envelope_width`. |
| `COLUMN_WIDTH_FRACTION` | `0.04` | First part of column tolerance: `0.04 * observed_envelope_width`. |
| `COLUMN_HEIGHT_FACTOR` | `0.75` | Second part of column tolerance: `0.75 * median_height`. |
| `COLUMN_MAX_LINE_STEP` | `3` | Vertical edges and column support span line-index differences from 1 through 3 inclusive. |
| `MIN_COLUMN_SUPPORT_ROWS` | `2` | A column must contain tokens from at least two distinct visual-line indices. |
| `STORE_ZONE_MAX_NORMALIZED_Y` | `0.25` | Store candidate centre must be at or above `0.25 + epsilon`. |
| `STORE_TIE_BAND_HEIGHTS` | `0.50` | Heading candidates within `0.50 * median_height + epsilon` of the top candidate form an unresolved tie. |
| `DATE_ZONE_MAX_NORMALIZED_Y` | `0.50` | Anchored or unanchored date centre must be at or above `0.50 + epsilon`. |
| `TOTAL_ZONE_MIN_NORMALIZED_Y` | `0.50` | A sole total candidate is safe only when `centre_y + epsilon >= 0.50`. |
| `CONTINUATION_MAX_EDGE_GAP_HEIGHTS` | `1.25` | Description continuation edge gap must be at most `1.25 * median_height + epsilon`. |
| `CONTINUATION_LEFT_TOLERANCE_HEIGHTS` | `1.0` | First part of continuation left tolerance: `1.0 * median_height`. |
| `CONTINUATION_LEFT_TOLERANCE_WIDTH_FRACTION` | `0.05` | Second part: `0.05 * observed_envelope_width`. |
| `NUMERIC_TIE_EPSILON` | `1e-9` | Finite comparison allowance; it is not a probability or confidence threshold. |

The derived column tolerance is:

```text
max(0.04 * observed envelope width, 0.75 * median usable-token height)
```

The derived maximum horizontal gap is:

```text
max(8.0 * median usable-token height, 0.70 * observed envelope width)
```

Equality plus the epsilon is accepted. A greater gap between any consecutive
cells makes the complete visual line ambiguous; otherwise the pair receives a
horizontal edge.

The derived continuation left tolerance is:

```text
max(1.0 * median usable-token height, 0.05 * observed envelope width)
```

These values are provisional development constants. They were not selected
from a held-out evaluation partition.

## Visual lines and spatial graph

Usable token views are sorted by vertical centre, top, left, and token ID. A
candidate joins an existing line only when it satisfies both same-line tests
against every current member. This complete-link condition prevents a chain of
individually close boxes from silently merging adjacent purchased rows.

If a token is compatible with more than one existing group, the competing
groups and the token's new singleton group are marked ambiguous. A second pass
compares every token with every completed group and marks all compatible groups
ambiguous when one token can belong to more than one line. This catches tall
regions that could otherwise bridge adjacent rows due to processing order.

Completed groups are sorted by median vertical centre, minimum left edge, then
sorted token IDs. Tokens inside a line are sorted by left edge, horizontal
centre, then token ID. Token IDs stabilize serialization; they do not convert a
substantive layout ambiguity into a selected value.

Within-line text is joined with one space and character spans map each joined
segment back to its source token. Consecutive cells whose horizontal overlap is
strictly above the configured ratio, or whose horizontal gap is strictly above
the derived maximum, make the line ambiguous.

The internal graph records:

- horizontal edges between consecutive same-line cells within the configured
  maximum of the median-height-scaled and envelope-width-scaled gaps;
- vertical edges between cells on later lines up to three line indices away
  when either right edges or horizontal centres are within column tolerance.

These edges make the spatial relationships explicit. V0 requires horizontal
edges between consecutive split description boxes and requires vertical edges
when forming repeated numeric columns. The graph remains internal and is not
added to Contract V0 output.

## Repeated numeric columns

The column model uses non-reserved, non-ambiguous item-like lines. Full-token
amounts and full-token quantities are clustered separately by right edge.

For a token to join a column candidate:

1. its right edge must be within column tolerance of every current member; and
2. at least one current member must be on a different line no more than three
   visual-line indices away and connected by a recorded vertical edge.

Exactly one eligible group permits attachment. Zero eligible groups starts a
new candidate. Multiple eligible groups also start a new candidate instead of
using token-ID order to choose between substantive alternatives. A retained
column requires at least two distinct supporting line indices. Column
representatives are median right edges and are ordered left to right.

## Receipt-level roles

### Store name

A store candidate must be a non-ambiguous alphabetic line whose normalized
centre is in the top quarter. Generic control lines, column headers, and
item-like lines are excluded. Exact generic footer text and any line containing
a token flagged as a supported date or generic summary anchor are also
excluded. The geometrically top candidate is selected.
When more than one candidate lies in the configured top tie band, the store
field is `UNRESOLVED` and references all tied lines. With no safe candidate it
is `MISSING`.

### Purchase date

Anchors are `DATE`, `PURCHASE DATE`, and `TRANSACTION DATE`. More than one
anchored line is `UNRESOLVED`. A sole anchored line is unresolved if its layout
is ambiguous or its centre lies below the upper-half date zone.

When no anchor exists, B2 considers non-ambiguous complete date lines in the
upper half. None is `MISSING`, more than one is `UNRESOLVED`, and one is
validated without correction. Supported forms are:

- `YYYY-MM-DD`;
- numeric day/month or month/day with `/` or `-` and a four-digit year, only
  when the calendar interpretation is unique;
- day followed by an English month name or abbreviation and a four-digit year.

A numeric value valid under two different day/month interpretations is
`UNRESOLVED`. Invalid calendar values are not repaired.

### Receipt total

Any line beginning with `TOTAL` or `GRAND TOTAL` is an explicit candidate.
Multiple such lines are `UNRESOLVED` and all are reserved from item parsing. A
sole candidate is extracted only when it contains exactly one supported amount,
has non-ambiguous layout, and lies in the lower-half footer zone. Otherwise it
is `UNRESOLVED`. Item arithmetic is never used to calculate or select a total.

## Item role assignment

Reserved receipt-field lines, ambiguous lines, generic control lines, and
generic column-header lines are excluded before item decoding. Item rows are
decoded in this order:

1. A joined line matching
   `description quantity x unit_price line_total` extracts all four directly
   observed fields. This supports one whole-line OCR region or separate boxes.
2. A multiplication-style line with an amount-bearing but otherwise unsafe
   body extracts the separable description and quantity; unit price and line
   total are `UNRESOLVED` and reference the competing body evidence.
3. A single whole-line OCR region matching
   `description quantity first_amount second_amount` without a multiplier
   extracts only the separable description. The quantity-shaped value and both
   amount roles are `UNRESOLVED` with source references because the region has
   neither multiplier evidence nor word-level column geometry.
4. When one or more OCR boxes are complete amounts, alphabetic boxes strictly
   left of the first numeric or multiplier box form the description. An
   alphabetic non-multiplier box at or to the right of that boundary rejects the
   candidate, which avoids collapsing obvious side-by-side text into one row.
   Every consecutive split description box must also have a horizontal edge.
5. A whole OCR region containing exactly one supported amount may map
   `description line_total`; quantity and unit price are `MISSING`.
6. A whole OCR region containing multiple amounts but no safe four-field match
   retains the text before the first amount as description, records quantity as
   `MISSING`, and records unit price and line total as `UNRESOLVED` with the
   amount-bearing token references.

For split-box geometry, quantity handling is:

- no quantity box: `MISSING`;
- more than one quantity box: `UNRESOLVED`;
- one quantity box: extracted only when there is exactly one stable quantity
  column, that column is strictly left of the first amount column when amount
  columns exist, and the box belongs uniquely to it; otherwise `UNRESOLVED`.
  Equality, including the epsilon allowance, is not treated as safely left.

Amount handling is:

- one amount and no stable amount column: unit price `MISSING`, line total
  extracted;
- one amount and one stable column with unique membership: unit price
  `MISSING`, line total extracted;
- one amount and exactly two stable columns: membership in the left column
  extracts unit price and leaves line total `MISSING`; membership in the right
  column leaves unit price `MISSING` and extracts line total;
- two amounts and exactly two stable columns: unit price and line total are
  extracted only for unique left-column/right-column membership in horizontal
  order;
- all other amount/column combinations leave both roles `UNRESOLVED`.

Amounts require two decimal places and may contain comma thousands separators
or an observed `RM`, `MYR`, or `$` prefix. B2 preserves the matched text. It
does not calculate unit price, line total, or receipt total from other values.

## Controlled description continuation

A non-row line can be a continuation only when it is non-ambiguous, contains
alphabetic evidence, contains no full-token amount, quantity, or multiplier,
contains no amount substring, is not a control or column header, is not a
supported date or summary anchor, lies strictly below the configured store
zone, and is not one of the exact generic footer phrases `THANK YOU`, `PLEASE
COME AGAIN`, or `RECEIPT COPY` with optional terminal punctuation.

The candidate and item row must have adjacent visual-line indices, and the
candidate must satisfy the edge-gap and left-alignment tolerances. It is
attached only when that description line is eligible for exactly one row and
that row is eligible for exactly one description line. When one description can
attach to several rows, or one row can receive several descriptions, every
affected row's description becomes `UNRESOLVED` and references the original
description plus its competing continuation tokens. No closest-by-token-ID or
closest-by-small-margin choice is made. A unique attachment joins text and token
references in vertical reading order. An unattached description line does not
create an item row.

## Missingness, ambiguity, and provenance

- `EXTRACTED` requires a directly observed value and its source token IDs.
- `MISSING` means no supported observed candidate was assigned and carries no
  value or confidence.
- `UNRESOLVED` means relevant evidence exists but its layout, interpretation,
  or role cannot be selected safely; competing token IDs are retained where
  available.

Receipt fields use `receipt_id:b2:*` IDs. Item rows use deterministic six-digit
reading-order IDs such as `receipt_id:b2:row:000000`, and item field IDs extend
the row ID. Every field confidence is `None`; raw OCR confidence is neither
calibrated nor promoted to a field probability.

`ReceiptExtractionStatus` reports structural completeness only. It is
`FAILED` when no field is extracted, `EXTRACTED` only when at least one item row
exists and every emitted field is extracted, and `PARTIAL` otherwise. It is not
an accuracy or persistence decision.

## Isolation and exclusions

B2 has no learned model, training phase, retailer-specific matching, Malaysian
price reference, OCR spelling correction, product normalization, correction
candidate generation or ranking, arithmetic correction, calibration, selective
verification, simulated user confirmation, oracle substitution, Flutter code,
SQLite dependency, inventory write, or persistence transition.

It does not initialize PaddleOCR. OCR adaptation and one-time gate recording
remain separate upstream responsibilities.

## Supported scope and known limitations

V0 supports ordinary single-block receipts with:

- whole-line `description quantity x unit_price line_total` regions;
- split-token multiplier rows;
- repeated split-token quantity, unit-price, and line-total columns;
- two-column description/amount rows;
- missing quantity or price roles represented explicitly;
- one uniquely associated description continuation.

Known limitations include:

- axis-aligned extents can be unreliable under extreme skew or rotation;
- observed-envelope zones can shift when OCR omits borders or includes outliers;
- whole-line OCR regions do not expose internal word geometry, so competing
  amounts can remain unresolved;
- complex side-by-side blocks, more than two stable amount columns, sparse
  columns, large inter-row gaps, and tall boxes spanning adjacent rows can be
  rejected or left unresolved;
- the three-line column-neighbour limit may prevent support across intervening
  non-item lines;
- generic financial-summary and footer filters cannot identify every unusual
  receipt convention or distinguish every unusual product name;
- ignored invalid-geometry tokens may cause missing fields rather than an
  extraction exception.

Synthetic tests can establish deterministic contract behavior and spatial
functionality; they cannot establish extraction accuracy, F1, superiority over
B1, or equivalent Android behavior.

## Shared reuse and change control

B3, PT1, and PT2 must consume this same B2 implementation and configuration,
not forked copies or configuration-specific variants. A final experimental
freeze should record the repository commit, implementation hash, manifest hash,
OCR configuration, development-data provenance, and conformance fixtures before
any held-out evaluation.

Any change to a numeric constant, comparison boundary, regex, field-role
precedence, ambiguity rule, source-reference rule, or grouping behavior changes
extractor semantics. Such a change requires review, a new extractor version or
explicit compatible revision, an updated manifest, and rerun synthetic tests.
This provisional implementation is not `HELD_OUT_EVALUATION_FROZEN`.
