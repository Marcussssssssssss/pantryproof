# PantryProof Deterministic Suspicion Detector V0

Status: **PROVISIONAL COMPONENT IMPLEMENTATION - NOT EVALUATION-FROZEN**

This document describes `pipeline.proposed.suspicion`. The component implements
only Algorithm 4.1 line 4's upstream suspicion decision for an already-valid
`MethodReadyFieldV1`. It does not generate candidates, score or calibrate them,
route review, create a receipt disposition, or authorize persistence.

A result with no suspicion reasons means only that altered candidate generation
is not requested. Permanent original candidate `c0` remains in the future
candidate audit and scoring path.

## 1. Requirements and development choices

### Thesis-required boundary

The moderated thesis Sections 3.4.3 and 4.3.1, Tables 4.5-4.6, and Algorithm
4.1 line 4 limit suspicion to upstream evidence available before candidate
scoring:

1. OCR confidence;
2. extractor confidence;
3. missing required content;
4. parse/type failure;
5. line-association conflict; and
6. arithmetic contradiction.

Candidate confidence, calibrated probability, retailer evidence, price
evidence, ground truth, and evaluation outcomes are not detector inputs.
Missing evidence stays missing rather than becoming negative evidence.

### Approved provisional development choices

- OCR confidence uses `MIN_ALL_REFERENCED` over the exact source tokens retained
  by `MethodReadyFieldV1`.
- If any referenced OCR token lacks confidence, the aggregate is unavailable;
  no partial minimum is calculated.
- Extractor confidence is read only from the exact original B2 field.
- Missing confidence is `UNAVAILABLE`; it does not trigger low confidence.
- Low confidence means `confidence < configured_threshold`. Equality does not
  trigger.
- Thresholds, score sources, and inclusive numeric domains are explicit
  configuration values. Values are never clamped, rescaled, or imputed.
- Confidence values are represented locally as finite `Decimal` values for
  deterministic comparison while the original model-native values remain in
  the immutable upstream records.

No production threshold has been selected. Unit-test thresholds are synthetic
and test-only.

## 2. Public API

The module-level entry point is:

```python
def detect_suspicion(
    method_field: MethodReadyFieldV1,
    context: SuspicionContextV0,
    configuration: SuspicionConfigurationV0,
) -> SuspicionResultV0:
    ...
```

The function is imported directly from `pipeline.proposed.suspicion`; the shared
`pipeline.proposed` package exports were not changed.

All V0 records are frozen, slotted dataclasses with tuple collections:

- `ConfidenceRuleV0` records a rule ID, declared score source, aggregation,
  explicit threshold and inclusive numeric domain.
- `ConfidenceEvidenceV0` records one source evidence ID and its finite value or
  explicit absence.
- `ConfidenceObservationV0` records the full confidence vector, exact missing
  evidence IDs, availability, and aggregate.
- `UpstreamObservationV0` records one provider/version, receipt and field
  identity, typed check, state, evidence IDs, and reason.
- `SuspicionContextV0` binds the method field, gate, image and source-token IDs
  to the four orchestrator-owned non-confidence checks.
- `SuspicionConfigurationV0` binds both confidence rules and the expected
  context builder to one existing `ConfigurationRefV1` of kind `THETA_A` and
  state `READY`.
- `SuspicionResultV0` retains the exact method-ready record, context,
  configuration, Theta_A reference, both confidence observations, and ordered
  reasons. On every construction it deterministically re-derives both confidence
  observations from the embedded original OCR/B2 evidence and configured rules.
  The recorded observation must equal that derived record in source, rule,
  aggregation, evidence IDs and values, availability, missingness and aggregate.
  `is_suspicious` is derived from the reason tuple.
- `SuspicionIntegrityError` identifies corrupt or incompatible stored inputs.
  A future orchestrator may translate it to `FAILED/PRE_RESOLUTION`; this module
  does not create that disposition.

## 3. Canonical reason ordering

Reasons always follow this order, independent of which checks fail first:

1. `LOW_OCR_CONFIDENCE`
2. `LOW_EXTRACTOR_CONFIDENCE`
3. `MISSING_REQUIRED_CONTENT`
4. `PARSE_TYPE_FAILURE`
5. `LINE_ASSOCIATION_CONFLICT`
6. `ARITHMETIC_CONTRADICTION`

Multiple reasons may coexist. Evidence identifiers are retained without silent
deduplication; duplicate IDs are rejected as malformed provenance.

## 4. Confidence and availability rules

For OCR confidence, the detector reads the exact ordered
`MethodReadyFieldV1.source_tokens` vector. Every present value is validated
against the rule's declared domain. If all values are present, the aggregate is
their minimum. If at least one is absent, the complete vector and exact missing
token IDs are retained and the aggregate is `None/UNAVAILABLE`.

For extractor confidence, the detector reads
`MethodReadyFieldV1.original_b2_field.confidence` and uses `DIRECT`
aggregation. Current `B2-layout-graph-v0` normally emits `None`, so unavailable
extractor confidence is expected and does not by itself imply suspicion.

Boolean, nonnumeric, NaN, infinite and out-of-domain values are rejected.
Domains are not assumed to be normalized `[0, 1]`; each rule declares the native
score source and domain. The OCR source label supplied by the context must equal
the OCR rule source. The extractor source must equal the exact B2 extractor
version in the method-ready record.

## 5. Other upstream checks

The four non-confidence observations use these states:

- `PASS`: requires evidence IDs and no failure reason;
- `FAIL`: requires evidence IDs and a nonempty reason;
- `UNAVAILABLE`: requires a reason and cannot claim evidence IDs; and
- `NOT_APPLICABLE`: requires a reason and cannot claim evidence IDs.

Only an evidence-backed `FAIL` triggers its corresponding suspicion reason.
The provider ID/version must match the context builder bound by Theta_A.

Task 2.5A deliberately supplies these records synthetically. It does not
implement runtime completeness, parse/type, line-association or arithmetic
diagnostic providers. B3 transformed values, B3 seed presence and B3
`PRE_CORRECTION` arithmetic diagnostics are not automatically treated as
authoritative suspicion evidence.

## 6. Identity and configuration integrity

Before detection, the module rechecks:

- the original field is `EXTRACTED`;
- receipt, field and field-type identities agree;
- exact original B2 value remains permanent `c0`;
- B2 and method-ready source-token IDs and ordering agree;
- every token belongs to the receipt;
- the stored gate belongs to the receipt and is `SUFFICIENT`;
- context receipt, method-field, field, gate, image and token identities agree;
- context builder and score sources match the configuration; and
- the configuration retains a READY `THETA_A` reference and its existing
  content-hash field.

The local checks do **not** prove that the suspicion payload is the content that
produced the Theta_A hash. Trusted manifest loading, payload-hash verification
and formal evaluation freeze remain later integration work.

### Result-ID scope

`result_id` is deterministic from the method-field ID plus the Theta_A
configuration ID/version. It is not content-addressed: different upstream
contexts or observations can produce different valid results with the same ID.
The complete immutable result record must therefore be retained for audit, and
`result_id` alone must not be used as a unique persistence-event key. A stronger
orchestrator/audit identity design is deferred; V0 does not introduce an
unapproved hashing or serialization format.

## 7. Known limitations and unresolved integration work

- Production confidence thresholds and native score domains are unresolved.
- `MethodReadyFieldV1` does not carry OCR `SourceProvenance`; the future
  orchestrator must derive the OCR score-source label from the genuine source
  package rather than accepting arbitrary caller metadata.
- Real diagnostic-provider records and their immutable configuration manifests
  do not yet exist.
- Mapping missing companion fields to an extracted target field remains an
  explicit orchestrator design decision. Missing or unresolved B2 fields are
  never converted into fake method-ready fields.
- No candidate generator, scorer, calibration model, selective-verification
  policy, review UI, database or Android integration is implemented.
- No language-neutral fixture or new serialization contract is introduced by
  this component.
- The detector is not trained, calibrated, evaluated on Malaysian grocery
  receipts, or production-ready.

## 8. Verification at implementation time

Executed with the repository's existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_proposed_suspicion.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Observed results:

- focused suspicion suite: 26 tests passed;
- complete regression suite: 237 tests passed;
- failures and errors: 0.

The tests use synthetic evidence and synthetic test-only thresholds. No dataset,
OCR inference, model fitting, calibration fitting, or held-out evaluation was
performed.
