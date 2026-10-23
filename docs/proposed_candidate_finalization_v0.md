# Proposed Candidate Finalization V0

Status: provisional, synthetic-only implementation boundary.

## Authority and scope

The moderated FYP1 thesis, especially Section 4.3, Tables 4.5-4.6 and
Algorithm 4.1, requires permanent retention of the original B2 candidate
`c0`, deterministic altered-candidate limiting, and overflow audit before
candidate evidence is constructed. Contract V1 defines the constructor
invariants for `CandidateRecordV1`, `CandidateProvenanceV1` and
`PreliminaryRankV1`.

Candidate finalization is the deterministic bridge between the approved local
ranking/limiting audit and those shared candidate records. It does not add a
research algorithm. It does not perform OCR, B2/B3 extraction, candidate
generation, deduplication, provenance generation, ranking or limiting. It also
does not create constraints, price evidence, candidate evidence, scores,
calibrated probabilities, correction decisions, review actions or persistence
events.

The public API is:

```python
materialize_ranked_candidate_records(
    *,
    limit_result: CandidateLimitResultV0,
) -> CandidateFinalizationResultV0
```

The exact existing limit result is the only input. No second configuration,
numeric limit or downstream policy is accepted.

## Permanent original c0

`CandidateFinalizationResultV0.original_candidate` is a derived property that
returns `limit_result.original_candidate` by reference. The finalizer never
constructs another original candidate. Permanent c0 remains:

- the exact observed B2 value and identity;
- `CandidateRole.ORIGINAL`;
- `CandidateLimitStatus.RETAINED`;
- supported by its original provenance;
- outside altered-candidate preliminary ranking; and
- without an overflow reason.

The existing c0-equivalence audit is exposed by reference through the
`equivalent_to_c0` property. Equivalent-to-c0 proposals never become duplicate
shared candidates.

## Altered CandidateRecordV1 mapping

For a limit decision with complete materialized provenance, the finalizer uses
the following exact projection:

| Shared field | Frozen upstream source |
|---|---|
| `candidate_id` | Altered identity candidate ID |
| `receipt_id` | Altered identity receipt ID |
| `field_id` | Altered identity field ID |
| `c0_candidate_id` | Permanent original candidate ID |
| `value` | Exact representative display value |
| `normalized_dedup_key` | Existing normalized deduplication key |
| `role` | `CandidateRole.ALTERED` |
| `provenance` | Complete canonical materialized shared-provenance tuple |
| `preliminary_rank` | Exact existing shared rank object |
| `limit_status` | Mapping below |
| `overflow_reason` | Mapping below |
| `record_version` | Frozen Contract V1 version |

The canonical provenance ordering and each upstream provenance-member object
are preserved. Candidate IDs, values, keys, ranks and provenance are not
regenerated, normalized or merged by this stage.

If a supposedly materialized identity cannot satisfy `CandidateRecordV1`, the
operation raises `CandidateFinalizationIntegrityError`. The shared-constructor
exception remains available as `__cause__`; it is not converted into an
ordinary provenance-blocked outcome.

## Capacity mapping

| Local capacity decision | Provenance | Shared outcome |
|---|---|---|
| `WITHIN_CAPACITY` | `MATERIALIZED` | Altered `RETAINED` record, no overflow reason |
| `LIMIT_OVERFLOW` | `MATERIALIZED` | Altered `LIMIT_OVERFLOW` record with `TOTAL_CANDIDATE_LIMIT_EXCEEDED` |
| `WITHIN_CAPACITY` | `BLOCKED` | No shared record; exact blocked audit |
| `LIMIT_OVERFLOW` | `BLOCKED` | No shared record; exact blocked audit |
| Ranking unavailable | Any | No altered shared record or capacity audit |

Overflow shared records are audit-only. Contract V1 prevents them from being
used as `CandidateEvidenceV1` inputs.

## Diagnostic partial materialization and no backfill

Every provenance-complete retained or overflow identity is materialized.
Every provenance-blocked identity is preserved in a
`BlockedCandidateFinalizationAuditV0`, which holds the exact upstream
`CandidateLimitDecisionV0` by reference and the fixed reason
`SHARED_PROVENANCE_UNAVAILABLE`.

The decision provides the original candidate identity, rank, capacity status,
overflow reason and complete blocked-provenance record without copying those
facts into independent editable fields.

A blocked within-capacity identity is never skipped or replaced by a later
candidate. Other valid retained records may remain in the result for diagnosis,
but the aggregate is blocked. A future candidate-evidence consumer must require
`RETAINED_SET_STRUCTURALLY_FINALIZED` before accepting the retained tuple as a
complete candidate set.

This component does not route blocked results to review, fallback or
persistence.

## Retained-set readiness

`CandidateFinalizationReadinessV0` describes only the within-capacity altered
set:

- `RETAINED_SET_STRUCTURALLY_FINALIZED`: every within-capacity altered identity
  has a valid shared record.
- `BLOCKED_BY_RETAINED_PROVENANCE`: at least one within-capacity altered identity
  lacks complete shared provenance.
- `RANKING_UNAVAILABLE`: upstream ranking and limit decisions are unavailable.

These states do not establish authenticated configuration, production
eligibility, correction accuracy or held-out performance.

## Full altered shared-ledger coverage

`CandidateFinalizationCoverageV0` separately records coverage of altered
candidate identities as shared candidate records alongside permanent c0. It
does not claim that later pipeline evidence or decisions are complete.

Coverage statuses are:

- `COMPLETE_SHARED_LEDGER`: every altered identity has a valid shared record.
- `INCOMPLETE_BLOCKED_PROVENANCE`: at least one ranked altered identity remains
  only in a blocked audit.
- `RANKING_UNAVAILABLE`: identities remain in upstream ranking-block records.

For a ready ranking, the mutually exclusive terminal categories are:

1. retained materialized;
2. overflow materialized;
3. retained provenance-blocked; and
4. overflow provenance-blocked.

Together they cover every ranked altered identity exactly once.
`materialized_candidate_ids` is a derived concatenation of the retained and
overflow materialized IDs in original rank order; it is not a fifth terminal
category.

A blocked overflow identity leaves retained-set readiness structurally
finalized when all selected identities are representable, but makes the full
shared ledger incomplete. A valid empty altered set has finalized retained-set
readiness and a complete empty altered ledger.

## Ranking unavailable

When the limiting result is `RANKING_UNAVAILABLE`, finalization:

- preserves the exact limiting result and original c0;
- exposes the exact upstream ranking blocks by reference;
- creates no altered shared records;
- creates no capacity-blocked finalization audits;
- records every ranking-blocked candidate ID in coverage; and
- returns unavailable readiness and coverage.

This differs from a valid ready ranking with no altered candidates. Malformed
or forged unavailable aggregates raise an integrity error instead of being
treated as ordinary unavailability.

## Reconstruction and integrity

Both public consumption and aggregate reconstruction call the complete
`CandidateLimitResultV0.__post_init__()` validator. Finalization then
reconstructs its entire projection and verifies:

- exact c0 and c0-equivalence preservation through the limiting result;
- exact altered and parent c0 IDs;
- exact representative values and normalized keys;
- complete, ordered canonical provenance;
- identity of upstream provenance-member and preliminary-rank objects;
- correct roles, capacity statuses and overflow reasons;
- deterministic retained and overflow order;
- no duplicate, omitted or backfilled identity;
- no shared record produced from blocked provenance;
- exact blocked-audit decision references;
- exact unavailable-ranking coverage;
- correct retained-set readiness and ledger coverage; and
- supported component and record versions.

Newly constructed `CandidateRecordV1` instances are compared by complete field
value with their deterministic reconstruction. They need not have the same
Python object identity as a freshly reconstructed record. The upstream rank
and provenance-member objects must, however, remain the original references.

All shared candidates and their provenance members are revalidated during
aggregate reconstruction. Validation contradictions raise
`CandidateFinalizationIntegrityError`; wrapped constructor and upstream
validation errors retain their original causes.

## Configuration boundary and limitations

The exact `CandidateLimitResultV0` retains the existing C3C1
`synthetic-fixture-only-v0` scope and `Theta_A` reference. Revalidation checks
their current structural invariants. It does not provide cryptographic manifest
authentication or prove that `Theta_A` and `candidateLimit` are genuinely
validation-frozen.

Consequently, V0 does not establish:

- production configuration authenticity;
- production or Android readiness;
- a final numeric candidate limit;
- correction quality or automatic-commit eligibility;
- held-out receipt performance; or
- completeness of any evidence, constraint, scoring, calibration, review or
  persistence stage.

The implementation and tests use synthetic evidence only. Production manifest
authentication and all downstream research stages remain deferred.
