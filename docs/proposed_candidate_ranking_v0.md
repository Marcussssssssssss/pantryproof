# Proposed Preliminary Candidate Ranking V0

Status: provisional development component for independent review. This ranking
profile is not an authenticated validation-frozen `Theta_A` manifest and has
not been evaluated on held-out receipts.

Implementation: `pipeline/proposed/candidate_ranking.py`

Tests: `tests/test_proposed_candidate_ranking.py`

## Scope and authority

The moderated thesis requires altered candidates to be ranked after normalized
deduplication and before `candidateLimit`, hard constraints, evidence
construction or scoring. Its preliminary non-price tuple is:

1. ascending declared source-category priority;
2. descending normalized edit similarity to permanent c0;
3. ascending source-order displacement; and
4. ascending normalized candidate text.

V0 adds permanent altered candidate ID only as a final deterministic
serialization tie-breaker when every thesis component is equal. Candidate ID
does not change tie-group membership.

The thesis fixes the tuple and the exclusion of price and downstream evidence.
The exact field-compatible comparison strings, Unicode unit, Levenshtein
implementation, Decimal representation, OCR displacement formula, blocked
aggregate behavior and tie identity schema below are reviewed provisional
engineering choices.

## Public interface

```python
compute_preliminary_candidate_ranking(
    *,
    provenance_result: CandidateProvenanceMaterializationResultV0,
    configuration: CandidateRankingConfigurationV0,
) -> PreliminaryCandidateRankingResultV0
```

Both arguments are keyword-only. The component consumes the complete
provenance-materialization result and does not rerun OCR, B2 or B3.

It creates no altered `CandidateRecordV1`, applies no candidate limit and
accepts no hard constraints, price/reference evidence, scores, calibration,
ground truth or held-out outcome.

## Configuration and Theta_A binding

`CandidateRankingConfigurationV0` is frozen and slotted. It contains the
existing `ConfigurationRefV1` for `Theta_A`, the fixed profile identifier
`candidate-preliminary-non-price-rank-v0`, and local component/record versions.
It creates no separate configuration ID or namespace.

The configuration requires:

- `kind = THETA_A`;
- `state = READY`; and
- a nonempty existing content hash.

The aggregate requires exact equality with the reference stored at:

```text
provenance_result
  .identity_preparation
  .deduplication_result
  .candidate_drafts
  .suspicion_result
  .theta_a_ref
```

This is structural binding only. It does not prove that the content hash was
resolved against an immutable validation-frozen manifest or that the profile
was selected through a genuine validation route. Synthetic READY references in
unit tests are test fixtures, not real frozen configurations. A future trusted
configuration loader remains responsible for manifest authentication.

## Complete ranking boundary

The result preserves by reference:

- the complete `CandidateProvenanceMaterializationResultV0`;
- the existing permanent c0 `CandidateRecordV1`; and
- the optional c0-equivalence audit.

Every upstream altered identity is taken from its original identity-preparation
order and resolved to exactly one materialized or provenance-blocked source
record. Final ranking is independent of that discovery order.

Each ranked or ranking-blocked local record retains:

- the exact altered identity and stable candidate ID;
- the complete proposal-level provenance audit;
- materialized-versus-blocked provenance status;
- exact original and candidate normalization records;
- best genuine source priority;
- edit-similarity audit; and
- source-order-displacement audit.

The aggregate revalidates the complete upstream chain and reconstructs every
stored comparison component, position, tie group and readiness state.

## Source priority

Priority is computed from every contribution in the lossless upstream audit:

1. `SOURCE_TOKEN_OR_NEIGHBOUR`;
2. `GENERIC_NORMALIZATION`;
3. `RETAILER_MAPPING`; and
4. `PANTRY_TERMINOLOGY`.

The minimum genuine priority wins. Blocked contributions are not discarded.
For a provenance-materialized candidate, the minimum priority in the complete
shared provenance union must equal the complete-audit result.

Adapter seed position, B3 event order, representative discovery position,
price and downstream evidence are excluded.

## Exact normalized edit similarity

Comparison strings are the stored field-compatible canonical values:

- c0: `original_normalization.canonical_value`;
- altered candidate: `deduplicated_group.normalization.canonical_value`.

Neither exact display value is overwritten. Both canonical strings must be
nonempty; an empty value is an integrity failure.

V0 uses Python Unicode code points and deterministic integer Levenshtein
distance with two rolling rows, requiring `O(min(n, m))` memory. It introduces
no third-party dependency.

For maximum string length `M` and edit distance `d`:

```text
similarity = (M - d) / M
```

`EditSimilarityAuditV0` stores `d`, `M`, and the reduced exact numerator and
denominator. Ranking and tie identity compare those ratios with integer
cross-multiplication. Decimal or floating-point approximations never determine
order.

The shared `PreliminaryRankV1.normalized_edit_similarity` is produced in a
private Decimal context with:

- 34 significant digits;
- `ROUND_HALF_EVEN`; and
- no dependence on the ambient Decimal context.

That Decimal is a bounded shared audit representation. The retained reduced
fraction is authoritative for comparison and ties, including when two exact
fractions serialize to the same bounded Decimal.

## OCR source-order displacement

The sole token sequence is the ordered tuple:

```text
adapter_result.original_b2_result.receipt_output.source_evidence.tokens
```

The component validates unique token IDs, receipt identity, all c0 source-token
references and exact c0 source-token objects. Tuple position is the OCR source
order. It does not use dictionary order, geometry distance, adapter seed
position, B3 event order or rank position.

For best-priority source/neighbour contributions:

```text
D = min(abs(candidate_token_index - c0_token_index))
```

The minimum spans every genuinely recorded support token and every c0 source
token. Genuine neighbours outside the c0 token set are valid. Multiple genuine
spans can provide token positions even when shared observed-value composition
is provenance-blocked; ranking never composes their text.

Every best-priority source/neighbour contribution must supply at least one
genuine span. Missing support makes displacement unavailable. Unknown tokens,
cross-receipt evidence, invalid offsets or altered literal slices are integrity
errors rather than ordinary ranking blocks.

When generic normalization is the best source, V0 records displacement zero as
a provisional c0-anchored normalization convention. It is not a measured
spatial distance. Optional generic spans neither change the zero nor fabricate
a source-order relationship.

Retailer and pantry terminology displacement semantics remain unsupported.
They receive no invented zero or sentinel.

`SourceOrderDisplacementAuditV0` records source kind, ordered support token IDs
and receipt positions, exact c0 token IDs and positions, availability, derived
integer displacement, or the explicit unavailability reason.

## Provenance blocking versus ranking blocking

Provenance status and ranking availability are independent:

- A complete shared provenance union may be ranked.
- A provenance-blocked identity may still receive local rank metadata when all
  ranking components are defensible, for example a composite generic rule or
  multiple genuine source spans.
- A source/neighbour identity with missing support spans cannot receive a
  defensible displacement and is ranking-blocked.

If any identity is unrankable, the aggregate returns
`RANKING_BLOCKED`, exposes no partially definitive ranked list and preserves
every identity in `ranking_blocks`. The actual unrankable identity records its
specific displacement reason. Otherwise-rankable peers record
`AGGREGATE_BLOCKED_BY_PEER` because their final positions depend on the missing
comparison.

This state is not candidate-limit overflow, constraint rejection, low score,
nonsuspicion, fallback or review routing. The later orchestrator outcome is
deliberately unresolved.

## Deterministic total order and ties

When every altered identity is rankable, total order is:

1. source priority ascending;
2. exact rational similarity descending;
3. OCR displacement ascending;
4. normalized candidate text ascending; and
5. permanent altered candidate ID ascending.

Unique one-based `rank_position` values are assigned after the total sort.

Tie-group equality uses only the first three components. Groups of one receive
no tie ID. Within a group, normalized text and then candidate ID produce the
deterministic order.

The exact positional tie payload is:

```json
[
  "pantryproof-preliminary-rank-tie-id-v1",
  "candidate-preliminary-non-price-rank-v0",
  "<receipt_id>",
  "<field_id>",
  "<theta_a_configuration_id>",
  "<theta_a_configuration_version>",
  "<theta_a_content_hash>",
  1,
  9,
  10,
  0
]
```

The final four integers are source priority, reduced similarity numerator,
reduced similarity denominator and displacement. Candidate IDs,
representative spellings, contributor counts and discovery positions are
excluded.

Serialization uses compact canonical JSON with `ensure_ascii=False`, strict
UTF-8 and no BOM. The full lowercase SHA-256 digest is prefixed with:

```text
pp:rank:tie:v1:sha256:
```

Every ranked record retains the payload and canonical JSON. The aggregate
rejects distinct payloads producing the same tie ID. No fallback identifier is
created.

## Deferred boundaries

V0 deliberately does not implement:

- a numeric `candidateLimit`;
- boundary-tie or overflow policy;
- retained/overflow `CandidateLimitStatus` assignment;
- altered `CandidateRecordV1` construction;
- hard constraints or candidate evidence;
- price/reference support;
- scoring, calibration, candidate selection or replacement;
- review/fallback/failure routing; or
- a configuration-manifest loader.

A future limiting stage may consume a `READY` ranking result. A future finalizer
must still refuse to turn provenance-blocked identities into incomplete shared
candidate records.

No model training, threshold fitting, held-out tuning or evaluation result was
used to define this component.
