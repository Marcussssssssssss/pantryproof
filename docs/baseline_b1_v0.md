# PantryProof B1 Deterministic Baseline Version 0

Status: provisional comparison baseline for review. Extractor identifier:
`B1-deterministic-v0`.

## Scope and boundary

B1 consumes one Contract V0 `ReceiptSourceEvidence` package. It uses the
package's already recorded `SourceEvidenceGateResult`; it has no gate callback
and does not run `sourceEvidenceSufficient()` again.

- `INSUFFICIENT` returns no `ReceiptOutput` and retains the gate result in a
  `FALLBACK_NO_UPDATE` `PreResolutionDisposition`.
- `SUFFICIENT` allows a deterministic extraction attempt. It does not imply
  extraction correctness. The result contains a pre-review `ReceiptOutput` and
  no automatic `AUTO_RESOLVED`, review, commit, or persistence record.

The result wrapper makes these two branches explicit. B1 does not initialize a
PaddleOCR model; OCR-to-contract adaptation remains the responsibility of the
existing adapter.

## Deterministic rule order

### 1. Generic reading order

Each OCR polygon is reduced to its bounding extent. Regions are sorted by top
coordinate, then left coordinate, then stable token ID. Adjacent regions are
placed on the same visual line only when each region's vertical centre lies
inside the other's vertical extent. Regions within a line are sorted left to
right.

Horizontally overlapping regions on the same line make that line's order
ambiguous. B1 does not map an item row from such a line; an ambiguous first-line
heading, date, or total is represented as unresolved where applicable.

For matching only, surrounding whitespace on each token is removed and tokens
on one visual line are joined with one space. This does not modify the immutable
`OcrSourceToken.original_text` or its raw confidence.

### 2. Store name

The first reading-order line is used only when it contains alphabetic evidence
and is not a supported date/financial anchor or an item pattern. No retailer
dictionary, alias, or spelling correction is used. An overlapping heading is
unresolved; an absent or unsafe heading is missing.

### 3. Purchase date

Only lines beginning with `DATE`, `PURCHASE DATE`, or `TRANSACTION DATE` are
considered. B1 accepts a valid value in one of these forms:

- `YYYY-MM-DD`;
- numeric `DD/MM/YYYY`, `DD-MM-YYYY`, `MM/DD/YYYY`, or `MM-DD-YYYY` when only
  one calendar interpretation is possible;
- `DD MON YYYY` or the corresponding English month name.

A numeric value for which both day-first and month-first interpretations are
valid is unresolved. Invalid dates are not digit-repaired. Multiple anchored
date lines are unresolved, and an unanchored date is not guessed.

### 4. Receipt total

Only exact `TOTAL` or `GRAND TOTAL` anchors followed by one observed amount are
eligible. `SUBTOTAL`, `TAX`, `CHANGE`, `CASH`, `TENDERED`, and `BALANCE` are not
receipt-total candidates or item rows. One eligible total is extracted;
multiple explicit candidates or an unsafe amount association are unresolved.
No item arithmetic is used to calculate, choose, or correct the total.

Before applying the partial-item rule, B1 also excludes a narrow set of generic
financial-summary lines. `DISCOUNT`, `ROUNDING`, `VOUCHER`, `SERVICE CHARGE`,
`SERVICE TAX`, `GST`, `SST`, `PAYMENT TOTAL`, and `AMOUNT PAID`
are excluded only when the complete line consists of that anchored label,
optional `:` or `=`, and one supported amount. This is deliberately a full-line
rule: a longer description such as `DISCOUNT BISCUITS 2.00` remains eligible as
an item rather than being removed by substring matching.

### 5. Item rows

B1 recognizes these conservative, directly observed line forms:

1. `description quantity x unit_price line_total` maps all four item fields.
2. `description line_total` maps the description and line total while recording
   quantity and unit price as missing.
3. A multiplication-style line that contains extra or otherwise unsafe amount
   associations maps only the directly separable description and quantity;
   unit price and line total are unresolved.

Amounts require an observed two-decimal value, optionally prefixed by `RM`,
`MYR`, or `$`. B1 preserves the matched text and does not normalize currency,
quantities, descriptions, or decimal punctuation. It never derives unit price
from quantity and line total, reconstructs an undetected row, normalizes a
product identity, or guesses a grocery category.

## Output status and provenance

Every extracted field references the OCR token or tokens whose character span
supplied its value. Missing fields contain no value. Unresolved fields contain
no selected value and retain relevant token references when available.

Token-level PaddleOCR text, polygons, source order in the evidence package, and
raw recognition confidence remain unchanged. B1 assigns no field confidence:
line-level OCR scores are not treated as calibrated field probabilities.

`ReceiptExtractionStatus` describes structural completeness only:

- `EXTRACTED` requires at least one detected item row and every emitted field to
  be extracted;
- `PARTIAL` means at least one field was extracted but the common schema is not
  structurally complete;
- `FAILED` means no field was extracted.

These states are not accuracy claims and do not authorize inventory updates.

## Isolation and known limitations

B1 has no learned layout model, retailer-specific mapping, external price
reference, OCR correction, candidate ranking, arithmetic correction,
calibration, selective verification, human-review simulation, oracle
substitution, database dependency, or inventory write.

The rules intentionally cover only simple receipt layouts. Multi-column or
overlapping OCR layouts, unanchored dates, unusual item syntax, amounts without
two decimal places, and competing anchors can remain missing or unresolved.
Generic financial-summary filtering removes obvious false-positive item rows
but cannot perfectly distinguish every unusual summary entry from every unusual
purchased product description.

Synthetic tests verify deterministic behavior and contract safety; they do not
measure field accuracy, F1, or improvement. No SROIE data or reference
annotation is used at runtime or in the tests.
