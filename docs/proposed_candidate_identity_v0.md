# Proposed Candidate Identity and Provenance Audit V0

Status: provisional development component for independent review. It is not a
validation-frozen automatic-method configuration and has not been evaluated on
held-out receipts.

## Scope

`pipeline/proposed/candidate_identity.py` consumes one validated
`CandidateDeduplicationResultV0` through this keyword-only interface:

```python
prepare_candidate_identities(
    *, deduplication_result: CandidateDeduplicationResultV0
) -> CandidateIdentityPreparationResultV0
```

It performs three bounded actions:

1. materializes permanent B2 c0 as one valid shared ORIGINAL
   `CandidateRecordV1`;
2. assigns stable content-derived identities to deduplicated altered groups;
3. preserves every altered proposal in a complete component-local provenance
   audit and classifies whether later shared provenance projection is blocked.

It does not materialize an altered `CandidateRecordV1` or altered
`CandidateProvenanceV1`. It does not rank, limit, constrain, construct evidence,
score, calibrate, select, or route review. Price evidence and ground truth are
not inputs.

The thesis requires permanent c0, provenance-preserving deduplication and a
bounded candidate set before candidate evidence is constructed. The precise
JSON identity schema, prefixes, SHA-256 encoding and local projection statuses
are approved provisional implementation choices rather than thesis-prescribed
algorithms.

## Original c0 shared record

The component constructs exactly one `CandidateRecordV1` for the exact
method-ready B2 value:

- `candidate_id` and `c0_candidate_id` are the existing permanent c0 ID;
- receipt, field, value and normalized key come from the exact validated
  upstream records;
- role is `ORIGINAL`;
- limit status is `RETAINED`;
- preliminary rank and overflow reason are absent; and
- provenance contains exactly one `ORIGINAL` member.

The ORIGINAL provenance retains the exact c0 value and exact ordered B2 source
token IDs. Its character spans are empty because no separate original
field-offset record exists. It claims no generic rule, resource snapshot,
source-order relationship or source-order position.

The permanent c0 candidate ID is never hashed or replaced. Only its provenance
member receives a deterministic ID.

### Original provenance identity

The positional payload is:

```json
[
  "pantryproof-original-provenance-id-v1",
  "<receipt_id>",
  "<field_id>",
  "<c0_candidate_id>",
  "<exact_c0_value>",
  ["<ordered_source_token_id>"]
]
```

The full lowercase SHA-256 digest is prefixed with:

```text
pp:provenance:original:v1:sha256:
```

## Altered candidate identity

Every deduplicated altered group receives this exact positional payload:

```json
[
  "pantryproof-altered-candidate-id-v1",
  "candidate-field-normalization-v0",
  "<receipt_id>",
  "<field_id>",
  "<c0_candidate_id>",
  "<normalized_deduplication_key>"
]
```

The normalization profile is taken from the validated upstream result. It is a
development-version dependency, not a new `Theta_A` namespace.

Serialization uses:

```python
json.dumps(
    payload,
    ensure_ascii=False,
    separators=(",", ":"),
    allow_nan=False,
)
```

The serialized value is encoded using strict UTF-8 without a BOM and hashed
with full, untruncated SHA-256. The candidate ID is:

```text
pp:candidate:altered:v1:sha256:<64 lowercase hexadecimal characters>
```

Unpaired Unicode surrogates and unsupported payload value types are rejected.
The aggregate derivation records every candidate ID and canonical payload. Two
different payloads producing the same ID are an integrity failure; no fallback
ID or silent rehash is used.

Representative spelling, proposal IDs, adapter positions, provenance order and
provenance count are deliberately outside the identity payload. Therefore new
supporting provenance or a newly preferred exact representative does not change
the candidate ID when the normalized field-compatible value remains the same.
Receipt, field, c0 identity, normalization profile or normalized-key changes do
change the ID.

## Altered identity drafts

`AlteredCandidateIdentityDraftV0` retains:

- candidate, receipt, field and c0 identities;
- exact normalized deduplication key;
- exact representative display value;
- complete `DeduplicatedAlteredGroupV0`;
- exact positional payload and serialized JSON; and
- normalization, identity-schema, component and record versions.

It contains no rank, similarity, displacement, limit state or overflow reason.
It is not a shared candidate record.

## Lossless proposal-level provenance audit

`ProposalProvenanceAuditV0` is constructed once for every contributing raw
proposal and retains the complete proposal and B3 seed plus explicit copies of:

- proposal and parent altered-candidate identity;
- source kind and exact proposed value;
- original adapter seed position;
- B3 ruleset ID;
- every B3 event ID and every B3 rule ID;
- every exact source-character span;
- token IDs derived only from those genuine spans;
- complete method-ready field; and
- permanent c0 ID and exact value.

Non-representative proposals are retained. Proposal order equals the canonical
deduplication-group order. No event-to-rule pairing, source token, span,
resource snapshot or source-order relationship is inferred.

`AlteredCandidateProvenanceAuditV0` joins one altered identity to all its
proposal audits and records `has_blocked_contributions`. Its constructor
requires every upstream contributing proposal exactly once and in order.

## Projection classification

The local classification is advisory input to a future reviewed materializer;
it is not proof that `CandidateProvenanceV1` construction succeeded:

- `PROJECTION_DEFERRED`: the recorded shape appears sufficient for a future
  mapping. A single-rule generic seed may use this state even without spans.
- `BLOCKED_COMPOSITE_GENERIC_RULES`: a generic seed contains multiple rule IDs
  without an independently verified event-to-rule mapping.
- `BLOCKED_MISSING_SOURCE_TOKENS`: a source/neighbour seed has no genuine
  candidate-specific spans from which source-token IDs can be retained.

A source/neighbour contribution is only deferred when genuine validated spans
identify its source tokens. Method-ready c0 tokens are never substituted as
altered-candidate support.

Blocked contributions remain attached to their candidate identity with all
evidence intact. `has_blocked_contributions=True` is a fail-closed requirement:
a future shared altered-candidate finalizer must refuse that identity unless a
separately approved provenance-resolution record exists. Blocking does not mean
limit overflow, hard-constraint rejection or a low score.

No altered `CandidateProvenanceV1` is created in this version, including for a
`PROJECTION_DEFERRED` contribution.

## c0-equivalent proposals

The existing `EquivalentToC0AuditV0` is retained unchanged and by reference in
the aggregate result. Such proposals create no altered identity and are not
attached to ORIGINAL shared provenance.

## Reconstruction and integrity

Every local record validates its exact derivation. The aggregate
`CandidateIdentityPreparationResultV0` stores the complete upstream
deduplication result and re-derives:

- the original shared candidate;
- every altered identity;
- every proposal audit and projection classification;
- blocked-contribution state; and
- the c0-equivalence sidecar.

It rejects changed payloads or hashes, duplicate/colliding IDs, substituted
receipt/field/c0 identity, missing contributions, forged classifications,
changed original candidates, and results that remove blocked evidence. All
records are frozen and slotted; upstream records are not mutated.

## Deferred work and limitations

- Altered shared candidates require the later deterministic non-price ranking
  and `candidateLimit` result before `CandidateRecordV1` can be constructed.
- A later reviewed provenance materializer must define the exact projection of
  deferred local audits into shared V1 provenance.
- Composite generic rules remain blocked until genuine rule/event mapping or a
  coordinated shared-contract extension exists.
- Missing source/neighbour token evidence remains blocked; tokens are never
  invented.
- Retailer and pantry terminology snapshots remain unavailable and are not
  fabricated.
- Candidate identities indicate equality under the provisional normalization
  profile; they do not establish real-world semantic correctness.
- The component does not authenticate the original B3 execution independently;
  it consumes the already-validated adapter, generator and deduplication chain.
- No held-out receipt, threshold selection, model fitting or evaluation was
  used to define this implementation.
