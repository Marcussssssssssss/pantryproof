# Proposed Candidate Draft Generation V0

Status: provisional component boundary for independent review

Implementation: `pipeline/proposed/candidate_generation.py`

Tests: `tests/test_proposed_candidate_generation.py`

## Purpose

Candidate Draft Generation V0 implements the bounded transition described by
Algorithm 4.1 lines 3–5: preserve the original B2 result as permanent `c0`, use
the validated suspicion result to decide whether altered sources are evaluated,
and expose already-recorded B3-compatible seeds as raw proposals.

This component is not a complete candidate-generation engine and makes no
claim about candidate coverage, correction accuracy, real-receipt performance,
production readiness, or held-out evaluation.

## Public API

```python
def generate_candidate_drafts(
    *,
    suspicion_result: SuspicionResultV0,
    adapter_result: ProposedAdapterResultV1,
) -> CandidateGenerationResultV0:
    ...
```

The two keyword-only inputs deliberately exclude price evidence, retailer
resources, terminology resources, ground truth, scoring and policy state.

The component defines frozen, slotted local records:

- `OriginalCandidateDraftV0`: exact unnormalized B2 `c0`, original candidate
  ID, B2 source-token order and complete `MethodReadyFieldV1` reference.
- `AlteredCandidateProposalV0`: one adapter-produced
  `B3CompatibleSeedV1`, retaining its existing seed ID as the proposal
  reference and its complete event, rule and span provenance.
- `CandidateSourceStatusV0`: auditable status for one permitted altered source.
- `CandidateGenerationResultV0`: the original draft, ordered altered proposals,
  source audit, and exact upstream suspicion and adapter records.

`CandidateGenerationResultV0` re-derives all output fields during validation.
An independently reconstructed result cannot substitute a different original,
proposal sequence or source-status audit while retaining the same upstream
records.

## Permanent c0

The original draft is constructed only from the selected method-ready field.
The generator verifies that:

- the complete method-ready record equals the adapter record selected by its
  method-field ID;
- the method-ready original field equals the corresponding field in the
  retained B2 receipt output;
- `source_image_id` equals the retained B2 source-evidence image ID;
- `source_processing_status` equals the retained B2 source processing status;
- the method-ready and adapter extraction statuses both equal the retained B2
  receipt extraction status;
- `b2_extractor_version` equals the retained B2 receipt extractor version;
- the selected method-ready field is not also listed among the adapter's
  excluded B2 field IDs;
- the original value equals permanent `c0`;
- the `c0` candidate ID is unchanged;
- source-token IDs remain in B2 order; and
- the method-ready source-token records equal the original receipt OCR tokens.

No normalization is applied to the `c0` value. A B3-transformed value cannot
replace it.

## Suspicion gate

When `SuspicionResultV0.is_suspicious` is false, the result contains only the
original draft. All four altered sources are recorded as
`NOT_EVALUATED_NO_SUSPICION`. Existing B3 seed presence does not create a new
suspicion signal.

The generator still checks adapter/seed integrity before returning this path;
source gating does not make contradictory upstream records acceptable.

## Candidate sources and ordering

The source audit always uses the thesis order:

1. `SOURCE_TOKEN_OR_NEIGHBOUR`
2. `GENERIC_NORMALIZATION`
3. `RETAILER_MAPPING`
4. `PANTRY_TERMINOLOGY`

For a suspicious field, V0 evaluates only existing adapter-produced B3 seeds
in the first two categories. Source-token proposals precede generic proposals,
while the original adapter order is retained within each category. The stored
adapter position is audit metadata, not a preliminary rank.

No new neighbouring-token scan or normalization rule runs here. Retailer and
pantry terminology sources are recorded as
`UNAVAILABLE_NOT_CONFIGURED` because no approved runtime snapshots exist. They
emit no proposals. Price evidence is not a candidate source or API input.

## Seed integrity

For the selected field, the generator verifies bidirectional agreement between
`MethodReadyFieldV1.b3_seed_ids` and the adapter seed collection:

- every declared ID has exactly one adapter seed;
- every adapter seed for the field is declared;
- seed IDs are unique;
- receipt and field identities match;
- `c0` candidate ID and exact value match;
- B3 ruleset references match;
- source kind is one of the two currently supported categories; and
- event and rule IDs are nonempty and unique.

The altered proposal embeds the complete immutable B3 seed. Composite event
and rule provenance and source spans therefore remain unchanged. An absent
source span stays absent; the generator does not fabricate one. Such a proposal
has limited literal-location provenance and that limitation must remain visible
when future candidate records are materialized.

The generator does not import or invoke `apply_b3()` and does not assert that a
seed has passed any hard constraint.

These checks establish internal consistency with the B2 output and B3 seed
metadata stored by the adapter. They do not independently authenticate that an
original B3 execution occurred, reconstruct its execution environment, or
prove that the stored event and rule identifiers were produced by that
execution. B3 authenticity remains an upstream adapter/orchestration boundary.

## Literal OCR span integrity

Span validation uses the original receipt OCR evidence retained by the
adapter. For every recorded span:

- the token ID must exist in the original receipt;
- the token must belong to the selected receipt;
- start and end must be non-Boolean integer offsets;
- the half-open range must be nonempty and within the original text; and
- `span.text` must equal `original_text[start:end]` exactly.

Normalized or B3-transformed text is never substituted for literal OCR text.

## Boundary with Task 2.5C

V0 deliberately does not create `CandidateRecordV1`. Altered shared candidate
records require a normalized deduplication key and `PreliminaryRankV1`, neither
of which is approved for this component.

Task 2.5C remains responsible for:

- field-compatible normalized keys;
- duplicate merging with provenance union;
- stable altered-candidate IDs;
- edit similarity and source displacement;
- preliminary ranking and tie handling;
- candidate limiting while always retaining `c0`; and
- final `CandidateRecordV1` materialization.

Hard constraints, evidence features, scoring, calibration, selection and
review routing also remain outside this component.

## Known unsupported sources and limitations

- General neighbouring-token discovery is not implemented.
- No new generic normalization is implemented beyond existing B3 seeds.
- Retailer and pantry terminology snapshots are not configured.
- Raw duplicate values intentionally remain separate proposals.
- A proposal with no recorded source span retains its seed provenance but
  cannot claim a literal character location.
- Proposal references are existing B3 seed IDs, not final candidate IDs.
- Candidate completeness and candidate quality are not assessed by this task.

## Synthetic verification

Verification performed on 2026-10-18 using the repository virtual environment:

```text
.\.venv\Scripts\python.exe -m unittest tests.test_proposed_candidate_generation -v
Ran 23 tests
OK

.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
Ran 260 tests
OK
```

The focused tests cover exact `c0` retention, suspicion gating, canonical source
ordering, seed-reference contradictions, receipt/field/`c0`/ruleset mismatches,
literal OCR spans, complete B2 source/extraction metadata consistency, field
exclusion contradictions, composite B3 provenance, raw duplicates, unavailable
resources, deterministic reconstruction, upstream immutability, API boundaries
and absence of B3 execution.
