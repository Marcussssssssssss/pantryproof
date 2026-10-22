# Proposed Altered Candidate Provenance Materialization V0

Status: provisional development component for independent review. It is not a
validation-frozen `Theta_A` configuration, does not claim held-out results and
does not change the frozen shared Contract V1.

## Authority and scope

The moderated thesis requires permanent c0, provenance-preserving candidate
deduplication and an auditable candidate boundary before hard constraints and
candidate evidence. Shared `CandidateProvenanceV1` defines the frozen record
shape. The exact projection rules, payload serialization, identifiers and
component-local blocking records below are approved provisional development
choices rather than thesis-prescribed algorithms.

`pipeline/proposed/candidate_provenance.py` exposes:

```python
materialize_altered_provenance(
    *, identity_preparation: CandidateIdentityPreparationResultV0
) -> CandidateProvenanceMaterializationResultV0
```

The function consumes the complete Task 2.5C2B identity and provenance-audit
result. It may create shared `CandidateProvenanceV1` members for altered
identities whose complete contribution set is safely projectable. It does not
create an altered `CandidateRecordV1`, rank or limit candidates, run hard
constraints, construct evidence, score, calibrate or route review.

The original shared c0 candidate and optional c0-equivalence audit are returned
unchanged and by reference. OCR and B3 are never rerun.

## Source-kind projection

### Generic normalization

A generic contribution is projectable only when it records exactly one B3 rule
ID. Its shared member uses:

- `source_kind = GENERIC_NORMALIZATION`;
- `original_observed_value` equal to the exact permanent B2 c0 value;
- the one genuine rule as `generic_rule_id`;
- every genuinely recorded source span, which may be empty;
- unique source token IDs in first span-appearance order; and
- no resource snapshot or source-order claim.

Multiple event IDs with one rule are allowed. Every event ID remains in the
linked `ProposalProvenanceAuditV0`; the shared shape has no event-ID field.
Multiple rule IDs remain atomically blocked because the adapter does not retain
an independently verifiable event-to-rule mapping. The component does not zip
parallel event and rule tuples or emit one apparently independent member per
rule.

### Source token or neighbour

A source/neighbour contribution is projectable only when it has exactly one
genuine source span. Its shared member uses:

- `source_kind = SOURCE_TOKEN_OR_NEIGHBOUR`;
- the exact literal span text as `original_observed_value`;
- the genuine span and its token ID;
- no generic rule or resource snapshot; and
- no source-order relationship or position.

The supporting token may be any token in the original receipt package,
including a genuine neighbour outside the permanent c0 field's token IDs. The
component never substitutes c0 source tokens as altered-value evidence.

No span is blocked as missing evidence. Multiple distinct spans are blocked
because the stored records do not define how to compose one observed value.
Their text is never concatenated and no separator is invented. Adapter seed
position is candidate-discovery metadata, not OCR spatial displacement.

### Retailer and terminology sources

`RETAILER_MAPPING` and `PANTRY_TERMINOLOGY` are not materialized in this
version. Current candidate generation has no approved immutable resource
snapshot input. An unexpected contribution of either kind is blocked with
`UNSUPPORTED_SOURCE_KIND_OR_RESOURCE`; no snapshot ID is fabricated.

Price evidence is not a candidate source and is not accepted by this component.

## Receipt-wide OCR revalidation

The component reaches the original receipt evidence through the exact retained
identity-preparation, deduplication, generation, adapter and B2 records. It does
not rely only on `MethodReadyFieldV1.source_tokens`, because neighbour evidence
may be outside those c0 references.

Before either projection or ordinary evidence blocking, every recorded span is
checked against the complete original receipt token package:

1. original token IDs are unique;
2. the token ID exists;
3. the token and evidence package belong to the candidate receipt;
4. offsets are non-Boolean integers;
5. `0 <= start < end <= len(token.original_text)`;
6. `span.text == token.original_text[start:end]`; and
7. recorded source-token IDs equal first span-appearance order.

Unknown tokens, receipt contradictions, invalid offsets, literal mismatches and
contradictory token ordering are integrity errors. In contrast, an otherwise
valid absent or multiple source/neighbour span is a recorded blocked outcome,
not corrupted evidence.

## Provenance-member identity

Every unique shared altered-provenance member uses this exact positional
payload:

```json
[
  "pantryproof-altered-provenance-member-id-v1",
  "1",
  "<receipt_id>",
  "<field_id>",
  "<altered_candidate_id>",
  "<source_kind>",
  "<original_observed_value>",
  ["<ordered_source_token_id>"],
  [
    ["<token_id>", 0, 4, "<literal_span_text>"]
  ],
  null,
  null,
  "<generic_rule_id-or-null>",
  "<resource_snapshot_id-or-null>"
]
```

The second value is `PROPOSED_CONTRACT_VERSION`. The consecutive nulls are the
absent source-order relationship and position. Optional rule and resource
positions contain a genuine string or JSON null, never placeholder text.

Serialization is:

```python
json.dumps(
    payload,
    ensure_ascii=False,
    separators=(",", ":"),
    allow_nan=False,
)
```

Strict UTF-8 bytes without a BOM are hashed using full, untruncated SHA-256.
The identifier is:

```text
pp:provenance:altered:v1:sha256:<64 lowercase hexadecimal characters>
```

The dedicated serializer accepts only strings, non-Boolean integer offsets,
explicit null and approved nested tuple/list structures. It rejects floats,
Boolean offsets, unsupported types, malformed positional shapes, invalid
Unicode, incompatible source-kind fields and unrecorded source-order claims.
It is deliberately separate from the candidate-identity serializer, which has
a different approved payload domain.

Distinct payloads producing the same ID are an integrity failure. No fallback
identifier or silent rehash is used.

## Exact deduplication and ordering

Shared provenance members are deduplicated only when their complete canonical
payload JSON is identical. Span contents, offsets and ordering are never
normalized away. Every upstream proposal remains in its existing lossless
identity audit, and every projectable proposal reference links to exactly one
unique shared member.

Contributor count, event count and discovery position are outside the member
identity. Adding another identical contributor therefore does not change the
member or altered-candidate ID. Nonidentical evidence remains separate.

The complete union is ordered by:

1. shared source-priority rank; then
2. canonical payload JSON.

This ordering is deterministic and independent of proposal discovery order.

## Atomic blocking

`ProvenanceBlockingReasonV0` distinguishes:

- `COMPOSITE_GENERIC_RULES`;
- `MISSING_SOURCE_NEIGHBOUR_SPANS`;
- `MULTIPLE_SOURCE_NEIGHBOUR_SPANS`; and
- `UNSUPPORTED_SOURCE_KIND_OR_RESOURCE`.

If every contribution behind an altered identity is projectable,
`AlteredCandidateProvenanceMaterializationV0` exposes the complete ordered
shared union and all contribution links.

If any contribution is blocked,
`BlockedAlteredCandidateProvenanceV0` exposes no shared provenance union. It
retains the complete upstream altered identity, every proposal audit and every
blocking record. Projectable contributions remain preserved in that upstream
audit but are not exposed as an apparently complete partial union.

Blocking is not candidate-limit overflow, constraint rejection, low score, no
suspicion or a user-review decision. The component does not decide whether a
future orchestrator should route a provenance-blocked candidate to review or a
stage-qualified failure.

## Aggregate integrity

`CandidateProvenanceMaterializationResultV0` retains the exact identity input
and deterministically partitions every altered identity into exactly one of:

- `materialized_candidates`; or
- `blocked_candidates`.

It rejects duplicate, omitted or cross-partition identities; changed c0 or
equivalence references; forged hashes or payloads; missing contribution links;
noncanonical member ordering; forged identity-stage blocking status; and any
output that differs from complete reconstruction from the upstream evidence.

All records are frozen and slotted. The input records are not mutated.

## Deferred boundaries

- Composite B3 event/rule relationships require the original B3 event records
  or a coordinated shared-contract extension; parallel ID tuples are not
  sufficient.
- Multiple source-span observed-value composition remains undefined.
- Retailer and pantry terminology resources need approved immutable snapshots.
- Altered `CandidateRecordV1` construction remains downstream because shared
  Contract V1 requires preliminary rank and candidate-limit state.
- Ranking, edit similarity, displacement, candidate limit, overflow and tie
  handling remain separate future components.
- Hard constraints, evidence features, price/reference support, scoring,
  calibration, correction policy, review routing and held-out evaluation are
  outside this component.
- This component authenticates consistency with the retained adapter evidence;
  it does not independently authenticate the historical B3 execution because
  `ProposedAdapterResultV1` does not retain the original `B3Result`.

No held-out receipt, threshold selection, model fitting, calibration fitting or
evaluation result was used to define this provisional implementation.
