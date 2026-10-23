# Proposed Feature Input Readiness Observation V0

Status: provisional, synthetic-only implementation for Task 2.5E1.

## Purpose and boundary

`pipeline/proposed/feature_readiness.py` provides one public inspection entry
point:

```python
inspect_feature_input_readiness(
    *,
    operand_audit: HardConstraintOperandAuditResultV0,
) -> FeatureInputReadinessResultV0
```

It inventories raw information already stored in an exact D3
`HardConstraintOperandAuditResultV0`. It does not construct Equation 4.1
feature values, evaluate hard constraints, decide eligibility, score or
calibrate candidates, select a value, route review, or authorize persistence.
In particular, this observation is not a `READY`, `ELIGIBLE`, `PASS`, or
feature-computability decision.

The supplied operand-audit object is retained by reference. The observer does
not rerun OCR, the source gate, B1, B2, B3, candidate generation, ranking,
limiting, finalization, or the D3 operand audit.

## Local records

All records are frozen, slotted, and carry component-local V0 versions:

- `InputFactObservationV0` records one stored raw fact, relationship, absence,
  unbound dependency, or policy-dependent question.
- `FeatureSlotInputObservationV0` groups facts under one existing
  `FeatureSlot`.
- `CandidateFeatureInputObservationV0` binds seven ordered slot observations
  to an exact retained candidate and its exact D3 candidate audit.
- `FeatureInputReadinessResultV0` binds all candidate observations to the
  exact supplied operand audit.

The component-local presence vocabulary applies to individual facts:

- `PRESENT`: the datum or relationship is stored in the supplied object graph;
  this does not establish correctness or computability.
- `ABSENT_IN_STORED_GRAPH`: a supported nullable datum is absent in that graph,
  such as `confidence=None`.
- `NOT_BOUND_BY_INPUT_CONTRACT`: D3 exposes no approved binding for the fact or
  resource. This does not claim that the resource is globally nonexistent.
- `UNDETERMINED_WITHOUT_POLICY`: interpreting or associating the input requires
  a feature transformation or methodology that has not been approved here.

Numeric inputs and coordinates are preserved as type/module/repr fingerprints.
These fingerprints are lossless observational metadata for the stored Python
values used by this boundary; they are not normalized numbers or feature
values.

## Seven-slot inventory

Every retained candidate has exactly the existing contract order
`[q_o, q_e, a_l, a_y, s_r, s_a, s_p]`. Permanent c0 is first, and overflow
candidates are excluded.

| Slot | Observed inputs | Deliberately not performed |
| --- | --- | --- |
| `q_o` OCR evidence | Associated OCR token IDs, literal text, polygons through the layout slot, and each nullable model-native confidence; absence of an authenticated OCR-model binding is explicit. | Aggregation, normalization, calibration, confidence reinterpretation, or model authentication. |
| `q_e` extractor evidence | Exact B2 target field, stored confidence including `None`, extractor identifier, and existing source/row relationships. | OCR-confidence substitution or invented extractor metadata. |
| `a_l` lexical agreement | Permanent c0 value, candidate value, source literals, and each candidate-provenance record with source-kind distinctions. | Text similarity, terminology lookup, or reuse of preliminary-ranking edit similarity as the approved feature. |
| `a_y` layout agreement | Source-token polygons, B2 field association, item-row relationship, and D3 substitution position. | Candidate-specific geometry, distances, agreement, or ambiguity thresholds. |
| `s_r` retailer support | Stored store field and candidate identity. | Retailer matching or scoring; an approved retailer snapshot is not bound by D3. |
| `s_a` arithmetic support | D3 original B2 item and receipt-total operands, statuses, source IDs, row order, and candidate substitution position. | Parsing, candidate substitution, equations, tolerances, rounding, exceptions, completeness, or implicit B3 reuse. |
| `s_p` price-reference support | Stored store/date fields and candidate/item identity. | Fetching, inference, association, or scoring; no versioned price snapshot is bound by D3. Missing support is not zero, negative evidence, incorrect ground truth, or a review decision. |

The observer keeps original B2 arithmetic operands distinct from a future
candidate-substituted calculation. Similarly, `NOT_BOUND_BY_INPUT_CONTRACT`
for retailer and price snapshots is distinct from a nullable value that is
`ABSENT_IN_STORED_GRAPH`.

## Reconstruction and integrity

Construction and reconstruction require:

- complete revalidation of the supplied D3 operand audit;
- one observation for each exact retained candidate in upstream order;
- permanent c0 first and no overflow candidate;
- exact candidate, candidate-audit, field, token, row, and provenance
  relationships;
- capture-once identity binding to the exact supplied D3 operand-audit object at
  both aggregate and candidate-observation levels;
- exactly seven slots in immutable `FEATURE_SLOT_ORDER`;
- deterministic reconstruction of every fact from the retained graph;
- non-fabricated source and resource references; and
- component-local version consistency.

The aggregate stores a private immutable primitive snapshot. Both the aggregate
and every candidate observation also capture their original D3 operand-audit
object reference once in private, non-comparison metadata. Repeated
`__post_init__()` calls require identity with that capture using `is`; a newly
constructed value-equal D3 record is not the same upstream evidence reference.
Nested candidate observations must also point to the aggregate's exact D3
object. Fresh wrappers remain valid when they are constructed around the same
unchanged upstream objects. Validation never refreshes either the original
reference capture or the primitive snapshot.

Value equality is still used for deterministic reconstruction of observational
content, while object identity protects the explicit exact-reference boundary.
Together these provide structural, in-process consistency checking. They are
not cryptographic authentication, tamper-proof storage, proof of immutable
source bytes, proof of source-gate execution count, or authentication of a
Theta_A manifest. Deliberate coordinated modification of upstream records and
all private integrity metadata is outside this mechanism's guarantee.

## Explicit exclusions

This module does not create Contract V1/V2 constraint outcomes,
`CandidateEvidenceV1`, missingness masks, `feature_schema_id`, feature values,
hard-rule overrides, eligibility flags, scoring inputs, raw scores,
probabilities, field decisions, review records, or persistence outcomes. Its
API accepts no ground truth, held-out annotations, reference-provider clients,
rule overrides, scorer, calibrator, or downstream policy configuration.

No real receipts, external resources, held-out data, or trained components are
used by the tests.

## Known limitations

- Presence says only what the supplied graph stores; it does not establish
  semantic correctness or feature readiness.
- D3 does not bind authenticated OCR-model metadata, approved retailer or
  price-reference snapshots, or the future lexical/layout/arithmetic/price
  transformation policies.
- The input records do not resolve hard-constraint eligibility or the pending
  Contract V2 policy questions. Scoring must remain downstream of a future
  approved hard-constraint boundary; this observer cannot be used to bypass it.
- Object retention plus deterministic reconstruction is suitable for the
  current local synthetic boundary, but is not a serialization protocol or an
  authenticity mechanism across runtimes.

## Synthetic conformance coverage

The focused suite covers c0-only and altered populations, exact slot order,
slot and candidate substitution attacks, overflow injection, nullable OCR and
B2 confidence, token/polygon mutation, provenance and c0 preservation,
non-reuse of preliminary similarity, raw arithmetic operands, missing and
unresolved operands, absent versus unbound facts, non-fabricated references,
repeatability, non-refreshing reconstruction, API shape, and forbidden
downstream records.
