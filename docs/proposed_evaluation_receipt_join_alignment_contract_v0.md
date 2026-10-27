# Provisional Receipt-Join and Alignment Contract Specification V0

Status: `PROPOSAL — NOT APPROVED — NOT EVALUATION_FROZEN`

## 1. Authority, purpose, and non-authorization boundary

This document proposes offline-only records and validation boundaries for two
separate operations:

1. associating one scoped runtime prediction receipt with one independently
   identified Task 2.5A reference receipt; and
2. recording matched and unmatched prediction/reference item rows after a
   separately approved deterministic matcher has run.

The proposal does not approve the schema, select a matcher, establish receipt
identity, authorize data access, authenticate provenance, implement code, or
permit held-out execution. It does not assume runtime receipt IDs and reference
receipt IDs are equal. It never adds reference truth to runtime records.

The moderated thesis PDF is not present in this repository. Thesis-labelled
requirements below are traced through
`docs/proposed_evaluation_protocol_v0.md`; direct PDF re-verification is not
claimed by this task.

The terms used in this document are:

- `CONFIRMED_REQUIREMENT`: already established by the merged contracts or the
  proposed evaluation protocol's traced thesis requirements;
- `PROPOSED_SCHEMA_SHAPE`: a candidate offline representation requiring schema
  approval; and
- `PENDING_APPROVAL`: a decision that this document deliberately does not make.

## 2. Repository foundation and evidence inventory

Repository inspection was performed on branch
`feat/tai-receipt-join-alignment-spec-v0` at merge commit `64ee9ca`. The working
tree was clean before this document was created.

| Evidence | Repository location | Relevant established boundary |
| --- | --- | --- |
| Reference receipt identity and ordered rows | `evaluation/reference_schema.py:273-304`, `349-409` — `ReferenceItemRow`, `TierAReferenceReceipt` | Reference receipt, row, and field IDs are independent evaluation identities. Reference rows carry validated `source_order`. |
| Reference availability and provenance | `evaluation/reference_schema.py:84-153`, `157-269` — `ReferenceValue`, `AnnotationProvenance`, `ReferenceField` | Reference values, availability, annotation/adjudication evidence, and normalization metadata remain independent of predictions. |
| Reference integrity and finalization | `evaluation/reference_validation.py:185-269` — `validate_reference_receipt()`, `validate_evaluation_ready_receipt()`, `validate_reference_collection()` | Duplicate receipt/row/field identities and linkage conflicts are rejected. Structural finalization does not establish dataset eligibility. |
| Dataset/manifest identity | `evaluation/manifest_schema.py:296-358` — `EvaluationManifest` | Manifest ID/version, dataset ID/version/tier, annotation version, partitions, receipt membership, cohorts, grouping, provenance, and alignment-development declarations already exist. |
| Manifest receipt and cohort membership | `evaluation/manifest_schema.py:131-182` — `ReceiptManifestEntry`, `CohortDefinition` | Manifest receipt IDs are Task 2.5A reference identities. Cohort presence is declared metadata, not approval. |
| Partition/group leakage validation | `evaluation/manifest_validation.py:70-177`, `223-234` | Each reference receipt has one manifest partition assignment; related-record transitive components cannot cross partitions; declared cohorts resolve to known manifest receipts. |
| Alignment-development controls | `evaluation/manifest_schema.py:186-233`; `evaluation/manifest_validation.py:180-220` | The alignment-development set is a training subset, not a fourth partition, and requires fitting-exclusion evidence. Declared evidence is not independent verification. |
| Prediction scope and complete receipt namespace | `evaluation/prediction_schema.py:100-142`, `277-299` — `EvaluationRunScope`, `PredictionBundle` | Dataset, tier, partition, cohort, run, system, configuration, and output stage jointly namespace prediction receipts. |
| Prediction receipt and row identity | `evaluation/prediction_schema.py:190-273` — `PredictionItemRow`, `PredictionReceipt` | Runtime receipt/row IDs remain opaque. `output_ordinal` is explicit and non-semantic. Fallback and execution-failure envelopes have no rows. |
| Prediction uniqueness and manifest-scope checks | `evaluation/prediction_validation.py:74-204` | Duplicate rows/ordinals/fields and complete prediction receipt keys are rejected. Current validation checks manifest scope but intentionally performs no receipt join. |
| Baseline adapter boundary | `evaluation/prediction_adapters.py:74-116`, `151-205`, `246-322` | B1/B2/B3 adapters require explicit ordinals, preserve runtime IDs and fallback absence, and do not infer reference IDs or run scope. |
| Exclusion/audit categories | `evaluation/exclusion_ledger.py:41-103`, `173-308` | Missing prediction, system failure, reference unavailability, adjudication pending, and configuration/freeze failure remain distinct audited conditions. |
| Common matcher requirements | `docs/proposed_evaluation_protocol_v0.md:227-282` | The protocol states the high-level deterministic matching sequence and its training-only selection boundary. |
| Leakage/freeze requirements | `docs/proposed_evaluation_protocol_v0.md:455-515`, `647-686` | Alignment inputs/configuration require freeze evidence, and schema, methodology, data-governance, synthetic implementation, and held-out authorization are separate gates. |

No existing module implements receipt joining, row-alignment link records, a
line matcher, threshold selection, or alignment scoring.

## 3. Identity namespaces and ownership

### 3.1 Namespaces that must remain separate

`CONFIRMED_REQUIREMENT`:

- `TierAReferenceReceipt.receipt_id` is the independent reference/manifest
  receipt identity.
- `PredictionReceipt.runtime_receipt_id` is a runtime producer identity inside
  one complete `EvaluationRunScope`.
- `ReferenceItemRow.row_id` and `PredictionItemRow.runtime_row_id` are different
  subordinate namespaces even when their strings happen to be equal.
- A source-reference string, filename, digest string, OCR image ID, or equal
  receipt-ID text is evidence to assess; none proves identity by itself.
- A receipt join is offline evaluation metadata. It must not be stored in
  `ReceiptOutput`, `PredictionReceipt`, proposed-method decisions, or another
  runtime object.

### 3.2 Proposed ownership

`PROPOSED_SCHEMA_SHAPE`: creation and verification should be separated:

1. A data-governance-authorized offline identity-mapping process creates a
   declared association from approved de-identified capture/transaction
   evidence. It must not use prediction correctness or alignment outcomes.
2. A distinct reviewer or independently recorded verification process checks
   the mapping against the authorized evidence and scope.
3. Tai-owned evaluation infrastructure validates and consumes the resulting
   records but does not infer the mapping from strings, images, descriptions,
   model output, or reference values.
4. Methodology reviewers approve the schema and permitted use; data-governance
   owners authorize dataset access and the mapping evidence. Structural code
   cannot grant either approval.

The precise creator/verifier eligibility, separation-of-duty requirement, and
authorization mechanism remain `PENDING_APPROVAL`.

## 4. Receipt-to-reference join proposal

### 4.1 Proposed logical records

Names and enum spellings in this section are `PROPOSED_SCHEMA_SHAPE`.

#### `ReceiptJoinOutcomeV0`

Three coverage outcomes are needed:

- `JOINED`: both a runtime prediction receipt and a reference receipt exist and
  are explicitly associated;
- `REFERENCE_ONLY`: an expected manifest/reference receipt has no emitted
  prediction receipt in the scoped bundle; and
- `PREDICTION_ONLY`: a scoped prediction receipt has no authorized reference
  membership in the selected manifest population.

`REFERENCE_ONLY` is not reference unavailability. It records only that the
selected reference population contains a receipt for which the scoped
prediction coverage contains no associated prediction receipt. It does not by
itself calculate false negatives, classify a system failure, or authorize any
denominator inclusion or exclusion. Those consequences belong to the later
approved evaluator and exclusion-ledger rules. `PREDICTION_ONLY` may be retained
for audit, but must block its use in the eligible reference population unless a
separately approved population rule accounts for it.

#### `ReceiptJoinVerificationStateV0`

The representation must distinguish at least:

- `UNVERIFIED`: required verification evidence is absent;
- `DECLARED`: a creator has declared the mapping and evidence references; and
- `INDEPENDENTLY_VERIFIED`: a distinct verification record and verifier
  reference are present.

These names are provisional. A state and its required fields are structural
claims only. A validator cannot establish that an external verifier was
eligible or that evidence was truthful.

Verification evidence is outcome-specific and must not be conflated:

- `JOINED` requires evidence for the declared identity association between the
  named runtime receipt and the named reference receipt, plus evidence that
  both sides resolve within the supplied prediction and selected reference
  coverage.
- `REFERENCE_ONLY` contains no runtime receipt identity and therefore has no
  receipt-association claim to verify. Its evidence must instead establish the
  reference receipt's selected-population membership and the completeness of
  the authorized run-input/execution roster and scoped prediction artifact
  used to assert that no associated prediction receipt was produced. Absence
  must not be inferred by searching for an equal runtime-ID string.
- `PREDICTION_ONLY` contains no reference receipt identity and therefore has no
  receipt-association claim to verify. Its evidence must instead establish the
  prediction receipt's membership in the complete scoped prediction artifact
  and the completeness of the authorized selected-reference population and
  identity-mapping process used to assert that no authorized reference link
  exists.

No unmatched outcome may fabricate the absent identity, a mapping event, a
verification event, a prediction receipt, or a reference receipt. The final
state decomposition may require separate association-verification and
coverage/absence-verification states rather than the illustrative single enum
above. Its exact states, evidence fields, verifier rules, and readiness effect
remain `PENDING_APPROVAL` under SCH-JA-03.

#### `ReceiptJoinProvenanceV0`

Proposed fields:

- join event ID;
- mapping-process/version ID;
- one or more authorized identity-evidence references;
- creator role or pseudonymous actor reference;
- optional recorded timestamp; and
- optional amendment/predecessor reference.

This record must not contain reference field values or prediction correctness.
Evidence references must identify stored audit material rather than copying
receipt images into the join contract.

#### `ReceiptJoinAuthorizationV0`

Proposed fields:

- authorization state;
- authorizing-role reference;
- authorization-record reference;
- authorized dataset/manifest/partition/cohort scope; and
- optional validity/amendment reference.

An authorization string alone does not prove authorization. A future validator
may check consistency and required presence; only the approved external
governance process can establish authority.

#### `ReceiptJoinEntryV0`

Proposed fields:

- stable `join_entry_id`;
- `ReceiptJoinOutcomeV0`;
- runtime receipt ID, nullable only for `REFERENCE_ONLY`;
- reference receipt ID, nullable only for `PREDICTION_ONLY`;
- outcome-appropriate association or coverage/absence evidence references;
- outcome-appropriate verification state or states;
- optional independent-verifier and verification-record references;
- reason code/detail for an unmatched side; and
- schema version.

For `JOINED`, both receipt IDs are mandatory. The record must store the two IDs
separately and must never replace one with the other. For either unmatched
outcome, the absent-side ID must remain null and the record must not contain
association-verification evidence for a nonexistent pair.

#### `ReceiptJoinSetV0`

One join set is proposed for one immutable prediction bundle scope. Fields:

- join-set ID and version;
- manifest ID and manifest version;
- dataset ID, dataset version, and dataset tier;
- partition ID and cohort ID;
- prediction bundle ID;
- run ID, system ID, configuration ID, and output stage copied from the bundle
  scope;
- join provenance and authorization records;
- tuple of join entries;
- optional set-level verification/audit reference; and
- schema version.

Copying scope identifiers into the join set makes cross-artifact validation
possible without changing `PredictionBundle`. It does not create a second
source of truth: validators must require exact equality with the supplied
manifest and prediction bundle.

### 4.2 Cardinality

`PROPOSED_SCHEMA_SHAPE`, recommended for approval:

For a join set naming partition `P` and cohort `C`, the **selected reference
population** is exactly the intersection of:

1. manifest receipt memberships whose `partition_id` is `P`; and
2. the receipt IDs declared by the manifest's `CohortDefinition` for `C`.

Both operands must come from the same supplied manifest ID/version and dataset
ID/version. Neither the full partition alone nor the full cohort alone may be
silently substituted for this intersection.

- Within one join set, actual `JOINED` associations form a partial one-to-one
  mapping: each scoped runtime receipt ID appears once and each reference
  receipt ID appears once.
- Every prediction receipt in the supplied bundle appears exactly once as
  `JOINED` or `PREDICTION_ONLY`.
- Every reference receipt in the selected manifest partition/cohort population
  appears exactly once as `JOINED` or `REFERENCE_ONLY`.
- Globally, one reference receipt may legitimately appear once in each
  different system/run/configuration/output-stage/cohort join set. This is not
  a one-to-many join inside a scope; it is repeated evaluation under distinct
  complete scopes.
- The same runtime receipt string may appear in another complete scope without
  collision. Its scoped identity is the complete `EvaluationRunScope` plus the
  runtime receipt ID.

Across a collection, the complete **source-scope key** consists of manifest and
dataset versions, partition, cohort, prediction bundle, run, system,
configuration, and output stage. The separate **join-set record key** consists
of join-set ID and join-set version. Distinct complete source scopes remain
distinct even when their runtime receipt IDs are identical. A collection must
not contain two unrelated current heads for the same source-scope key. If two
records claim that role or contain different coverage/associations without an
approved revision relationship, they are conflicting duplicates and must fail
closed.

A correction must create a separately identified auditable revision. The new
record must retain the predecessor join-set ID/version, amendment reason,
amendment provenance, and applicable authorization/verification evidence. It
must not mutate, replace, or silently overwrite the historical join set.
Whether a collection designates one revision as current, and the exact lineage
fields, remain `PENDING_APPROVAL` with the join-set schema.

This cardinality preserves paired comparison without assuming equality of
source IDs and prevents one runtime receipt from being reused for two reference
transactions in the same run.

### 4.3 Proposed validation boundary

A future structural validator should reject:

- duplicate join-set or join-entry IDs;
- duplicate runtime-side or reference-side coverage within one join set;
- `JOINED` entries missing either side;
- `REFERENCE_ONLY` entries containing a runtime receipt ID;
- `PREDICTION_ONLY` entries containing a reference receipt ID;
- conflicting mappings for either side;
- selected reference population membership that is not exactly the
  partition/cohort intersection;
- join-set dataset, tier, manifest, partition, cohort, bundle, run, system,
  configuration, or output-stage metadata that disagrees with supplied source
  contracts;
- a reference receipt absent from the manifest or reference collection;
- a reference receipt assigned to another partition or absent from the named
  cohort;
- a runtime receipt absent from the supplied prediction bundle;
- a reference record whose receipt ID disagrees with manifest membership;
- incomplete coverage of either the selected manifest population or prediction
  bundle;
- conflicting duplicate join sets for the same complete source scope;
- duplicate revision identities, broken or cyclic predecessor lineage, or an
  amended association without amendment reason/provenance;
- invalid verification-state/verification-evidence combinations; and
- authorization records whose declared scope conflicts with the join set.

An unverified or merely declared `JOINED` association may be serialized for
audit, but an alignment-ready validator must reject it. Unverified
coverage/absence claims for `REFERENCE_ONLY` or `PREDICTION_ONLY` likewise
cannot become alignment-ready. A populated hash, source reference,
authorization string, or provenance string cannot upgrade either association
verification or coverage/absence verification. The precise readiness states
remain subject to SCH-JA-03 approval.

Structural reference finalization, manifest eligibility, join verification,
and held-out authorization are separate gates. A valid join cannot make a
draft reference final, make an ineligible receipt eligible, authenticate a
manifest, or permit held-out access.

### 4.4 Missing and fallback receipt behavior

- If an expected reference receipt has no `PredictionReceipt`, represent it as
  `REFERENCE_ONLY`. Do not fabricate a runtime receipt, fallback, rows, or
  fields. This records prediction-receipt absence only; it does not itself
  decide field-level false-negative counts, system-failure classification, or
  denominator treatment. The later approved metric contract and exclusion
  ledger remain authoritative.
- A genuine fallback is different: it is an actual `PredictionReceipt` with a
  runtime receipt ID and no rows. It may be `JOINED` to its reference receipt.
  Later row coverage then consists entirely of unmatched reference rows.
- An execution-failure `PredictionReceipt`, if a separately authorized future
  producer creates one, follows the same identity rule as fallback and must not
  fabricate rows.
- A `PREDICTION_ONLY` receipt is retained as an integrity/audit outcome; it
  cannot silently enter an eligible reference-based denominator.

## 5. Prediction-to-reference row-link proposal

### 5.1 Separation from the matching algorithm

`CONFIRMED_REQUIREMENT`: a successfully completed row-link contract records
what an approved matcher did. It does not define, execute, tune, or repair that
matcher. Constructing a structurally valid link record cannot demonstrate that
the selected pair was methodologically correct. A blocked alignment record is
not a matcher result.

Receipt-level fields require no item-row match. After a verified receipt join,
their association is determined by their unique receipt-level field role.
Item-level fields require a verified row link; within a matched row, fields are
associated by their item-level role. Any future field-link layer must preserve
the original field IDs and these dependencies.

### 5.2 Proposed logical records

#### `RowAlignmentOutcomeV0`

- `MATCHED`;
- `PREDICTION_ONLY`; and
- `REFERENCE_ONLY`.

For a successfully completed alignment, every emitted prediction row and every
adjudicated reference row must be represented exactly once. Unmatched rows are
first-class outcomes, not absent records. A blocked record follows the separate
requirements in Section 5.3 and must not claim complete row coverage.

#### `RowMatchModeV0`

For matched rows, the protocol currently implies at least:

- `EXACT_NORMALIZED_DESCRIPTION`; and
- `THRESHOLDED_NORMALIZED_LEVENSHTEIN`.

Enum names are provisional. Unmatched outcomes have no match mode and instead
require an unmatched reason. No manual/ad-hoc match mode should be introduced
without an approved methodology amendment and provenance route.

#### `RowMatchEvidenceV0`

Proposed auditable content:

- matcher configuration ID/version;
- normalization specification ID/version;
- distance specification ID/version where applicable;
- exact threshold-selection record reference where applicable;
- references to the immutable prediction and reference description fields;
- normalized comparison strings or immutable references to their stored
  normalization outputs;
- exact match/distance evidence in a non-floating deterministic representation;
- prediction and reference order evidence actually used by the matcher;
- equal-cost tie-break evidence; and
- matcher implementation/software version.

The exact normalized-distance encoding, storage of normalized strings, and
order-evidence form are `PENDING_APPROVAL`. Binary floating-point values should
not be the sole reproducibility evidence.

#### `PredictionReferenceRowLinkV0`

Proposed fields:

- stable row-link ID;
- receipt-join entry ID;
- row-alignment outcome;
- runtime receipt ID and runtime row ID, nullable only for `REFERENCE_ONLY`;
- reference receipt ID and reference row ID, nullable only for
  `PREDICTION_ONLY`;
- copied prediction `output_ordinal` for audit, explicitly non-semantic;
- copied reference `source_order`;
- optional match mode and match evidence, required only for `MATCHED`;
- optional unmatched reason, required only for an unmatched outcome;
- alignment event/provenance reference; and
- schema version.

The copied order fields must equal their source records. Storing them does not
approve prediction `output_ordinal` as matcher source order.

#### `ReceiptRowAlignmentV0`

Proposed fields:

- receipt-alignment record ID;
- receipt-join entry ID;
- matcher configuration ID/version;
- alignment state such as completed or structurally blocked;
- tuple of row links;
- typed blocking reason or blocking-reason reference when blocked;
- references to the available prediction/reference row identity inventories;
- alignment provenance; and
- schema version.

The final state names, whether partial diagnostic attempts are stored outside
the canonical row-link tuple, and the exact blocking-reason schema remain
`PENDING_APPROVAL` under SCH-JA-05.

#### `RowAlignmentSetV0`

Proposed fields:

- alignment-set ID/version;
- receipt-join set ID/version;
- manifest and dataset identity;
- complete prediction run scope;
- matcher configuration and frozen-selection references;
- alignment-development subset/freeze reference where applicable;
- tuple of receipt-alignment records;
- set-level provenance/verification evidence; and
- schema version.

### 5.3 Proposed row-link validation

A future validator should first distinguish successfully completed and blocked
receipt-alignment records. For a successfully completed record it should
require:

- exact agreement between the alignment-set scope and its receipt-join set;
- one receipt-alignment record for every receipt-join coverage entry;
- all row IDs to resolve to the receipt identities named by the join entry;
- each prediction row to appear once as `MATCHED` or `PREDICTION_ONLY`;
- each reference row to appear once as `MATCHED` or `REFERENCE_ONLY`;
- no row ID to be substituted merely because its text equals another row;
- exactly two sides and match evidence for `MATCHED`;
- exactly one side and an unmatched reason for unmatched outcomes;
- one-to-one matched pairs, with no split, merge, or many-to-one link;
- copied output/source order values to equal their source records;
- matcher configuration identity to be identical across one alignment set;
- match-mode evidence to be consistent with the selected frozen matcher; and
- complete, noncontradictory alignment provenance.

For a successfully completed record covering a `JOINED` fallback or
execution-failure receipt with no prediction rows, every reference row must be
`REFERENCE_ONLY`. For a completed `REFERENCE_ONLY` receipt coverage entry, the
same complete reference-row coverage is required without a fabricated runtime
receipt. For a completed `PREDICTION_ONLY` entry, every prediction row is
unmatched and the record remains outside the eligible reference population.

For a blocked record, proposed minimum structural requirements are:

- a typed blocking reason or an explicit reference to a separately typed
  blocking record;
- the receipt-join entry and matcher/configuration identity that were intended
  or attempted, without claiming that the matcher completed;
- preservation or immutable references to every available prediction and
  reference receipt/row identity at the point of blocking;
- provenance for the blocking event and stage;
- no `MATCHED` or completed unmatched outcome presented as a canonical matcher
  result; any retained partial diagnostic trace must be clearly non-result
  evidence under the future approved schema; and
- no metric outcome, score, denominator action, or claim of complete one-to-one
  row coverage.

A record that claims completion but lacks complete one-to-one coverage must be
rejected. A genuinely blocked record is not required to fabricate coverage for
rows the matcher did not process, but it must not discard source identities
that were already available. Final alignment-state names, partial-trace
handling, and blocking-reason fields remain `PENDING_APPROVAL` under SCH-JA-05.

### 5.4 Deterministic serialization order

`PROPOSED_SCHEMA_SHAPE`: canonical serialization should sort by identity rather
than display text or inferred source order:

1. join sets by complete evaluation scope, join-set ID, then join-set version;
2. join entries by outcome, null-safe reference receipt ID, null-safe runtime
   receipt ID, then join-entry ID;
3. receipt alignments by join-entry ID; and
4. row links by outcome, null-safe runtime row ID, null-safe reference row ID,
   then row-link ID.

This order is only an interchange convention. The matcher processing order and
monotonic constraint must be separately approved and recorded. Serializers must
not reorder stored source-token references or mutate source contracts.
Historical join-set revisions remain separately serialized records linked by
their approved lineage representation; canonicalization must not collapse an
older revision into its successor.

## 6. Matcher methodology: confirmed versus unresolved

| Topic | Confirmed requirement | Still unresolved; no choice is made here |
| --- | --- | --- |
| Unicode normalization | Apply Unicode NFKC. | Unicode database/runtime version, error handling, and whether normalization output is stored or recomputed. |
| Case/whitespace | Case fold, trim, and collapse repeated whitespace. | Exact whitespace character set, case-fold implementation/version, and treatment of invisible/control characters. |
| Punctuation | Preserve punctuation that changes product identity or a numeric value. | Approved significant-punctuation catalogue, contextual exceptions, punctuation canonicalization, and examples. |
| Exact matching | Pair exact normalized-description matches before edit-distance matching. | Assignment among duplicate exact strings, whether exact matches are chosen globally under monotonicity, and handling of conflicting exact candidates. |
| Edit distance | Remaining candidates use normalized Levenshtein distance. | Normalization denominator, empty-string behavior, code-point versus grapheme units, exact arithmetic representation, and malformed-text handling. |
| Monotonicity | Remaining matching operates under monotonic source order. | Approved prediction-side source order. C1A `output_ordinal` is explicitly non-semantic and cannot be used without Tai/methodology approval. Interaction between exact matches and global monotonicity is also unresolved. |
| One-to-one matching | Split/merged many-to-one matches are prohibited. | Whether the implementation is dynamic programming, another global optimizer, or a proven equivalent deterministic procedure. |
| Duplicate descriptions | Duplicate rows remain distinct identities. | Deterministic assignment of duplicate exact/cost-equal rows beyond the stated tie rules. |
| Equal-cost ties | Prefer smallest absolute order difference, then earlier reference index. | Final tie completion if both remain equal; definition of prediction/reference index under the approved order policy. |
| Missing/unresolved descriptions | Prediction fields retain their runtime `MISSING`/`UNRESOLVED` states; reference availability remains independent. | Whether such rows are forced unmatched, block the receipt alignment, or use another prospectively approved evidence route. No fallback policy is selected here. |
| Threshold development | Select from a predeclared finite grid using training-only alignment F1; smaller threshold wins an F1 tie. | Grid values, distance precision, alignment-F1 definition, labelled-unit definition, minimum evidence, and selected value. |
| Masking/leakage | Frozen comparator predictions generate examples; trained annotators label matched/unmatched pairs with system identity masked; subset is training-only and excluded from fitting. | Masking implementation/audit, annotator/adjudicator workflow, comparator set, label schema, disagreement handling, access controls, and freeze authority. |
| Validation/held-out use | Validation and held-out results cannot choose or revise the matcher. | Exact technical access-control mechanism and independent pre-run verification process. |

The reference `source_order` is executable today. No corresponding approved
prediction source-order field exists. This is the principal methodology blocker
for matcher implementation, but it does not block synthetic join/link schema
work that treats `output_ordinal` only as recorded metadata.

## 7. Proposed synthetic validation design

These are future tests, not implemented by this document.

| Scenario | Required future assertion |
| --- | --- |
| Different runtime/reference receipt IDs | A verified explicit `JOINED` entry is valid when all manifest, bundle, scope, and evidence links agree; string equality is unnecessary. |
| Equal receipt strings without evidence | Equality alone cannot create or verify a join. |
| Outcome-specific verification | `JOINED` requires pair-association evidence; `REFERENCE_ONLY` and `PREDICTION_ONLY` require complete coverage/absence evidence and contain no fabricated pair-verification event or absent-side ID. |
| Duplicate join entry or side | Reject duplicate entry IDs, repeated runtime-side coverage, repeated reference-side coverage, and conflicting mappings. |
| Selected population boundary | Require exactly the intersection of receipts assigned to the named manifest partition and receipts declared in the named cohort. Reject union, partition-only, or cohort-only substitution. |
| Duplicate complete join-set scope | Reject conflicting join sets that claim the same manifest/dataset versions, partition, cohort, bundle, run, system, configuration, and output stage. Keep different complete scopes distinct. |
| Join-set amendment | Require a new join-set ID/version, predecessor link, reason, provenance, and applicable authorization/verification; retain the prior record and reject silent overwrite or undocumented change. |
| Cross-dataset link | Reject any join-set, bundle, manifest, authorization, or reference dataset conflict. |
| Cross-partition link | Reject a reference assigned to another manifest partition or a bundle scope naming another partition. |
| Contradictory cohort | Reject a reference absent from the join set's declared cohort. |
| Missing prediction receipt | Preserve one `REFERENCE_ONLY` receipt entry without fabricating fallback/output. The record asserts receipt-level absence only; later approved metric and ledger rules decide false-negative, failure, and denominator consequences. |
| Fallback receipt | Permit an explicit verified receipt join to the real no-output prediction receipt; require no prediction rows and all reference rows unmatched. |
| Prediction without eligible reference | Preserve `PREDICTION_ONLY` for audit and block inclusion in the eligible reference population. |
| Unverified association or absence | Permit audit serialization but reject alignment-ready validation. A hash/provenance string cannot verify either a joined association or unmatched coverage/absence. |
| Unauthorized held-out mapping | Reject alignment/evaluation readiness even if identity structure is valid. |
| Duplicate product descriptions | Preserve separate runtime/reference row IDs and one-to-one coverage; never collapse by description text. |
| Successfully completed matched/unmatched alignment | Every row on both sides appears exactly once across matched and unmatched outcomes. |
| Broken/substituted row identity | Reject row IDs belonging to another receipt, nonexistent rows, or text-based ID substitution. |
| Missing/unresolved prediction description | Preserve the row and status; exercise the eventually approved policy without silently deleting the row. Until approval, matcher execution is blocked. |
| Unavailable/pending reference description | Preserve reference state; reject any matcher path not explicitly permitted by the approved methodology/finalization gate. |
| Many-to-one or split/merge | Reject repeated matched use of any prediction or reference row. |
| Incomplete completed alignment | Reject a completed record that omits a source row, contains a row twice, omits match evidence, or has contradictory outcome fields. |
| Blocked alignment | Require typed/referenced blocking reason, available source identity preservation, intended configuration and blocking provenance; prohibit completion, canonical match outcomes, metric output, and complete-coverage claims. |
| Inconsistent matcher identity | Reject mixed normalization, distance, threshold, implementation, or matcher configuration IDs in one set. |
| Output ordinal treated as approved source order | Reject the matcher configuration unless the prediction order policy has separately recorded approval. |
| Threshold development outside training subset | Reject validation/held-out membership, unknown subset IDs, or missing fitting-exclusion evidence. |
| Unmasked development labels | Reject the masking/conformance claim and block matcher freeze. |
| Post-held-out matcher change | Record configuration/freeze failure and require a new approved run; do not rewrite prior links. |

## 8. Consolidated decision register

### 8.1 Tai-owned extraction and prediction-identity decisions

| ID | Exact question | Options | Recommended option | Evidence/rationale | Owner | Blocks | Synthetic structural work independently? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TAI-JA-01 | What approved prediction-side order may the monotonic matcher consume? | C1A `output_ordinal`; a new separately evidenced source-order declaration; no monotonic matching until another source exists. | Prefer a separately approved/evidenced order unless Tai and methodology review establish that recorded tuple position is the required source order. | C1A and C1B explicitly describe `output_ordinal` as non-semantic (`prediction_schema.py:190-207`; adapter documentation lines 120-135). | Tai with methodology reviewer | Matcher implementation and tie evidence | Yes; link schema can copy ordinal only as audit metadata. |
| TAI-JA-02 | Which artifact proves baseline producer/version identity for join/alignment freeze, especially B1/B2 fallback? | Prediction provenance plus external artifact registry; extend a future offline run manifest; rely on module constants. | Use external immutable run/artifact evidence; do not treat module constants as artifact proof. | C1B cannot verify B1/B2 fallback versions from their result envelopes (`prediction_adapters.py:208-243`). | Tai/shared freeze reviewer | Evaluation execution and freeze audit | Yes. |

Already settled and not reopened: B1/B2/B3 adapters preserve opaque runtime
identities; B3 preserves B2-origin row/field identities; missing/unresolved
fields remain explicit; adapters never infer reference IDs; and
`ReceiptExtractionStatus.FAILED` can remain structured output.

### 8.2 Shared evaluation-schema decisions

| ID | Exact question | Options | Recommended option | Evidence/rationale | Owner | Blocks | Synthetic structural work independently? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SCH-JA-01 | Should receipt joining use paired-only links or a complete coverage envelope? | Store only pairs; store pairs plus separate missing ledgers; use `JOINED`/`REFERENCE_ONLY`/`PREDICTION_ONLY` coverage entries. | Complete coverage entries. | It makes missing prediction receipts auditable and prevents denominator disappearance without fabricating runtime objects. | Shared evaluation-schema reviewers | Receipt-join schema | No implementation until schema choice; documentation/tests can be designed. |
| SCH-JA-02 | Is one join set bound to exactly one complete prediction bundle scope? | One scope per set; mixed scopes with per-entry scope. | One immutable scope per set. | C1A complete scope is already the prediction identity namespace and simplifies duplicate/cardinality validation. | Shared evaluation-schema reviewers | Receipt-join schema | No implementation until approved. |
| SCH-JA-03 | What join verification-state model and evidence fields are required? | Boolean verified flag; unavailable/declared/independently-verified states; external signed registry only. | Typed states plus state-dependent evidence, while leaving authentication external. | Task 2.5B already distinguishes declared and verified evidence and forbids treating a digest string as authentication. | Shared schema + data governance | Join readiness validator | A structural prototype can proceed after record-shape approval. |
| SCH-JA-04 | Should structural and alignment-ready validation be separate? | One strict validator; structural validator plus readiness validator. | Separate validators. | Unverified records can be retained for audit without being accepted for alignment; reference finalization and dataset eligibility are already distinct. | Shared evaluation-schema reviewers | Validator API | Yes after approval. |
| SCH-JA-05 | What exact row-link/evidence decomposition is approved? | Single flat link; link plus evidence; per-receipt record plus set envelope and evidence. | Per-receipt coverage plus separate match evidence and set envelope. | Supports complete coverage, one matcher identity, and audit without embedding algorithm behavior in constructors. | Shared evaluation-schema reviewers | Alignment-link schema | No implementation until approved. |
| SCH-JA-06 | What canonical serialization order is approved? | Source order; prediction ordinal; stable identity-key sorting. | Stable identity-key sorting for interchange, with algorithm order recorded separately. | Determinism must not imply that output ordinal is authoritative source order. | Shared evaluation-schema reviewers | Serializers/cross-runtime fixtures | Yes after approval. |

### 8.3 Methodology decisions

| ID | Exact question | Options | Recommended option | Evidence/rationale | Owner | Blocks | Synthetic structural work independently? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MTH-JA-01 | What executable normalization specification implements NFKC, case folding, whitespace collapse, and significant punctuation? | Versioned standard-library profile; external library profile; custom frozen table/profile. | Choose a versioned profile with a conformance corpus; no specific profile is selected here. | Protocol fixes operations but not the Unicode/runtime version or punctuation catalogue. | Methodology reviewers | Matcher and threshold labels | Yes for opaque configuration references. |
| MTH-JA-02 | How is normalized Levenshtein distance defined? | Divide by max length, reference length, sum length, or another predeclared formula; code points versus graphemes. | No recommendation without thesis/method review; require exact rational/decimal evidence and empty-string rules. | “Normalized Levenshtein” is stated, but its executable denominator is not. | Methodology reviewers | Matcher, grid, alignment F1 | Yes for schema only. |
| MTH-JA-03 | What deterministic global matching procedure satisfies exact-first, monotonic, one-to-one behavior? | Greedy; dynamic programming; another proven equivalent global optimizer. | Prefer a globally defined deterministic objective after formal review; do not select an algorithm here. | Greedy choices can conflict with later monotonic/one-to-one optimum and duplicate descriptions. | Methodology reviewers | Matcher implementation | Yes for link schema. |
| MTH-JA-04 | How are exact duplicate descriptions paired? | Earliest monotonic pairing; minimize order difference globally; include exact pairs in the global objective. | Resolve jointly with MTH-JA-03 and stated tie rules. | Protocol preserves duplicates but does not fully specify collision assignment. | Methodology reviewers | Matcher implementation | Yes. |
| MTH-JA-05 | What completes equal-cost tie-breaking after order difference and earlier reference index remain tied? | Earlier prediction order; lexical stable ID; global path ordering. | Predeclare a total ordering that does not use truth values; no option selected here. | Existing tie rules may still leave equal global solutions. | Methodology reviewers | Determinism proof/tests | Yes. |
| MTH-JA-06 | What happens when prediction or reference description is missing, unresolved, unavailable, pending, or malformed? | Force unmatched; block receipt alignment; approved alternate-evidence route. | Preserve the state and block unsupported paths; exact policy requires approval. | Silent repair/deletion would change FP/FN coverage and violate reference-state boundaries. | Methodology + annotation reviewers | Matcher and metric population | Yes for records/validators. |
| MTH-JA-07 | What threshold grid, alignment-label unit, and alignment-F1 formula are frozen? | Candidate grids/formulae predeclared by reviewers. | Use a finite training-only grid and smaller-threshold tie rule as required; values/formula remain undecided. | Protocol lines 249-274 fix the selection boundary but not numerical values or full label schema. | Methodology reviewers | Threshold-development task | Yes for schema references, not selection. |
| MTH-JA-08 | Which frozen comparator predictions generate development examples? | B1/B2/B3 individually; one named comparator; a predeclared union. | Must be named before labels/results; no comparator set selected here. | Protocol says frozen comparator predictions but does not identify the exact set for this producer. | Methodology reviewers with Tai | Masked annotation and threshold freeze | Yes for generic schema. |

### 8.4 Data-governance and annotation decisions

| ID | Exact question | Options | Recommended option | Evidence/rationale | Owner | Blocks | Synthetic structural work independently? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GOV-JA-01 | Who may create, verify, approve, and amend runtime-to-reference mappings? | Same authorized actor; creator plus independent verifier; controlled registry workflow. | Creator/verifier separation where feasible, with role and amendment evidence. | Join errors can corrupt every paired result; structural fields alone cannot prove authority. | Data-governance/ethics owner | Real join production and use | Yes. |
| GOV-JA-02 | What source evidence may establish transaction identity without exposing personal data? | Capture-session mapping; approved de-identified transaction registry; manually adjudicated mapping; combinations. | Use the minimum approved de-identified source and record its lineage; no specific source is chosen here. | Equal filenames, hashes, or IDs are not authentication and raw receipt data are sensitive. | Data-governance owner | Real join production | Yes. |
| GOV-JA-03 | What authorization/access boundary applies to training, validation, and held-out join maps? | Common access; role-separated partition access; sealed held-out registry released once. | Role-separated access with held-out release only after readiness authorization. | Protocol forbids held-out access before full freeze and independent audit. | Data-governance/held-out custodian | Dataset use and held-out execution | Yes. |
| GOV-JA-04 | How are masked match labels created, independently checked/adjudicated, retained, and audited? | Single annotation; independent labels plus adjudication; another approved controlled workflow. | Predeclare masking and QA with independent evidence appropriate to the approved protocol; exact workflow remains open. | Protocol requires trained annotators and system masking but not its executable workflow. | Annotation/methodology/data-governance owners | Threshold development/freeze | Yes for schema. |

### 8.5 Leng-dependent proposed-method integration decisions

| ID | Exact question | Options | Recommended option | Evidence/rationale | Owner | Blocks | Synthetic structural work independently? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LNG-JA-01 | What immutable proposed-method prediction artifact supplies the scoped receipt, rows, final pre-review fields, configuration, output stage, and disposition? | Extend C1A through a separate adapter; new proposed-method offline bundle; another reviewed interface. | Provide a separate adapter into C1A while retaining B2-origin identities where the method contract guarantees them. | C1A documentation records this interface as pending; current repository has no completed selector/policy producer. | Leng with shared-contract review | Proposed-method receipt joining/alignment | Yes for B1/B2/B3 schemas. |
| LNG-JA-02 | How are B2 missing/unresolved/non-method-ready fields and rows represented in the proposed-method evaluation output? | Preserve original C1A states; provide explicit method outcome records; another reviewed mapping. | Preserve every emitted runtime identity/state and add no truth-dependent omission. | Missing/unresolved fields cannot disappear from evaluation; exact proposed output remains Leng-owned. | Leng | Proposed-method adapter and field links | Yes for baseline work. |
| LNG-JA-03 | Which configuration/freeze identifiers bind proposed-method output to scorer, calibration, policy, and receipt disposition? | One composite configuration ID; typed component references plus composite run ID. | Use immutable typed component references with one externally scoped configuration identity; exact design needs Leng/shared approval. | Protocol requires frozen pre-review decision/configuration before reference access. | Leng + shared methodology reviewer | Proposed-method join readiness and held-out audit | Yes for baseline work. |

## 9. Implementation roadmap after approvals

Each step below requires separate authorization. File names are proposals, not
permission to create them.

### 9.1 Receipt-join schema and validator

Authorization needed: **schema authorization**; synthetic-only. No methodology
algorithm or dataset authorization is needed for synthetic fixtures.

Prerequisites:

- approve SCH-JA-01 through SCH-JA-04;
- confirm join cardinality and coverage population; and
- approve provisional provenance/authorization/verification state fields.

Proposed files:

- `evaluation/receipt_join_schema.py`;
- `evaluation/receipt_join_validation.py`;
- `tests/test_evaluation_receipt_join.py`;
- `docs/evaluation_receipt_join_v0.md`; and
- `evaluation/__init__.py` for exports only.

Acceptance criteria:

- immutable, versioned join-set, entry, provenance, authorization, and evidence
  records;
- complete scope equality checks against supplied manifest and bundle;
- one-to-one joined cardinality and complete side coverage;
- exact partition/cohort intersection population and complete-scope collection
  identity checks;
- explicit reference-only/prediction-only behavior;
- outcome-specific association versus coverage/absence verification;
- auditable immutable revision lineage with no silent overwrite;
- no equality-based or source-string-based implicit join;
- structural versus alignment-ready validation separated;
- unverified/unauthorized records cannot become ready; and
- deterministic serialization with synthetic adversarial tests.

### 9.2 Alignment-link schema and validator

Authorization needed: **alignment-link schema authorization**; synthetic-only.
It does not require an approved matcher if match evidence remains externally
supplied and no algorithmic correctness is claimed.

Prerequisites:

- implemented receipt-join schema;
- approve SCH-JA-05 and SCH-JA-06; and
- approve the minimum matcher-configuration reference shape.

Proposed files:

- `evaluation/alignment_schema.py`;
- `evaluation/alignment_validation.py`;
- `tests/test_evaluation_alignment_links.py`;
- `docs/evaluation_alignment_links_v0.md`; and
- `evaluation/__init__.py` for exports only.

Acceptance criteria:

- matched/prediction-only/reference-only row outcomes;
- explicit receipt-join dependency;
- exact identity resolution and complete one-to-one row coverage for completed
  records;
- blocked-record reason, identity preservation, provenance, and prohibition on
  matcher-completion or metric claims;
- duplicate descriptions remain distinct;
- fallback/reference-only coverage without fabricated rows;
- matcher configuration and provenance consistency;
- incomplete/contradictory records rejected; and
- deterministic serialization that does not imply approved prediction order.

### 9.3 Deterministic matcher implementation

Authorization needed: **methodology authorization and schema authorization**;
synthetic conformance only initially.

Prerequisites:

- resolve TAI-JA-01 and MTH-JA-01 through MTH-JA-06;
- approve exact normalization, punctuation, distance, objective, order, missing
  state, and total tie-break specifications; and
- freeze a matcher-configuration schema and conformance corpus.

Proposed files:

- `evaluation/alignment.py`;
- `tests/test_evaluation_alignment.py`; and
- `docs/evaluation_alignment_algorithm_v0.md`.

Acceptance criteria:

- pure deterministic matching against immutable prediction/reference inputs;
- no threshold selection inside the matcher;
- exact-first, thresholded distance, monotonic, one-to-one, duplicate, missing,
  and total tie behavior exactly matches the approved specification;
- exact auditable evidence for every matched/unmatched outcome; and
- adversarial determinism/conformance tests.

### 9.4 Training-only threshold development

Authorization needed: **methodology authorization plus training-data and
annotation authorization**. Synthetic tests may precede data use, but actual
selection cannot.

Prerequisites:

- resolve MTH-JA-07, MTH-JA-08, and GOV-JA-04;
- approved/frozen training alignment subset and fitting-exclusion evidence;
- frozen comparator predictions and masked labelled matches; and
- approved finite grid, alignment-F1 definition, tie rule, and audit format.

Proposed files only after authorization:

- `evaluation/alignment_selection.py`;
- `tests/test_evaluation_alignment_selection.py`;
- `docs/evaluation_alignment_selection_v0.md`; and
- a separately controlled, versioned selection artifact location.

Acceptance criteria:

- reject non-training or non-subset records;
- reject missing/mismatched fitting-exclusion, masking, prediction, label, or
  comparator evidence;
- evaluate only the predeclared grid;
- apply the smaller-threshold F1 tie rule;
- serialize every candidate outcome and selected/no-estimate state; and
- produce freeze evidence without accessing validation or held-out outcomes.

### 9.5 Evaluation execution and audit integration

Authorization needed: **schema, methodology, dataset, freeze, and explicit
partition-specific execution authorization**. Held-out execution requires the
additional independent readiness gate.

Prerequisites:

- verified receipt joins;
- frozen matcher and threshold;
- finalized eligible references;
- frozen manifest, configurations, software, comparator/proposed artifacts,
  exclusion ledger, and verification evidence;
- Leng's proposed-method output interface for PantryProof comparisons; and
- data-governance authorization for the intended partition.

Proposed future boundaries:

- join/alignment integration in `evaluation/runner.py`;
- audit/result provenance records in separately approved evaluation modules;
- metric computation only under a distinct metric-task authorization.

Acceptance criteria:

- one authorized partition and cohort at a time;
- immutable prediction/reference inputs and complete identity coverage;
- no ground truth enters runtime prediction paths;
- unverified joins, unfrozen matchers, leakage, incomplete alignment, or
  unauthorized access block execution;
- fallback/missing/unmatched outcomes remain visible for later denominators;
  and
- held-out execution cannot start from structural validity alone.

## 10. Confirmed requirements and remaining blockers

Confirmed for subsequent schema design:

- runtime and reference identifiers are independent namespaces;
- complete prediction scope is required to identify a prediction receipt;
- manifest reference membership controls dataset/partition/cohort identity;
- actual receipt joins are explicit and offline;
- duplicate item descriptions preserve distinct row identities;
- all matched and unmatched rows in a successfully completed alignment must
  remain represented;
- one-to-one alignment prohibits split/merged matches;
- fallback and missing prediction receipts do not create fabricated rows;
- alignment development is training-only and excluded from fitting;
- source strings and digest strings are not authentication; and
- structural validity is not methodology, dataset, freeze, or held-out
  authorization.

Primary blockers before matcher implementation are the approved prediction
source-order meaning, executable normalization/punctuation profile, normalized
distance definition, global monotonic objective, complete tie behavior, and
missing/unresolved-description policy.

Primary blockers before real join or threshold use are data-governance-approved
mapping evidence, creator/verifier roles, partition access controls, masked
annotation workflow, actual dataset eligibility/finalization, and freeze
authority.

The smallest safe next implementation boundary is Section 9.1: a
synthetic-only receipt-join schema and validator after the shared schema owners
approve the coverage, cardinality, evidence, and readiness decisions. It must
not include row matching, threshold selection, metrics, or dataset access.

## 11. Explicit exclusions

This proposal does not implement or authorize:

- Python modules, tests, exports, or runtime changes;
- real receipt, label, mapping, or dataset access;
- automatic receipt-ID joins;
- source-image/hash comparison;
- a line matcher or output-order interpretation;
- normalization, edit distance, threshold grid, threshold fitting, or alignment
  F1;
- evaluation metrics or denominators;
- proposed-method adaptation;
- configuration or methodology freeze;
- validation or held-out execution; or
- ethics, consent, identity, provenance, digest, or authorization claims.

Independent review and explicit approval are required before any roadmap step
begins.
