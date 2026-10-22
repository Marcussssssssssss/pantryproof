# Proposed Synthetic Candidate Limiting V0

Status: provisional synthetic-only development component for independent
review. It is not a validation-frozen `Theta_A` configuration, an authenticated
candidate limit, held-out evidence, or a production policy.

Implementation: `pipeline/proposed/candidate_limiting.py`

Tests: `tests/test_proposed_candidate_limiting.py`

## Scope and authority

The moderated thesis requires a bounded candidate set after deduplication and
preliminary non-price ranking, while permanently retaining original B2 `c0`.
Overflow candidates and ties remain auditable, and the limit belongs to the
automatic-method configuration because it can affect the pre-review prediction.
The limit or its validation grid, selection criterion, and tie rule must be
frozen before held-out access.

The thesis does not choose the numeric limit. V0 therefore accepts an explicit
synthetic fixture value and does not provide a default or claim a production
value. Its exact total-count arithmetic, no-backfill behavior, and strict
boundary-tie handling are reviewed provisional engineering choices.

## Public boundary

```python
apply_candidate_limit(
    *,
    ranking_result: PreliminaryCandidateRankingResultV0,
    configuration: CandidateLimitingConfigurationV0,
) -> CandidateLimitResultV0
```

Both arguments are keyword-only. The component consumes the completed ranking
result. It invokes that record's integrity reconstruction but never calls OCR,
B2, B3, candidate generation, provenance materialization, or public ranking to
create substitute results.

It does not construct altered `CandidateRecordV1`, hard constraints, evidence,
scores, calibration, candidate selection, review routing, persistence, or
evaluation output.

## Synthetic-only configuration

`CandidateLimitingConfigurationV0` is frozen and slotted. It contains:

- the existing READY `THETA_A` `ConfigurationRefV1`;
- a required non-Boolean integer `candidate_limit >= 1`;
- a nonempty diagnostic `fixture_reference`;
- limiting policy `total-candidate-limit-v0`;
- tie policy `strict-ranked-boundary-v0`;
- scope `synthetic-fixture-only-v0`; and
- fixed component and record versions.

The aggregate requires exact equality with the `Theta_A` reference stored in
the ranking configuration. This proves structural reference consistency only.
`ConfigurationRefV1.content_hash` is not recomputed here, and the separately
supplied numeric limit is not proven to be covered by that hash. A fixture
reference does not authenticate either the fixture or the limit.

Configuration integrity is checked at three distinct levels:

1. Construction calls `CandidateLimitingConfigurationV0.__post_init__()` and
   rejects invalid fields before the record is returned.
2. Consumption and aggregate reconstruction explicitly rerun those same
   invariants. This detects synthetic adversarial in-memory mutation of an
   already constructed frozen record before limiting decisions are applied or
   accepted as reconstructed output. The rerun also revalidates the nested
   `ConfigurationRefV1`, including its identity, version, state, hash/status,
   and record-version shape, before checking the limiting-specific `THETA_A`
   kind, READY state, and nonempty hash requirements.
3. Genuine manifest-level `Theta_A` authentication remains unavailable. Local
   invariant revalidation cannot prove that the numeric limit is covered by the
   referenced hash or that it was selected and frozen through the approved
   validation route.

There is deliberately no caller-controlled `authenticated`,
`manifest_verified`, or `production_ready` flag. A future trusted loader and a
separately reviewed configuration version must load canonical manifest bytes,
verify their hash, and confirm the pre-held-out freeze before production or
validation-frozen evaluation.

## Total-limit arithmetic

V0 interprets `candidateLimit` as the maximum total candidate count. Permanent
`c0` consumes one slot and is never ranked or overflowed.

```text
L = candidate_limit
A = L - 1                         # altered capacity
N = number of ranked altered identities
p = stored one-based altered rank

WITHIN_CAPACITY iff p <= A
LIMIT_OVERFLOW  iff p > A

within_capacity_count = min(N, A)
overflow_count        = max(0, N - A)
bounded_total_count   = 1 + within_capacity_count <= L
```

`candidate_limit=1` retains only `c0`. Equivalent-to-c0 proposals remain in
their existing equivalence audit and consume no altered slot.

## Ranking preservation

For a `READY` ranking, V0 requires consecutive one-based stored positions and
uses the candidates in that exact order. It does not recompute source priority,
edit similarity, source-order displacement, normalized text, candidate IDs, or
tie groups.

Each frozen `CandidateLimitDecisionV0` retains the exact upstream
`RankedAlteredCandidateV0` object. Its status is either:

- `WITHIN_CAPACITY`, with no overflow reason; or
- `LIMIT_OVERFLOW`, with the sole reason
  `TOTAL_CANDIDATE_LIMIT_EXCEEDED`.

Every ranked altered identity receives exactly one decision. Candidate identity,
complete source audit, shared provenance where available, provenance-blocking
records, exact similarity, displacement, rank, and tie metadata remain reachable
through the retained ranking record.

## Provenance-blocked slot accounting

Capacity and provenance completeness are independent:

| Capacity | Provenance | Meaning |
|---|---|---|
| Within | `MATERIALIZED` | Structurally eligible for later retained shared-record finalization |
| Within | `BLOCKED` | Consumes the slot and blocks retained-set finalization |
| Overflow | `MATERIALIZED` | Keeps rank, provenance, and overflow reason for later overflow-ledger finalization |
| Overflow | `BLOCKED` | Keeps both overflow and provenance-blocking audits locally |

A blocked identity is never skipped and a lower-ranked complete identity is
never promoted into its slot. A blocked overflow identity does not itself block
the retained set, but it still cannot become a complete shared altered record.

`CandidateRetainedSetReadinessV0` is deliberately narrow:

- `STRUCTURALLY_READY`: every within-capacity altered identity has materialized
  shared provenance and a valid local capacity decision;
- `BLOCKED_BY_SELECTED_PROVENANCE`: at least one within-capacity identity has
  blocked provenance; or
- `RANKING_UNAVAILABLE`: no complete ranking exists.

Structural readiness does not authenticate `Theta_A` or the numeric limit. It
also says nothing about overflow-ledger completeness, constraints, scoring,
automatic correction, review, or inventory commitment.

## Ranking-unavailable behavior

A valid upstream `RANKING_BLOCKED` result produces an auditable local result
with:

- limiting readiness `RANKING_UNAVAILABLE`;
- no capacity decisions;
- every upstream `CandidateRankingBlockV0` preserved unchanged and by reference;
- permanent `c0` and its equivalence audit preserved unchanged and by reference;
- boundary-tie status `RANKING_UNAVAILABLE`; and
- retained-set readiness `RANKING_UNAVAILABLE`.

The configured synthetic limit remains recorded but is not reported as applied.
This state is not treated as c0-only success, no suspicion, overflow, or an
ordinary integrity failure. A malformed or forged ranking record is rejected.

## Strict boundary-tie audit

The limit is never expanded to retain a complete tie group. A split exists only
when altered capacity `A` is positive and below `N`, and stored ranks `A` and
`A+1` share the same non-null tie-group ID.

`BoundaryTieAuditV0` uses the existing tie ID and stores:

- policy `strict-ranked-boundary-v0`;
- `NO_SPLIT`, `TIE_GROUP_SPLIT`, or `RANKING_UNAVAILABLE`;
- total limit and altered capacity;
- the split tie-group ID;
- every group member in stored rank order; and
- the exact within-capacity and overflow partitions.

No new tie identity, similarity threshold, or ranking comparison is introduced.
For `NO_SPLIT` and `RANKING_UNAVAILABLE`, all tie identity and member fields are
empty.

## Aggregate reconstruction

`CandidateLimitResultV0` retains the exact complete ranking result,
configuration, original c0, equivalence audit, decisions or ranking blocks,
boundary-tie audit, and retained-set readiness. Construction deterministically
rederives the entire result and rejects:

- mismatched `Theta_A`;
- invalid limits, scope, policies, or versions;
- malformed upstream ranking evidence;
- changed, missing, duplicated, substituted, or reordered identities;
- changed ranks or ranking metadata;
- incorrect capacity status or counts;
- backfilling around blocked identities;
- wrong overflow reasons;
- forged tie boundaries or partitions;
- changed c0 or equivalence references;
- missing or replaced ranking blocks;
- partial limiting of a blocked ranking; and
- changed retained-set readiness.

For `READY`, every decision must retain its corresponding exact upstream ranked
object by reference. For `RANKING_BLOCKED`, every block must retain its exact
upstream object by reference. Upstream objects are never mutated.

## Shared-record and evidence boundary

V0 creates no altered `CandidateRecordV1`. A separately approved finalizer may
later construct:

- `RETAINED` altered records only for within-capacity, provenance-materialized
  identities; and
- `LIMIT_OVERFLOW` altered records only for overflow,
  provenance-materialized identities, preserving rank and the approved reason.

Provenance-blocked identities cannot be converted into incomplete shared
records. Permanent c0 remains the already materialized original shared record.
Later candidate evidence must be restricted to genuine retained shared
candidates; Contract V1 already forbids evidence for overflow candidates.

## Deferred boundaries

The following remain unresolved or outside V0:

- numeric candidate-limit selection;
- validation grid, objective, optimisation route, and research freeze;
- authenticated `Theta_A` manifest and trusted configuration loader;
- altered shared-candidate finalization;
- complete overflow-ledger materialization;
- hard constraints and seven-slot evidence;
- scoring, calibration, candidate replacement, and selective verification;
- routing for retained provenance blockage; and
- persistence and held-out evaluation.

Passing the synthetic suite demonstrates structural and deterministic contract
behavior only. It is not evidence of receipt accuracy, calibrated probability,
production safety, or held-out performance.
