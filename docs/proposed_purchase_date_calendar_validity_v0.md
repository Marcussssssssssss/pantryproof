# PURCHASE_DATE_CALENDAR_VALIDITY_V0

Status: `PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`

Implementation acceptance: `PENDING_INDEPENDENT_TECHNICAL_REVIEW`

## 1. Scope

`pipeline/proposed/purchase_date_calendar_validity.py` implements the bounded,
synthetic-only purchase-date calendar-validity rule approved in
`docs/proposed_method_decision_log.md`.

The module evaluates one exact retained D3 `PURCHASE_DATE` candidate and returns
one existing `ConstraintRuleOutcomeV2`. It does not aggregate rule outcomes,
select a candidate, change permanent B2 `c0`, build features, score, calibrate,
route review, persist inventory or access evaluation data.

The implementation is traced to:

- `G2A-LNG-01` through `G2A-LNG-06`;
- Tai B3 compatibility decisions Q1 through Q6; and
- joint `G2A-SHARED-01` structural evidence-reference semantics.

These decisions do not approve broader HC-D06/HC-D07 methodology, controller
behavior, shared-contract migration or held-out execution.

## 2. Public boundary

The public evaluator is:

```python
evaluate_purchase_date_calendar_validity_v0(
    *,
    rule_outcome_id: str,
    operand_audit: HardConstraintOperandAuditResultV0,
    candidate_audit: CandidateOperandAuditV0,
    rule_profile_reference: HardConstraintProfileRefV2,
    grammar_reference: str,
    candidate_evidence_reference: EvidenceReferenceV2,
) -> ConstraintRuleOutcomeV2
```

`recognizes_purchase_date_grammar_v0(value: str) -> bool` is the separately
versioned syntax-recognition boundary. It recognizes grammar only. Calendar
interpretations always come from B3's public `parse_generic_date()` API.

The module is imported directly. It is deliberately not added to package
exports.

## 3. Approved identifiers

| Purpose | Exact value |
|---|---|
| Component version | `purchase-date-calendar-validity-v0` |
| Rule ID | `PURCHASE_DATE_CALENDAR_VALIDITY_V0` |
| Rule version | `v0` |
| Grammar reference | `PURCHASE_DATE_GRAMMAR_V0` |
| Profile ID | `purchase-date-calendar-validity-profile-v0` |
| Profile version | `v0` |
| Applicability reference | `PURCHASE_DATE_ONLY_V0` |
| Evidence namespace | `CANDIDATE_RECORD_V1` |
| B3 ruleset | `B3-generic-rules-v0` |
| Verified B3 Git blob | `73a929fe68c5459ea20c944069bf2cb05e86982a` |

The Git blob and populated metadata are reproducibility references. They do not
authenticate source bytes, owner identity, evaluator execution or an evaluation
freeze.

## 4. Grammar compatibility

The module mirrors the supported B3 date syntax without importing B3's private
regular-expression constants:

- year first: `YYYY-M-D` or `YYYY-MM-DD`, with hyphens;
- numeric day/month or month/day with the same `/` or `-` separator twice;
- day, English month name or abbreviation, four-digit year; and
- English month name or abbreviation, day with optional comma, four-digit year.

The mirror preserves B3's NFKC and outer-whitespace handling, default Unicode
digit semantics, named-date Unicode whitespace behavior, separator restrictions
and Python `re.IGNORECASE` month matching. It performs no locale selection,
date-window check or repair.

The public B3 parser remains the authority for calendar interpretations. G2A
validates the returned type, original literal, enum state, normalized value,
interpretation uniqueness and state shape. A recognizer/parser disagreement
raises `PurchaseDateParserCompatibilityError` instead of changing outcomes.

In particular, B3 `INVALID` is not mapped directly to G2A `FAIL`:

- recognized grammar plus no valid interpretations is `FAIL`;
- unsupported or malformed syntax is `UNAVAILABLE`.

Future changes to B3's parser, ruleset, grammar or relevant Python/Unicode
behavior require explicit compatibility review and conformance reruns.

## 5. Outcome mapping

| Condition | State | Attempted | Evidence | Reason kind | Code |
|---|---|---:|---|---|---|
| Exactly one distinct calendar-valid interpretation | `PASS` | `true` | `AVAILABLE` | `null` | `null` |
| Recognized grammar; every interpretation calendar-impossible | `FAIL` | `true` | `AVAILABLE` | `FAILURE` | `CALENDAR_DATE_IMPOSSIBLE` |
| Multiple distinct valid interpretations | `UNAVAILABLE` | `true` | `UNAVAILABLE` | `UNAVAILABILITY` | `AMBIGUOUS_DATE_INTERPRETATION` |
| Unsupported or malformed syntax | `UNAVAILABLE` | `true` | `UNAVAILABLE` | `UNAVAILABILITY` | `DATE_FORMAT_UNSUPPORTED` |

The deterministic non-pass details are:

- `All interpretations permitted by the approved purchase-date grammar are calendar-invalid.`
- `Multiple distinct calendar-valid interpretations; no unique date established.`
- `Candidate literal does not match the approved purchase-date grammar.`

The evaluator never emits `NOT_APPLICABLE`.

## 6. Source and configuration binding

Before parsing, the evaluator reconstructs the supplied
`HardConstraintOperandAuditResultV0` and candidate audit. It requires:

- the exact `CandidateOperandAuditV0` object stored in the D3 operand aggregate;
- the exact retained candidate object from the prepared D3 candidate tuple;
- the tuple's existing first permanent `c0` candidate;
- matching candidate, receipt, field and original B2 target identities;
- a `PURCHASE_DATE` target;
- one `CANDIDATE_RECORD_V1` reference whose ID and source version equal the
  exact candidate's `candidate_id` and `record_version`; and
- complete equality between the profile `Theta_A` and the D3 input `Theta_A`.

The evidence reference is only a structural pointer. It does not prove Python
object identity or authenticity. Exact live object binding is checked from the
existing D3 aggregate, and later aggregation must still use
`build_source_bound_constraint_result_v2(...)`.

The accepted profile contains exactly one mandatory rule at position zero, the
approved IDs and applicability reference, and no external resources. The
evaluator neither interprets nor modifies `Theta_A`.

## 7. Typed failures

The module exposes distinct failures:

- `PurchaseDateConfigurationError`: incompatible grammar or profile;
- `PurchaseDateParserCompatibilityError`: incompatible B3 ruleset/result or
  recognizer/parser drift;
- `PurchaseDateIntegrityError`: malformed or contradictory stored records;
- `PurchaseDateSourceBindingError`: substituted candidate/audit/evidence
  identity or non-purchase-date target; and
- `PurchaseDateEvaluationError`: unexpected public-parser execution failure.

These failures do not fabricate `ConstraintRuleOutcomeV2` records.

## 8. Synthetic verification

`tests/test_proposed_purchase_date_calendar_validity.py` uses only synthetic
records and covers:

- ISO, day-first, month-first and named valid dates;
- identical and distinct dual interpretations;
- impossible dates, leap-day validity and invalidity;
- unsupported separators, mixed separators, year lengths, month names and
  malformed literals;
- NFKC, Unicode digits, whitespace and Python case-insensitive month behavior;
- exact candidate, permanent `c0`, source audit, evidence and `Theta_A` binding;
- substituted audits and incorrect evidence namespace, ID or version;
- invalid profiles, grammar references, resources and B3 versions;
- parser-result and grammar drift;
- post-construction mutation and unexpected parser failure;
- deterministic outcome details; and
- compatibility with the existing source-bound V2 aggregate factory.

The tests establish structural and deterministic development behavior only.
They do not establish accuracy, dataset eligibility, methodology freeze or
held-out readiness.

## 9. Explicit limitations

The implementation does not:

- authenticate the B3 blob, profile, `Theta_A` or evidence records;
- modify Contract V0, V1 or V2;
- alter B2/B3 extraction or candidate generation;
- decide whether a missing/unresolved field should receive an audit;
- implement field-wide candidate completeness or aggregation;
- resolve HC-D06/HC-D07 or controller behavior;
- implement scoring, calibration, selection, review or persistence;
- access real receipts, validation data or held-out data; or
- authorize integration or evaluation.

Independent technical review and a separate authorized Git integration remain
mandatory.
