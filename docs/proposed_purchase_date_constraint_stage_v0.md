# Purchase-Date Candidate-Set Constraint Stage V0

Status: `PROVISIONAL_DEVELOPMENT — PENDING INDEPENDENT IMPLEMENTATION REVIEW`

Decision IDs:

- `G2A-PURCHASE-DATE-CONSTRAINT-STAGE-01`
- `G2A-PURCHASE-DATE-CONSTRAINT-STAGE-01-ID-RESOLUTION`

This document records the bounded, synthetic-only implementation authorized by
Leng Wei Heng. It does not authorize Git integration or evaluation freeze.

## 1. Purpose and pipeline position

The stage connects the canonical D3 operand audit to the existing candidate-level
G2A purchase-date evaluator and source-bound Contract V2 factory:

```text
canonical D3 operand audit
  -> exact retained purchase-date candidates
  -> G2A calendar-validity outcome per candidate
  -> source-bound ConstraintResultV2 per candidate
  -> immutable ordered tuple
```

It is an audit execution boundary only. It does not decide which candidate is
best, remove a retained candidate, or authorize a correction.

## 2. Public interface

The module exposes exactly one public function:

```python
evaluate_purchase_date_constraint_stage_v0(
    *,
    operand_audit: HardConstraintOperandAuditResultV0,
    rule_profile_reference: HardConstraintProfileRefV2,
    grammar_reference: str,
) -> tuple[ConstraintResultV2, ...]
```

All arguments are keyword-only.

- `operand_audit` is the already constructed canonical D3 operand audit. It
  owns the exact retained candidate objects, candidate order, original B2
  evidence, permanent `c0`, and frozen `Theta_A` chain.
- `rule_profile_reference` is the existing one-rule G2A purchase-date profile.
  The canonical evaluator and V2 factory validate it against the D3 `Theta_A`.
- `grammar_reference` is the existing G2A grammar reference. The stage does not
  introduce or select another grammar.

No candidate, evidence, rule-outcome, or result identifiers are supplied by the
caller. No new public wrapper record is introduced. The module is deliberately
not added to `pipeline.proposed` package exports.

## 3. Candidate completeness and ordering

Before evaluation, `HardConstraintOperandAuditResultV0.__post_init__()` performs
complete deterministic D3 reconstruction. It requires exactly one operand audit
for every prepared candidate and preserves the exact upstream references in
canonical order.

The stage then iterates `operand_audit.candidate_audits` without sorting or
filtering. Therefore:

1. permanent original `c0` remains first;
2. every retained altered candidate remains present;
3. remaining candidates preserve canonical D3 order;
4. one G2A invocation and one `ConstraintResultV2` are produced per candidate;
5. missing, duplicate, reordered, rebound, or inconsistent candidate records
   fail D3 reconstruction instead of being skipped.

The stage never adds a candidate interpretation or changes a candidate value.

## 4. Deterministic IDs and evidence

The supplemental ID decision approves these stage-local templates:

```text
rule_outcome_id = {candidate_id}:{rule_id}:outcome
constraint_result_id = {candidate_id}:constraints:v2
```

The exact retained D3 `candidate_id` and canonical
`PURCHASE_DATE_CALENDAR_VALIDITY_V0` rule ID are used. The templates are scoped
only to this purchase-date stage and are not a global policy for future rules.

All outcome and result IDs are derived and checked before any candidate is
evaluated. Empty IDs or collisions raise `PurchaseDateIntegrityError`; the
stage never repairs, suffixes, or silently replaces an ID.

For each candidate, the stage creates the already approved structural evidence
reference:

```text
reference_namespace = CANDIDATE_RECORD_V1
reference_id = exact candidate.candidate_id
source_record_version = exact candidate.record_version
```

This reference is structural metadata. It does not independently authenticate
source bytes or replace the evaluator and V2 factory's live source-object checks.

## 5. G2A evaluation and V2 construction

For every candidate audit, the stage calls the canonical six-keyword-only
`evaluate_purchase_date_calendar_validity_v0()` exactly once with:

- the approved deterministic outcome ID;
- the same aggregate operand audit;
- the exact candidate-audit object from that aggregate;
- the supplied G2A profile and grammar;
- the exact derived `CANDIDATE_RECORD_V1` evidence reference.

The returned outcome is passed unchanged, as the sole ordered rule outcome, to
`build_source_bound_constraint_result_v2()`. The factory receives the exact
operand audit, candidate audit, profile, and approved deterministic result ID.

Consequently, existing G2A meanings remain unchanged:

- `PASS` remains successful calendar-valid evidence;
- `FAIL` remains a recognized but impossible calendar date;
- `UNAVAILABLE` remains ambiguous or unsupported evidence and is never
  reinterpreted as `PASS` or `FAIL`.

The V2 factory continues to validate exact candidate and permanent-`c0` object
identity, complete rule-profile coverage, profile equality, and frozen
`Theta_A` binding.

## 6. Determinism and failure behavior

Evaluation plans and IDs are deterministic functions of the canonical records.
Repeated evaluation of unchanged inputs produces equal ordered tuples and IDs.
The returned collection is an immutable Python tuple.

The stage is fail-closed and whole-stage:

- it first reconstructs the complete operand audit and derives all IDs;
- it does not catch or translate D3, G2A, parser-compatibility, configuration,
  source-binding, or Contract V2 exceptions;
- if any candidate raises, the applicable typed exception propagates;
- the local result list is not returned or exposed;
- no partial tuple, default evidence, substituted outcome, or skipped candidate
  is produced.

The stage consumes stored evidence only. It does not rerun OCR, B2 extraction,
full B3 extraction, candidate drafting, deduplication, identity/provenance
materialization, ranking, limiting, finalization, context preparation, or operand
auditing. The existing bounded G2A evaluator may continue to call B3's approved
public date parser.

## 7. Synthetic coverage

The dedicated tests cover:

- one-candidate permanent `c0` execution;
- multiple candidates in exact `c0`-first D3 order;
- one evaluator and factory call per retained candidate;
- one source-bound result per candidate;
- `PASS`, `FAIL`, and `UNAVAILABLE` preservation;
- deterministic repeated output and immutable tuple shape;
- exact candidate, `c0`, evidence, profile, provenance, and `Theta_A` binding;
- missing, duplicate, reordered, rebound, and inconsistent evidence rejection;
- non-purchase-date rejection;
- empty and colliding deterministic ID rejection before evaluation;
- whole-stage propagation of a middle-candidate compatibility error;
- absence of OCR, extraction, or D3 upstream reruns; and
- non-mutation of permanent `c0` and canonical source evidence.

All tests use synthetic records only.

## 8. Explicit exclusions and remaining dependencies

This stage does not approve or implement:

- another hard-constraint predicate or rule catalogue;
- feature construction or missingness encoding;
- scoring or calibration;
- candidate selection, rejection, replacement, or commitment;
- field-wide eligibility or unavailable-candidate controller policy;
- receipt-level orchestration or selective-verification routing;
- Android integration or UI behavior;
- SQLite or other persistence;
- source-byte, profile, configuration, or blob authentication;
- real-receipt, validation, or held-out evaluation; or
- evaluation freeze.

Later functionality remains dependent on separately approved hard-rule,
feature, scorer, calibrator, selection, controller, review, and persistence
boundaries. Independent implementation review is required before Git
integration.
