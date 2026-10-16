# PantryProof B3 Generic-Rule Baseline Version 0

Status: `PROVISIONAL_IMPLEMENTATION`. Algorithm and ruleset identifier:
`B3-generic-rules-v0`. This implementation is not frozen for held-out
evaluation and makes no accuracy or calibration claim.

## Scope and public boundary

B3 is a deterministic downstream transformation of the existing
`B2-layout-graph-v0` automatic result. Its public API is:

```python
apply_b3(b2_result: B2ExtractionResult) -> B3Result
```

`apply_b3` accepts no OCR engine, source-gate callback, retailer identity,
external price reference, ground truth, review decision, model, or persistence
service. It does not call `extract_b2`. On the sufficient-source branch it
requires the incoming `ReceiptOutput.extractor_version` to be exactly
`B2-layout-graph-v0`.

`B3Result` retains the exact original `B2ExtractionResult` and, when B2
produced structured output, a distinct `ReceiptOutput` whose extractor version
is `B3-generic-rules-v0`. The wrapper also retains ordered field
relationships, rule events, proposed source-supported candidates, arithmetic
diagnostics, adjustment evidence, and other diagnostics. Convenience
properties expose the original B2 result, transformed output, and original
pre-resolution disposition without creating new policy state.

If B2 returned no structured output because its recorded gate result was
`INSUFFICIENT`, B3 returns no structured output and preserves the same
`FALLBACK_NO_UPDATE` disposition. No downstream rules run. B3 neither invokes
nor attempts to prove another source-gate execution.

A sufficient B2 output remains in the automatic population even when its
structural status is `PARTIAL` or `FAILED`. B3 does not create
`REVIEW_REQUIRED`, user/oracle substitution, selective verification, or
abstention.

## Immutable original and transformed relationships

B3 never mutates its frozen input. For every B2 field, the result contains one
ordered `B3FieldTransformation` linking the exact original `StructuredField`
object to the corresponding B3 field object. The same immutable object may be
reused when its value is unchanged. The transformed receipt preserves:

- receipt ID and the exact `ReceiptSourceEvidence` object;
- receipt field IDs;
- item row IDs and order;
- field order and field status;
- item-row association;
- source-token IDs and their order;
- confidence and unresolved-reason semantics;
- pantry-product identity; and
- B2 `ReceiptExtractionStatus`.

The transformed output remains `PRE_REVIEW_AUTOMATIC`. B3 adds or deletes no
item row and does not turn a B2 `MISSING` or `UNRESOLVED` field into an
extracted field. A normalized item description remains receipt-description
text; it is not a pantry-normalized product identity.

`SourceSlice` records half-open offsets into an **original** OCR token together
with the literal text. Unicode-normalized offsets are never presented as
source offsets. Rule events are assigned contiguous sequence numbers in the
implemented phase order. Repeated execution on an equal input produces equal
records and ordering.

## Frozen rule order

For the sufficient branch, B3 executes these stages in order:

1. Validate the result type, exact B2 extractor identifier, and source branch.
2. Normalize the extracted store followed by item descriptions in B2 row
   order.
3. Parse and normalize the extracted purchase date.
4. Parse and normalize extracted item quantities in B2 row order.
5. Parse and normalize each item's unit price and line total in B2 row order,
   followed by the receipt total, without changing field status.
6. Scan immutable source tokens for complete single-token generic adjustments.
7. Compute pre-correction item and observed-row receipt arithmetic diagnostics.
8. In B2 item order, discover then conditionally apply candidates for each
   item; rebuild the interim output, recheck observed-row receipt arithmetic,
   then discover and conditionally apply a receipt-total candidate.
9. Recompute final arithmetic diagnostics from the resulting B3 values.
10. Build ordered field relationships and validate every source slice and
    diagnostic source reference.

Arithmetic expectations do not themselves become candidates. Candidate
ordering, token ID, lexical order, and smallest residual never resolve a
substantive tie.

## Text normalization

`normalize_receipt_text` applies the following pure representation rules:

1. Unicode NFKC normalization.
2. Locale-independent Unicode `casefold()`.
3. The fixed punctuation substitutions below.
4. Collapse all Unicode whitespace runs to one ASCII space and trim both ends.

| Observed characters | Replacement |
|---|---|
| `‘ ’ ‚ ‛` | ASCII apostrophe (`'`) |
| `“ ” „ ‟` | ASCII quotation mark (`"`) |
| `‐ ‑ ‒ – — −` | ASCII hyphen-minus (`-`) |
| `…` | three ASCII periods (`...`) |

This is a substitution map, not an unrestricted deletion list. Internal
punctuation is retained. B3 performs no abbreviation expansion, spell
correction, retailer matching, or semantic product-identity inference.

Text normalization applies only to extracted `STORE_NAME` and
`ITEM_DESCRIPTION` values. The original B2 values and original OCR token text
remain unchanged in the wrapper and source package.

## Date and quantity parsing

`parse_generic_date` performs complete-string matching after NFKC and outer
whitespace trimming. Supported forms are:

- year first: `YYYY-M-D` or `YYYY-MM-DD`, using hyphens;
- numeric day/month or month/day using the same `/` or `-` separator twice;
- day, English month name or abbreviation, and four-digit year; and
- English month name or abbreviation, day with optional comma, and four-digit
  year.

Every candidate is calendar-validated. For a numeric day/month-or-month/day
value, both interpretations are tested. Neither valid is `INVALID`; exactly
one valid is normalized to ISO; two valid interpretations yielding the same
date are valid; and two different valid dates are `AMBIGUOUS`. B3 uses no
current date, locale, retailer, or ground truth. An invalid or ambiguous value
is retained and receives a diagnostic rather than being guessed.

`parse_positive_quantity` accepts a complete positive Decimal with optional
valid comma thousands grouping and an optional dot fractional part. Signs,
exponents, zero, negative values, mixed separators, and embedded units are not
accepted. Successful quantities are emitted as a plain Decimal string with no
scientific notation or unnecessary trailing zeroes. Missing quantities are
not defaulted.

## Monetary representation

`parse_money` uses exact `Decimal` parsing after NFKC and trimming. The active
V0 grammar accepts:

- an optional `RM`, `MYR`, or `$` prefix;
- an ungrouped integer part, or comma groups of exactly three digits;
- a dot decimal separator; and
- one or two fractional digits.

One fractional digit is padded to two; two digits are retained. A parsed value
is quantized to the frozen currency quantum and represented with exactly two
decimal places. Decimal-comma input, signs in ordinary monetary fields,
malformed or mixed grouping, exponent notation, `NaN`, and infinity are
unsupported. `$` remains a distinct marker and is not interpreted as
Malaysian ringgit. `RM` and `MYR` are preserved as source marker categories;
B3 performs no currency conversion.

A representation change retains the original field ID and source references
and records the original and resulting values in an ordered rule event.

## Decimal arithmetic policy

The frozen provisional constants are:

```text
CURRENCY_QUANTUM   = Decimal("0.01")
CURRENCY_TOLERANCE = Decimal("0.01")
ROUNDING_MODE      = ROUND_HALF_UP
```

All Decimal operations use an operation-local context whose precision is
derived from the accepted operands. The process-global Decimal context is not
an input to B3, so its default 28-digit precision cannot silently round or
reject a grammar-valid large literal. Currency quantization alone performs the
declared `ROUND_HALF_UP` rounding.

Binary floating-point arithmetic is not used. For an item with usable
quantity, unit price, and line total, B3 computes:

```text
raw expected       = quantity * unit price
rounded expected   = raw expected quantized to 0.01 with ROUND_HALF_UP
absolute difference = abs(observed line total - rounded expected)
```

Diagnostics distinguish:

- `RAW_EXACT_MATCH`;
- `MATCH_AFTER_CURRENCY_ROUNDING`;
- `WITHIN_INCLUSIVE_TOLERANCE` when the difference is at most `0.01`;
- `MISMATCH_BEYOND_TOLERANCE`;
- `INCOMPLETE_OPERANDS`;
- `AMBIGUOUS_OR_CONFLICTING_UNITS`;
- `CONFLICTING_CURRENCY_MARKERS`; and
- `EXPLICIT_PROMOTION_OR_ADJUSTMENT_EXCEPTION`.

An exact match takes precedence over rounded match, which takes precedence over
the inclusive tolerance. The one-cent tolerance is a consistency boundary,
not a confidence threshold, and never authorizes candidate application. A
separately and directly supported candidate must make the relation raw-exact
or exact after the declared currency rounding.

Receipt-level arithmetic compares the parseable line-total values for the
**observed B2 item rows at the relevant phase** with that phase's parsed
receipt total. PRE_CORRECTION uses normalized pre-semantic-correction values;
FINAL uses the resulting B3 values. It is explicitly an
`OBSERVED_RECEIPT_ROWS` check, not proof that OCR or B2 detected every purchase
line. Missing or unresolved item totals produce an incomplete result rather
than disappearing from the population. Pre-correction and final phases are
recorded separately so a representation or supported correction cannot hide
its effect on diagnostics.

The same quantum, rounding mode, and tolerance must be used by the compatible
upstream PantryProof generic-rule path before comparative evaluation.

## Weighted goods

The only active unit vocabulary is:

```text
kg, g, lb, lbs, oz
```

Matching is case-insensitive and requires explicit immutable source evidence.
A usable weighted relation requires both an explicit positive quantity/unit
pair and a compatible unit-price denominator in the relevant source boundary.
The explicit source quantity must also equal the structured B2 quantity. When
both kinds of weighted evidence are absent, B3 performs ordinary item
arithmetic without inferring a unit. Partial, conflicting, or multiple unit
evidence produces a diagnostic and suppresses forced arithmetic equality. B3 infers no unit,
quantity, denominator, or conversion and performs no `g`/`kg`, `oz`/`lb`, or
other cross-unit conversion. It never fabricates a weighted item row.

The association boundary is frozen as each item field's ordered public
`source_token_ids`: B3 scans each referenced token and a whitespace-joined
view inside that same field boundary. It never joins across field roles or
relies on the input order of `ReceiptSourceEvidence.tokens`. Exactly one
distinct source quantity/unit pair and one distinct rate-amount/denominator
pair must remain. `lb` and `lbs` are equivalent only for this comparison. The
source quantity must equal the structured quantity, the observed rate amount
must equal the structured unit price, units must agree, and explicit approved
currency groups must be compatible. Grouped positive quantities use the same
grammar as the quantity parser. Unknown currency context such as `EUR
10.00/kg` is not stripped to an unprefixed usable rate.

## Adjustments and promotions

B3 recognizes only complete, single-token adjustment lines. It performs no
new split-token grouping and does not access B2's private layout graph. Active
anchored labels are:

```text
DISCOUNT, VOUCHER, COUPON, REBATE,
TAX, GST, SST, SERVICE TAX, SERVICE CHARGE, SURCHARGE,
SUBTOTAL, ROUNDING
```

Negative labels (`DISCOUNT`, `VOUCHER`, `COUPON`, and `REBATE`) are recorded as
subtractions when unsigned or explicitly negative; an explicit positive sign
is a direction conflict. Tax and charge labels are additions when unsigned or
explicitly positive; an explicit negative sign is a direction conflict.
`SUBTOTAL` is reference-only. `ROUNDING` requires an explicit `+` or `-`; an
unsigned value has unknown direction. Every record retains label, normalized
amount, currency marker, direction, exact source slice, representation status,
and ambiguity reason where applicable.

Adjustment evidence that is already represented by a structured B2 field is
marked so it is not counted twice. Contract V0 has no adjustment-scope field,
so every observed adjustment records scope ambiguity; a direction conflict is
recorded in the same diagnostic. V0 does not numerically add or subtract an
adjustment. Unrepresented non-reference adjustment evidence instead qualifies
a receipt-sum mismatch and vetoes a receipt-total correction. `SUBTOTAL`
remains reference-only: it does not itself explain a total mismatch. An
unrepresented subtotal conservatively vetoes receipt-total correction. Product
descriptions merely containing an adjustment word do not match the complete
anchored grammar. A token already assigned by B2 to `ITEM_DESCRIPTION` is
excluded even when its complete text superficially resembles an adjustment;
B3 does not relabel a product description as a financial line.

`already_represented` is true only when the adjustment token is referenced by
a monetary equation field whose parsed value equals the adjustment amount.
Store, date, description, or unrelated field membership is not evidence that
the amount was counted. Explicit adjustment currencies also participate in
the receipt-level currency-conflict check: conflicting adjustment groups, or
an adjustment group conflicting with an explicit equation group, cannot
explain a mismatch.

Generic whole-word promotion indicators include `PROMO`, `PROMOTION`,
`SPECIAL OFFER`, `OFFER`, and `BUY n GET n`. Promotion evidence may explain or
suppress an **item** mismatch beyond tolerance, but never authorizes rewriting
a promotional price to force equality. The scan is limited to tokens already
referenced by that B2 item row; receipt-level promotion handling is disabled.

## Candidate generation and application

B3 keeps five concepts separate:

1. representation normalization;
2. unambiguous parsing;
3. arithmetic diagnostics;
4. correction candidate proposal; and
5. actual application.

A non-representation monetary candidate must be a complete amount directly
present in immutable original OCR text, with exact token and character-span
provenance. Its support must stay inside the target field's existing B2
source-token boundary. Identical values are deduplicated while all supporting
slices are retained. Proposed candidates remain in `B3Result.candidates` even
when later rejected, so candidate generation and final selection are auditable.
The result validates uniqueness by target field and value, target-boundary
membership, and every literal source slice.

A candidate can be applied only when exactly one distinct value remains, its
field role is unambiguous, and arithmetic corroborates it as raw exact or exact
after currency rounding. Item candidates are additionally vetoed by relevant
promotion, adjustment, weighted-unit, currency, or incomplete-operand
exceptions. Receipt-total candidates are vetoed by incomplete
observed rows, unrepresented adjustments, currency conflict, or ambiguous
source support. Item correction considers unit price and line total only;
quantity is never corrected. A shared token containing
several monetary values is not proof of a unique field alternative. Competing
alternatives remain diagnostic; token ID, lexical order, and smallest residual
are not semantic tie-breakers.

For V0, the amount match must occupy its OCR token apart from surrounding
whitespace. This rejects numeric substrings inside labels, unsupported
currencies, signs, parentheses, percentages, or other enclosing context. A
separate approved `RM`, `MYR`, or `$` marker inside the same target boundary
is retained as an additional exact source slice; an unsupported
three-letter/symbol marker vetoes the candidate. Any source token shared with
another item or receipt monetary field is excluded as role-ambiguous, even if
it contains only one value. Shared or multi-value tokens are excluded as
support; another independent, unambiguous target token may still support a
candidate. Result construction revalidates that every money slice
canonicalizes to the recorded candidate value and that all marker/value
slices match the original token text.

When existing B2 evidence cannot establish a role-bound alternative, the
computed expected value is recorded but the automatic field is unchanged.
Arithmetic alone never invents a replacement.

In ordinary current `extract_b2` output, a dedicated monetary token normally
already supplies the same literal stored in the B2 field; whole-line evidence
is usually shared or multi-valued and is rejected. Consequently, semantic
candidate application is expected to be rare and was exercised defensively
with Contract-valid synthetic wrappers whose structured value disagrees with
another literal inside its existing source boundary. The parser and
diagnostic paths are fully active, but V0 does not claim that current
production B2 fixtures expose routine safe semantic corrections.

## Diagnostic and evaluation semantics

General diagnostics distinguish invalid or ambiguous parsing, observed or
scope-ambiguous adjustments, incomplete or conflicting weight evidence,
missing direct correction support, shared-token ambiguity, competing
candidates, and an actually applied supported correction. Arithmetic
diagnostics use the separate outcomes listed above.

Diagnostics are audit evidence, not probabilities, calibration, review
requests, or exclusion decisions. Every sufficient B2 receipt—including a
structurally failed, partial, ambiguous, or difficult receipt—retains a B3
automatic output and remains in the evaluation population.

## Explicit exclusions

B3 V0 has no learned model, training, retailer-specific vocabulary, Malaysian
retailer price database, external candidate price, pantry-semantic identity
guess, correction ranker, confidence calibration, selective verification,
human/user substitution, oracle substitution, inventory persistence, Flutter
code, SQLite dependency, hidden B2 graph access, alternate extractor, or
ground-truth input. It does not initialize PaddleOCR.

SROIE held-out test data, Tier A held-out receipts, and adjudicated labels are
not runtime inputs and must not be used to tune these rules. Synthetic tests
establish deterministic behavior only; they do not establish extraction
accuracy, correction accuracy, F1, or superiority over B1, B2, or PantryProof.

## Change control and known limitations

Before held-out evaluation, the implementation, manifest, reused B2 version,
rule order, grammars, punctuation map, units, adjustment semantics, Decimal
settings, test fixtures, development-data provenance, and relevant hashes must
be reviewed and frozen. A semantic change requires a reviewed version update,
manifest update, and rerun of the complete synthetic suite.

Known limitations include:

- B2 exposes token-level field references but no field-role character spans;
- one OCR token may be shared by several fields, sharply limiting safe
  non-representation correction;
- semantic corrections are generally unreachable on ordinary current B2
  outputs unless a distinct, role-bound alternative literal survives;
- candidate substrings inside label-bearing tokens are conservatively disabled;
- split-token financial adjustments are deliberately unsupported;
- promotion and adjustment scope can remain unknown;
- B3 does not repair B2 missing/unresolved values or undetected item rows;
- the weighted grammar performs no unit conversion;
- the monetary grammar is dot-decimal and two-decimal-output only;
- observed-row receipt arithmetic cannot prove receipt completeness; and
- Unicode NFKC/casefold is a representation policy, not product-identity
  normalization.

Relative to the moderated thesis Table 4.10 intent, V0 implements the shared
generic normalization, parsing, Decimal consistency, explicit weighted-unit,
promotion/adjustment, and conservative evidence-backed correction families.
It deliberately leaves retailer knowledge, external price references,
decimal-comma and cross-unit conversion, split-token adjustment grouping,
inferred missing values/rows, learned ranking, calibration, selective
verification, and user/oracle substitution disabled. Those differences are
explicit comparator boundaries, not evidence that the corresponding thesis
families were evaluated or found ineffective.

The manifest remains `PROVISIONAL_IMPLEMENTATION` with
`held_out_evaluation_frozen: false` until formal review and freeze evidence are
recorded.
