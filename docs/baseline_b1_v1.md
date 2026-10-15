# PantryProof B1 Deterministic Baseline Version 1

Status: **PROVISIONAL_IMPLEMENTATION**. Extractor identifier:
`B1-deterministic-v1`. This revision is not frozen for held-out evaluation.

## Scope and source gate

B1 consumes one Contract V0 `ReceiptSourceEvidence` package and the package's
already recorded `SourceEvidenceGateResult`. It accepts no gate callback.

- `INSUFFICIENT` returns no `ReceiptOutput` and a `FALLBACK_NO_UPDATE`
  disposition retaining the recorded gate result.
- `SUFFICIENT` permits a deterministic, pre-review extraction attempt. It is
  not a correctness claim and creates no resolution, review, persistence, or
  inventory event.

The source package, OCR text, token polygons, token IDs, source order, and raw
OCR confidences are immutable. Extracted fields retain source token IDs. B1
does not promote OCR confidence to field confidence.

## Frozen geometry and reading order

The three public constants are:

- `B1_STORE_HEADER_MAX_NORMALIZED_Y = 0.25`
- `B1_LINE_CLUSTER_TOLERANCE_HEIGHTS = 0.50`
- `B1_GEOMETRY_EPSILON = 1e-9`

Every usable polygon is reduced to an axis-aligned extent. Empty text,
non-finite geometry, and width or height no greater than the epsilon are not
used for extraction; the original source token is still preserved.

The normalization envelope is the minimum top to maximum bottom of usable OCR
tokens. A line's normalized vertical centre is
`(line_center_y - envelope_top) / envelope_height`. This is observed-token
envelope normalization, not full-image normalization, because Contract V0 has
no image dimensions.

Tokens are considered compatible with a fixed line anchor when both:

1. `vertical_overlap / min(token_heights) + 1e-9 >= 0.50`; and
2. `absolute_vertical_centroid_gap / min(token_heights) <= 0.50 + 1e-9`.

Tokens are visited by vertical centroid, horizontal centre, then token ID. A
group retains its first token as its fixed anchor; this is intentionally not a
complete-link algorithm. Compatibility with multiple anchors marks all
affected groups ambiguous. A postcheck detects bridge tokens. Visual lines are
ordered by anchor centroid, anchor left edge, then anchor token ID. Regions
within a safe line are ordered by left edge, horizontal centre, then token ID.
Substantive horizontal overlap is unsafe except that separate complete monetary
regions may proceed to the explicit equal-position money tie rule.

## Frozen literal grammars

Amounts are two-decimal values with optional `RM`, `MYR`, or `$` prefix:
`(?:RM\s*|MYR\s*|\$\s*)?\d+(?:,\d{3})*\.\d{2}`. Multiple amounts in a
declared row must be whitespace-separated. Quantities are `\d+(?:\.\d+)?`.

### Store name

B1 searches safe visual lines whose normalized centre is at most `0.25 +
1e-9`. It chooses the earliest alphabetic line after excluding complete dates,
generic controls, exact financial-summary forms, and supported item grammars.
It uses no retailer dictionary, logo detection, or prominence score. No
eligible line is `MISSING`; ambiguity affecting the earliest eligible heading
is `UNRESOLVED` with available references.

### Purchase date

Candidates are either anchored by `DATE`, `PURCHASE DATE`, or `TRANSACTION
DATE`, or are complete standalone supported date lines. Candidates already
classified as item rows are excluded. Supported complete values are:

- year-first hyphen form `YYYY-M-D`, with one- or two-digit month and day
  (`YYYY-MM-DD` is therefore also accepted);
- numeric day/month or month/day forms using `/` or `-`, provided the same
  separator is used twice;
- `DD MON YYYY` or an English month-name equivalent.

For a numeric day/month-or-month/day value, B1 validates both calendar
interpretations. Neither valid is `INVALID`; exactly one valid is selected; two
valid interpretations that produce the same calendar date are valid; and two
valid interpretations that produce different dates are `AMBIGUOUS`. Thus
`11/11/2026` is valid while `10/11/2026` remains ambiguous. Mixed separators,
such as `13-10/2026`, are unsupported and are not repaired.

Selection is deterministic: no candidate is `MISSING`; any observed invalid,
calendar-ambiguous, or layout-ambiguous candidate is `UNRESOLVED`; conflicting
valid canonical dates are `UNRESOLVED`; equivalent valid duplicates select the
earliest candidate in frozen reading order. Dates are validated with the
calendar and normalized to zero-padded ISO `YYYY-MM-DD`. B1 performs no OCR
repair and does not use system time.

### Item rows

The declared full-line forms, evaluated in this order, are:

1. `description quantity x|× amount [amount ...]`;
2. `description QTY|QUANTITY [:|=] quantity amount [amount ...]`;
3. `description quantity amount [amount ...]`, where the numeric slot appears
   immediately before the amount sequence and description ends in nonnumeric
   evidence;
4. `description amount [amount ...]`.

Descriptions must contain alphabetic evidence and remain directly observed.
The quantity is extracted only in forms 1–3; form 4 records it `MISSING`. No
default quantity is invented.

For separate OCR regions, the unique greatest right edge identifies
`LINE_TOTAL`. Monetary regions tied at that position are `UNRESOLVED` and
retain competing references. When a single whole-line OCR token contains all
amounts and therefore has no word geometry, the last textual amount is the
rightmost amount. The remaining amount is `UNIT_PRICE` only under a quantity
grammar and only when exactly one remains. Otherwise unit price is `MISSING` or
`UNRESOLVED`; it is never derived arithmetically. Undetected rows are not
reconstructed.

Generic controls begin with `DATE`, `PURCHASE DATE`, `TRANSACTION DATE`,
`GRAND TOTAL`, `TOTAL`, `SUB TOTAL`, `TAX`, `CHANGE`, `CASH`, `TENDERED`, or
`BALANCE`. Exact label-plus-optional-amount financial summaries are
`DISCOUNT`, `ROUNDING`, `VOUCHER`, `SERVICE CHARGE`, `GST`, `SST`, `SERVICE
TAX`, `PAYMENT TOTAL`, and `AMOUNT PAID`. These anchored complete-line rules do
not reject longer product descriptions containing the same words.

### Receipt total

Only beginning-of-line `TOTAL` and `GRAND TOTAL` anchors are eligible;
`SUBTOTAL` is not. A valid anchored line contains one or more supported amounts
and no other body text. Its unique rightmost amount is the candidate, using the
same separate-region and whole-region tie rules as item rows.

B1 evaluates anchors in stable reading order and selects the last valid safe
candidate. A malformed earlier or later anchor does not override it. An unsafe
valid association at or after the last safe candidate makes the result
`UNRESOLVED`. If anchors were observed but no safe valid association exists,
the result is `UNRESOLVED`; if no approved anchor exists, it is `MISSING`. Item
arithmetic is never used.

## Output semantics and exclusions

All seven shared field types remain represented: store, date, item description,
quantity, unit price, line total, and receipt total. `MISSING` means no
supported evidence was assigned. `UNRESOLVED` means relevant evidence exists
but cannot be selected safely; available competing references are retained.
`ReceiptExtractionStatus` measures structural completeness only, not accuracy.

Training is `NOT_APPLICABLE`. B1 has no learned parameters, B2 prediction or
layout-graph dependency, retailer resource, external price input, ground-truth
input, OCR correction, candidate scoring, calibration, selective verification,
human-review simulation, oracle output, Flutter, SQLite, or inventory write.
No SROIE held-out test data or Tier A held-out receipt is used by these rules or
synthetic tests.

## Change control and limitations

Before held-out evaluation, the implementation, manifest, constants, grammars,
tie rules, development-data provenance, and relevant hashes must be reviewed
and frozen. Any semantic change requires a reviewed version/manifest update and
the complete synthetic suite. `held_out_evaluation_frozen` remains false.

Known limitations include observed-envelope rather than image normalization,
axis-aligned geometry, no internal word boxes for whole-line OCR, conservative
ambiguity propagation, narrow literal receipt grammars, no multi-column model,
and imperfect generic distinction between unusual products and financial
summary lines. Synthetic conformance does not establish accuracy, F1, or
superiority over another baseline.
