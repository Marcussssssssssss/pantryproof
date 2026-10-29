# PantryProof Proposed-Method Decision Log

Registry preparation status: `PREPARED_AWAITING_INDEPENDENT_REVIEW_AND_INTEGRATION`

Recorded development status: `PROVISIONAL_DEVELOPMENT`

Implementation status: `IMPLEMENTATION_NOT_YET_AUTHORIZED_OR_ACCEPTED`

Evaluation status: `NOT_EVALUATION_FROZEN`

## 1. Purpose, scope and authority

This document is the proposed append-only decision registry for the bounded
PantryProof proposed-method decisions recorded below. It is intended to become
canonical for those decisions only after independent review and authorized Git
integration. Preparation of this untracked document does not itself make the
registry canonical, independently reviewed or integrated.

The registry records supplied conversational approval evidence at its actual
strength. Its authority is limited to the stated proposed-method methodology,
the bounded G2A implementation scope, B3 compatibility conditions and the
specific shared evidence-reference semantics jointly approved below.

This registry does not replace, modify or expand the authority of
`docs/evaluation_decision_log.md`. The evaluation log remains outside this
registry's authority. Conversely, the evaluation log does not grant authority
over Leng's proposed-method decisions or shared runtime contracts.

This registry does not authorize:

- changes to B2 or B3;
- changes to Contract V0, Contract V1 or Contract V2;
- package-export, controller, Android or persistence integration;
- candidate selection, scoring, calibration or review routing;
- source-code implementation without a separate task;
- staging, committing, pushing, merging or other Git mutation;
- real-receipt, validation or held-out execution; or
- methodology, configuration, implementation or evaluation freeze.

## 2. Repository foundations

The governance and development references are intentionally distinct:

| Reference purpose | Recorded checkpoint |
|---|---|
| Documentation-governance foundation | `main@3d64793b04ecf7ab35ed997a99f107308ca32b67` |
| G2A development checkpoint | `feature/self-correction@99f5ca433e3ca08e3d1f3f16f65af0dadf36ba28` |
| Protected shared project foundation | `36e6cef0a32aa98d56b21373e2078d7c1fbb1f71` |

The file was prepared in the feature checkout. That fact does not make the
feature checkout a descendant of the remote documentation foundation. No
ancestry or integration relationship between the two checkpoints is inferred
by this document.

During G2A-OWNER-05R2, the documentation-foundation commit was unavailable in
the local object database. No fetch or branch switch was performed. The
recorded documentation checkpoint is retained; local source inspection and
ancestry verification against that commit could not be performed. This is
separate from the source-fidelity corrections to this unintegrated draft.

## 3. Approval evidence and attribution conventions

The evidence consists of excerpts and messages supplied in the FYP project
conversation. No immutable conversation-message IDs, independently
authenticated identities, cryptographic signatures or independently verified
original timestamps are asserted.

Evidence classifications used here are:

- **Direct owner statement**: wording supplied as the owner's own response.
- **Proposal approved by reference**: the complete proposal and the subsequent
  owner instruction approving it are both preserved.
- **Attributed owner message**: a message supplied by the user and attributed
  to another named owner, without independent authentication.
- **Assistant-authored proposal**: proposal text only; it becomes approved only
  where a preserved owner statement expressly approves it by reference.
- **Historical reaffirmation**: a current dated confirmation that does not
  invent or backdate the missing original timestamp.

An approver's supplied name and capacity record the conversational attribution.
They are not proof of identity, independence or signature. Git commits, blobs,
hashes, ruleset IDs and populated provenance fields identify development
context; they are not approval evidence or evaluation-freeze authentication.

For a proposal approved by reference, this registry preserves both the exact
proposal and the approving owner statement. A summary alone is not substituted
for exact evidence.

## 4. Append-only history and decision identifiers

Decision history is append-only at the logical-record level:

1. Existing decision text, attribution, evidence strength, date or authorization
   boundary must not be silently rewritten.
2. Corrections require a new amendment record with its own identifier, date,
   source, reason and predecessor reference.
3. A replacement requires a new supersession record identifying the earlier
   decision and the exact clauses retained or replaced.
4. Earlier records remain visible after amendment or supersession.
5. Conflicting active successors fail closed pending explicit owner resolution.
6. Missing or unauthenticated evidence must not be upgraded by inference.

Decision IDs such as `G2A-LNG-03` identify methodology decisions. Approval
envelope IDs use the registry-local `PM-APP` namespace. Envelope IDs are local
administrative keys, not signatures, message IDs or authentication evidence.

The following decision statuses apply:

- `PROPOSED`: recorded for consideration but not owner-approved.
- `APPROVED`: approved by the named owner within the recorded boundary.
- `PENDING`: a stated approval or provenance requirement remains unresolved.
- `AMENDED`: a later identified record changes part of the earlier decision.
- `SUPERSEDED`: a later identified record replaces the earlier decision for
  future work while preserving its history.
- `REJECTED`: explicitly rejected by the applicable owner.

Design approval, implementation authorization, implementation acceptance and
evaluation freeze are independent states. Every envelope below remains
`IMPLEMENTATION_NOT_YET_AUTHORIZED_OR_ACCEPTED` and `NOT_EVALUATION_FROZEN`.

## 5. Named owners and capacities

| Person | Supplied approval capacity | Boundary |
|---|---|---|
| Leng Wei Heng | Proposed-method methodology and bounded implementation owner | Proposed-method methodology, identifiers, G2A scope and registry governance |
| Leng Wei Heng | Proposed-method/shared-interface owner | Proposed-method side of `G2A-SHARED-01` only |
| Tai Yong Xin | B2/B3 implementation and compatibility owner | B3 parser compatibility Q1-Q6 |
| Tai Yong Xin | B2/B3 and shared-interface compatibility owner | Compatibility side of `G2A-SHARED-01` only |

These capacities are supplied conversational attributions. They do not imply
independent reviewers or authority beyond the recorded decision boundary.

## 6. Source-evidence register S1-S8

| Source | Classification | Decisions/evidence |
|---|---|---|
| S1 | Direct owner statement | Original G2A methodology approval; `G2A-LNG-01`, `G2A-LNG-02` |
| S2-A | Preserved owner-approval proposal | Exact `G2A-LNG-03`, `G2A-LNG-04`, `G2A-LNG-06` terms and historical-provenance status |
| S2-B | Direct owner approval by reference | Approval instruction for the immediately preceding recommended proposal |
| S2-C | Assistant-authored proposal approved by reference | Deterministic reason-detail strings referenced by S2-A and approved through S2-B |
| S2-D | Earlier user-supplied proposal | Exact `G2A-LNG-02` and `G2A-LNG-05` proposal text |
| S3 | Historical reaffirmation | Dated `G2A-LNG-01` reaffirmation |
| S4 | Direct owner statement | `G2A-GOV-01` |
| S5 | Direct owner approval by reference | Leng response to `G2A-SHARED-01` |
| S6 | User-supplied message attributed to Tai | B3 compatibility Q1-Q6 |
| S7 | User-supplied message attributed to Tai | Tai response to `G2A-SHARED-01` |
| S8 | Direct owner statement with complete proposal | `G2A-LNG-05` |

S1 original statement:

> I approve the proposed grammar-aware PURCHASE_DATE_CALENDAR_VALIDITY_V0 methodology. Prepare the isolated G2A Codex implementation prompt, respecting the pending Tai compatibility confirmation and no Git actions.

S2-B subsequent owner instruction:

> For the recommended approval question, approve it. For those in pending, provide guidelines or suggestions for it.

S3 dated owner-level reaffirmation:

> G2A-LNG-01 is now established in this conversation as an owner-level reaffirmation dated **29 October 2026**, without backdating or claiming recovery of the original timestamp.
>
> Implementation remains blocked because:
>
> - Tai’s six-part B3 parser compatibility confirmation is still missing.
> - Historical timestamp remains `HISTORICAL_TIMESTAMP_UNVERIFIED`.
> - Canonical decision-log registration and independent owner attribution remain outstanding.
> - Separate implementation authorization is still required.
>
> No repository files or Git state were changed. Current verdict remains **BLOCKED_PENDING_TAI_COMPATIBILITY_CONFIRMATION**.

The Tai-compatibility statement in S3 records status at that earlier time. S6
contains the later attributed Q1-Q6 approvals. The historical timestamp remains
unverified.

## 7. Leng main approval envelope

### 7.1 Envelope metadata

| Field | Recorded value |
|---|---|
| Approval-envelope ID | `PM-APP-2026-10-29-G2A-LNG-01` |
| Decisions | `G2A-LNG-01`, `G2A-LNG-02`, `G2A-LNG-03`, `G2A-LNG-04`, `G2A-LNG-06` |
| Named approver | Leng Wei Heng |
| Capacity | Proposed-method methodology and bounded implementation owner |
| Reaffirmation date | `2026-10-29`, explicitly stated in S3 |
| S2 package approval date | Not established by the supplied S2-B owner statement; S2-A proposes a conditional date only |
| Evidence strength | Direct conversational statement and proposal approved by reference |
| Design status | `APPROVED` within the clauses below |
| Implementation status | `IMPLEMENTATION_NOT_YET_AUTHORIZED_OR_ACCEPTED` |
| Evaluation status | `NOT_EVALUATION_FROZEN` |
| Independent review | Required; not recorded as completed |

S2-A identified Leng Wei Heng as the named approver in the capacity of
proposed-method methodology and bounded implementation owner. It proposed an
approval date of 29 October 2026 if actually confirmed on that date. S2-B
supplies the approving instruction but does not state its date. It does not
establish that the conditional date was met. The envelope ID is an
administrative identifier and does not prove an original owner approval date.

The following Response fields reproduce the wording of the available S2-A proposal questionnaire. They do not independently prove owner approval; the approving owner instruction is S2-B.

S2-A's exact implementation boundary is:

> These decisions approve the stated methodology, identifiers and proposed file boundary within the owner's authority.
>
> They do not authorize coding, staging, committing, pushing or merging until the decisions are registered, independently reviewed and a separate implementation task is authorized.
>
> **Evaluation status:** `PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`.

### 7.2 `G2A-LNG-01` - original approval and dated reaffirmation

Status: `APPROVED` prospectively, with historical provenance limitation.

The exact original statement is S1, reproduced in Section 6. The original
historical approval timestamp is:

`HISTORICAL_TIMESTAMP_UNVERIFIED`

S2-A also recorded:

> **Response: PENDING**
>
> The original methodology approval is acknowledged, but its historical timestamp and independent provenance verification remain pending. Do not backdate the decision.

The separate owner-level reaffirmation is S3, reproduced in Section 6, with
date `2026-10-29`. The reaffirmation does not recover, replace or backdate the
unknown original timestamp.

The bounded reaffirmed rule is that the grammar-aware
`PURCHASE_DATE_CALENDAR_VALIDITY_V0` methodology remains active with the
approved `PASS`, `FAIL`, `UNAVAILABLE` and typed-error semantics. It is limited
to purchase-date hard-constraint evaluation and does not authorize downstream
controller or evaluation activity.

Outstanding requirements are independent review, authorized registry
integration and separate synthetic implementation authorization.

### 7.3 `G2A-LNG-02` - grammar-aware outcome methodology

Status: `APPROVED` by reference through S1, using the preserved S2-D proposal.

Exact approved proposal:

| Condition | Outcome |
|---|---|
| Exactly one distinct valid interpretation under approved grammar | PASS |
| Recognized approved grammar, all permitted interpretations impossible | FAIL |
| Multiple distinct valid interpretations | UNAVAILABLE |
| Unsupported grammar | UNAVAILABLE |
| Malformed literal | UNAVAILABLE |
| Configuration or integrity failure | Typed error; no rule outcome |
| Unexpected evaluator failure | Typed error; no fabricated outcome |

The purchase-date-specific evaluator never emits `NOT_APPLICABLE`.

Transcription baseline: the shorter table and sentence above reproduce the
earlier available S2-D packet from G2A-OWNER-04R. Later expanded explanations
are secondary editorial material. No fuller original proposal is claimed to
have been recovered or reconstructed.

Editorial clarification from the G2A-OWNER-05R2 instruction: under supported
grammar, one distinct calendar-valid interpretation permits PASS; recognized
grammar with every permitted interpretation calendar-invalid permits FAIL.
Unsupported grammar or malformed representations remain UNAVAILABLE rather
than being treated as recognized calendar-impossible dates. B3 INVALID alone
is insufficient to establish G2A FAIL. Configuration, integrity and unexpected
execution failures produce typed errors rather than rule outcomes. These
clarifications preserve the existing policy; they are not presented as newly
recovered verbatim S2-D evidence or as a new owner approval.

The approval is bounded to the verified grammar-aware rule. It does not invent
date windows, locale preference, thresholds or downstream policy.

### 7.4 `G2A-LNG-03` - attempt, evidence and reason semantics

Status: `APPROVED` by reference through S2-A and S2-B.

S2-A recorded:

> **Response: APPROVE**
>
> Approve the exact proposed mapping:

Exact approved mapping:

| Condition | Attempted | Evidence availability | Reason kind | Reason code |
|---|---:|---|---|---|
| PASS | true | AVAILABLE | null | null |
| FAIL | true | AVAILABLE | FAILURE | CALENDAR_DATE_IMPOSSIBLE |
| Ambiguous UNAVAILABLE | true | UNAVAILABLE | UNAVAILABILITY | AMBIGUOUS_DATE_INTERPRETATION |
| Unsupported/malformed UNAVAILABLE | true | UNAVAILABLE | UNAVAILABILITY | DATE_FORMAT_UNSUPPORTED |

Exact deterministic reason details approved by reference:

- PASS: `null`
- FAIL: `All interpretations permitted by the approved purchase-date grammar are calendar-invalid.`
- Ambiguous: `Multiple distinct calendar-valid interpretations; no unique date established.`
- Unsupported/malformed: `Candidate literal does not match the approved purchase-date grammar.`

S2-A further recorded:

> Approve the deterministic reason details specified in the G2A owner-confirmation proposal.
>
> Use one evidence reference with namespace `CANDIDATE_RECORD_V1`, the exact candidate ID and actual candidate record version.
>
> The literal remains present even when calendar-validity evidence is insufficient. Configuration, integrity and unexpected execution failures must produce typed errors rather than fabricated outcomes.

The approving owner statement is S2-B, reproduced in Section 6. S2-C is
assistant-authored proposal text, not an independent approval; it is effective
only because S2-A expressly referenced those reason strings and S2-B approved
the proposed approval package.

### 7.5 `G2A-LNG-04` - identifiers and configuration

Status: `APPROVED` by reference through S2-A and S2-B.

S2-A recorded:

> **Response: APPROVE**
>
> Approve these identifiers:

Exact approved identifiers and settings:

- Rule ID: `PURCHASE_DATE_CALENDAR_VALIDITY_V0`
- Rule version: `v0`
- Grammar reference: `PURCHASE_DATE_GRAMMAR_V0`
- Profile ID: `purchase-date-calendar-validity-profile-v0`
- Profile version: `v0`
- Applicability reference: `PURCHASE_DATE_ONLY_V0`
- Evidence namespace: `CANDIDATE_RECORD_V1`
- One mandatory rule at position `0`
- No external resources
- Exact live D3 `Theta_A` configuration binding

The rule applies only to `PURCHASE_DATE`.

The approved grammar mirror must remain version-bound to the verified B3 parser
behavior. No hashes or authentication claims may be fabricated.

The rule ID/version, grammar reference, profile ID/version and applicability
reference are component-local proposed-method identifiers. The evidence
namespace has the separately approved shared semantics in Section 11. Existing
`Theta_A` and source-binding contracts are consumed unchanged.

#### B3 verified source dependency reference

This engineering dependency reference is reproducibility metadata added during
the bounded G2A-OWNER-05R1 documentation correction. It is separate from, and
does not alter, the verbatim owner approval statements above.

- Module: `pipeline/baseline_b3.py`
- Ruleset: `B3-generic-rules-v0`
- Git source blob: `73a929fe68c5459ea20c944069bf2cb05e86982a`
- Verification context: G2A0 read-only parser inspection against
  `feature/self-correction@99f5ca4`

The source identity is reproducibility metadata, not source authentication or
evaluation-freeze approval. No Python/Unicode runtime version is claimed frozen.
Actual runtime compatibility must be recorded and tested during a
separately authorized synthetic implementation.

Any B3 source or relevant runtime behavior change requires conformance
revalidation before adoption, consistent with Tai's Q3–Q6 conditions.

### 7.6 `G2A-LNG-06` - bounded implementation file scope

Status: `APPROVED` by reference through S2-A and S2-B.

S2-A recorded:

> **Response: APPROVE**
>
> Authorize the following as the proposed file allowlist for a subsequent, separately authorized synthetic-only implementation task:

1. `pipeline/proposed/purchase_date_calendar_validity.py`
2. `tests/test_proposed_purchase_date_calendar_validity.py`
3. `docs/proposed_purchase_date_calendar_validity_v0.md`

S2-A's exact exclusion is:

> No changes to existing files, package exports, B2/B3, Contract V0/V1/V2, controller, candidate generation, Android, persistence, scoring, calibration or evaluation.

This does not authorize implementation in the present documentation task.

An earlier unexecuted task proposed these different filenames. Their source
is Section 3 of the user-supplied Task 2.5G2A attachment
(`027e2d3d-77d6-4c21-8f73-5818e9022eea/Pasted text.txt`), available for
read-only comparison during this correction. This is conversational task
provenance, not an independently authenticated earlier approval:

1. `pipeline/proposed/hard_constraint_date_rule.py`
2. `tests/test_proposed_hard_constraint_date_rule.py`
3. `docs/proposed_hard_constraint_date_rule_v0.md`

Those earlier names are `SUPERSEDED` for the prospective implementation scope
by the current S2-approved allowlist. No implementation exists under either
allowlist as a result of this registry preparation.

## 8. Leng `G2A-LNG-05` approval envelope

### 8.1 Envelope metadata

| Field | Recorded value |
|---|---|
| Approval-envelope ID | `PM-APP-2026-10-29-G2A-LNG-05-01` |
| Decision | `G2A-LNG-05` |
| Named approver | Leng Wei Heng |
| Capacity | Proposed-method methodology and bounded implementation owner |
| Supplied approval date | `2026-10-29` |
| Source | S8 direct owner statement |
| Evidence strength | Supplied conversation approval; not independently authenticated |
| Design status | `APPROVED` |
| Implementation status | `IMPLEMENTATION_NOT_YET_AUTHORIZED_OR_ACCEPTED` |
| Evaluation status | `NOT_EVALUATION_FROZEN` |

### 8.2 Exact owner statement

> I, Leng Wei Heng, APPROVE G2A-LNG-05 exactly as proposed, in my capacity as proposed-method methodology and bounded implementation owner, dated 29 October 2026. This confirms the G1/V2 aggregation boundary only. No coding, Git changes, shared-contract migration or held-out evaluation are authorized.

### 8.3 Exact approved proposal

The G2A evaluator produces one `ConstraintRuleOutcomeV2` for one exact retained
D3 purchase-date candidate under the applicable approved rule.

That outcome is incorporated only through existing source-bound G1/V2 audit and
aggregation interfaces.

G2A must not:

- Replace permanent `c0`.
- Select a candidate.
- Change existing hard-constraint aggregation or eligibility policy.
- Determine field-wide commitment.
- Route controller outcomes.
- Change persistence.
- Bypass complete rule-profile validation.
- Imply any shared Contract V2 migration.

Existing source-binding and Theta_A validation requirements remain mandatory.

This decision resolves the sole approval-linkage gap identified in the
G2A-OWNER-04R evidence review. It does not authorize implementation.

## 9. Registry-governance approval envelope

### 9.1 Envelope metadata

| Field | Recorded value |
|---|---|
| Approval-envelope ID | `PM-APP-2026-10-29-G2A-GOV-01` |
| Decision | `G2A-GOV-01` |
| Named approver | Leng Wei Heng |
| Capacity | Proposed-method owner |
| Approval date attribution | Not established by the exact S4 owner statement; the packet attributes `2026-10-29` to a subsequent conversation record, not to the statement itself |
| Source | S4 direct owner statement; date attribution remains separately limited |
| Evidence strength | Supplied conversation approval; not independently authenticated |
| Status | `APPROVED` |

### 9.2 Exact approval statement

> I approve G2A-GOV-01 Option A at the Leng proposed-method owner level: establish docs/proposed_method_decision_log.md as the separate append-only proposed-method decision registry, with PM-APP identifiers scoped locally. No shared-contract authority, coding, or Git changes are authorized by this approval.

This decision establishes the intended separate registry. The later
G2A-OWNER-05 authorization permits preparation of this one document only; it
does not retrospectively expand `G2A-GOV-01` and does not independently accept
or integrate the prepared registry.

The administrative date in the PM-APP envelope ID does not establish the
owner's original approval date. S4's exact owner statement is preserved without
inserting a date into it.

## 10. Tai B3 compatibility approval envelope

### 10.1 Envelope metadata

| Field | Recorded value |
|---|---|
| Approval-envelope ID | `PM-APP-2026-10-29-G2A-TAI-01` |
| Decisions | B3 compatibility Q1-Q6, preserved individually |
| Named approver | Tai Yong Xin |
| Capacity | B2/B3 implementation and compatibility owner |
| Supplied approval date | `2026-10-29` |
| Evidence source | S6 user-supplied message attributed to Tai |
| Evidence strength | Attributed conversational approval; not independently authenticated |
| Status | `APPROVED` with the conditions below |
| Implementation status | `IMPLEMENTATION_NOT_YET_AUTHORIZED_OR_ACCEPTED` |
| Evaluation status | `NOT_EVALUATION_FROZEN` |

### 10.2 Exact supplied message and individual decisions

> Hi Leng, I've reviewed all six B3 compatibility questions. My responses are below.

**Q1: APPROVE**

Conditions:

- You may reuse `parse_generic_date()`, `DateParseResult`, and `B3ParseState` as the existing B3 public parser interface.
- The approval applies to the verified `B3-generic-rules-v0` implementation.
- The interface is version-bound, not guaranteed to remain unchanged in future versions.

**Q2: APPROVE**

Conditions:

- You may import `pipeline.baseline_b3` directly from your proposed-method module.
- The existing proposed-method adapter already imports B3, so this is consistent with the current dependency structure.
- Your implementation must not introduce circular imports, invoke B2/B3 extraction again, or modify their existing behavior.
- Include an import compatibility test.

**Q3: APPROVE**

Conditions:

- You may use the stated B3 ruleset and Git blob as your reproducibility reference.
- Bind your compatibility tests to the exact verified source version and relevant Python/Unicode behavior.
- The Git blob identifies the source version; it does not independently authenticate an evaluation freeze.
- Future B3 updates require compatibility revalidation before adoption.

**Q4: APPROVE**

Conditions:

- You may implement a separately versioned syntax recognizer that mirrors B3's supported date grammar.
- Use B3's public parser for calendar interpretations.
- Do not import private B3 regex constants or modify B3 source code.
- Preserve the supported normalization, Unicode digit, whitespace, separator, and month-name matching behavior.
- B3 `INVALID` must not map directly to G2A `FAIL`. Only recognized grammar with no valid calendar interpretation may produce that outcome.
- Unsupported or malformed formats must remain distinguishable.

**Q5: APPROVE**

Conditions:

- You may create synthetic conformance tests in your own proposed-method test file.
- Cover valid, invalid, ambiguous, unsupported, Unicode, and boundary cases.
- Do not modify existing B3 tests.
- Any mismatch between the mirrored recognizer and the approved B3 grammar must fail compatibility verification rather than silently changing behavior.

**Q6: APPROVE**

Conditions:

- You may continue developing against the verified B3 version.
- I can continue maintaining B2/B3 independently.
- If B3's public parser, grammar, or relevant dependency behavior changes, you must rerun compatibility tests and explicitly review the differences before adopting the new version.
- Any incompatible shared-interface change requires separate coordination and approval.

**Confirmation details**

- **Name:** Tai Yong Xin
- **Role:** B2/B3 implementation and compatibility owner
- **Date:** 29 October 2026
- **Decision:** APPROVE Q1–Q6 with the conditions above.

These approvals concern B3 interface compatibility only. They do not authorize
changes to B2/B3, existing shared contracts, controller behavior, evaluation
methodology, or held-out evaluation.

> Your G2A methodology decisions, evidence mappings, implementation scope, and coding authorization remain subject to their respective approval and decision-log gates.

## 11. Joint shared-namespace approval envelope

### 11.1 Envelope metadata

| Field | Recorded value |
|---|---|
| Approval-envelope ID | `PM-APP-2026-10-29-G2A-SHARED-01` |
| Decision | `G2A-SHARED-01` |
| Namespace | `CANDIDATE_RECORD_V1` |
| Leng capacity | Proposed-method/shared-interface owner |
| Tai capacity | B2/B3 and shared-interface compatibility owner |
| Supplied approval dates | `2026-10-29` for both owners |
| Evidence sources | S5 direct approval by reference; S7 attributed Tai message |
| Evidence strength | Supplied conversational approvals; not independently authenticated |
| Status | `APPROVED` within the exact structural semantics below |
| Contract migration | Not authorized or required by this decision |

### 11.2 Exact shared proposal approved by Leng

`CANDIDATE_RECORD_V1` identifies a structural evidence reference to an existing `CandidateRecordV1`.

- `reference_id` equals the referenced candidate's actual `candidate_id`.
- `source_record_version` equals its actual `record_version`.
- It does not independently authenticate Python object identity, source bytes, provenance or evaluator execution.
- Exact live D3 candidate and permanent c0 identity must be independently verified.
- No existing Contract V1/V2, B2/B3 or shared interface modification is requested.

### 11.3 Exact Leng owner response

> I, Leng Wei Heng, APPROVE G2A-SHARED-01 at the proposed-method/shared-interface owner level on 29 October 2026. I approve the exact CANDIDATE_RECORD_V1 structural reference semantics stated above, with no authentication, identity-proof, coding, or Git authorization implied. Tai's separate approval remains required.

### 11.4 Exact Tai supplied response

> Hi Leng, I've reviewed the proposed shared evidence namespace.
>
> **Decision ID:** G2A-SHARED-01
>
> **Response:** APPROVE
>
> **Exact approved rule:**

Approve `CANDIDATE_RECORD_V1` as a structural evidence-reference namespace for
an existing `CandidateRecordV1`.

The following semantics apply:

1. `reference_namespace` must equal `CANDIDATE_RECORD_V1`.
2. `reference_id` must equal the referenced candidate's actual `candidate_id`.
3. `source_record_version` must equal the referenced candidate's actual `record_version`.
4. The reference is a structural pointer only. It does not independently authenticate Python object identity, source bytes, provenance, or evaluator execution.
5. Exact live D3 candidate and permanent `c0` identity must be validated through the existing source-binding and V2 factory mechanisms. G2A must not treat the evidence reference alone as proof of identity.
6. No modifications to existing Contract V1/V2, B2/B3, or shared interfaces are authorized by this decision.

- **Named approver:** Tai Yong Xin
- **Approval capacity:** B2/B3 and shared-interface compatibility owner
- **Approval date:** 29 October 2026

**Conditions:**

- The namespace must be used only for exact existing candidate-record references.
- No fabricated candidate IDs, record versions, or evidence references.
- G2A must preserve permanent B2 `c0` and existing D3 candidate identities.
- The implementation must use existing source-binding validation rather than introduce an alternative identity-verification mechanism.
- Synthetic tests must verify correct references and reject mismatched candidate IDs or versions at the appropriate validation boundary.
- This approval concerns shared evidence-reference semantics only. It does not authorize Contract V2 modifications, downstream orchestration, real-data evaluation, or held-out execution.
- Register this decision in the canonical approval log before relying on it for implementation.

Tai's exact closing decision is:

> **Decision:** APPROVE with the conditions above.

### 11.5 Shared-semantics conclusion and limitations

The separate Leng and Tai approvals agree that the namespace is a structural
reference only. The namespace does not authenticate the referenced record,
source bytes, Python object identity, provenance or actual evaluator execution.
Exact live D3 candidate and permanent `c0` identity remain subject to the
existing source-binding and Contract V2 factory mechanisms.

The existing Contract V2 namespace field can represent the approved uppercase
identifier. This decision establishes its bounded semantic meaning without
modifying Contract V1, Contract V2, B2, B3 or any shared interface.

## 12. Authorization and lifecycle state

| State dimension | Recorded state |
|---|---|
| Decision evidence | Approved only as supported by S1-S8 and the exact boundaries above |
| Registry document | Prepared; awaiting independent review and authorized integration |
| Registry canonical status | Not yet canonical in Git |
| Synthetic G2A implementation | Not separately authorized |
| Implementation acceptance | Not granted |
| Shared-contract migration | Not authorized |
| B2/B3 modification | Not authorized |
| Controller/Android/persistence integration | Not authorized |
| Real-data or held-out execution | Not authorized |
| Evaluation status | `PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN` |

This documentation preparation does not authorize the three-file G2A
implementation. A separate task must authorize implementation after this
registry is independently reviewed and integrated through an authorized Git
workflow.

## 13. Known evidence limitations and outstanding gates

1. The original historical methodology timestamp remains
   `HISTORICAL_TIMESTAMP_UNVERIFIED`.
2. S1-S8 are supplied conversational evidence, not authenticated signatures or
   independently verified identities.
3. No immutable conversation-message ID is available or invented.
4. The registry has not yet received independent review.
5. The registry has not been staged, committed, merged or otherwise integrated.
6. No synthetic implementation authorization or implementation acceptance is
   recorded.
7. Source-version Git blobs and hashes remain provenance metadata, not
   authenticated evaluation-freeze evidence.
8. Real-data, validation and held-out execution remain prohibited.
9. Earlier and later assistant-prepared evidence packets used different S2-A
   labels and S2-D wording. Under G2A-OWNER-05R3 source precedence, this registry
   uses the earlier available G2A-OWNER-04R packet for exact transcription.
   Later expanded explanations are editorial clarifications, not new owner
   approvals or authenticated original text. The original conversational source
   beyond the supplied packets has not been independently authenticated.
   These packet differences do not constitute a contradiction between Leng
   and Tai. No absent original wording has been reconstructed.

## 14. Independent-review requirements

An independent reviewer should verify that:

1. every exact proposal and owner statement matches S1-S8;
2. assistant-authored S2-C text is identified as proposal text approved by
   reference rather than independent owner evidence;
3. the historical timestamp and dated reaffirmation remain distinct;
4. all decision IDs and envelope IDs are unique;
5. Q1-Q6 remain separate and every Tai condition is preserved;
6. both `G2A-SHARED-01` approvals and all seven Tai conditions remain visible;
7. S8 is the explicit approval source for `G2A-LNG-05`;
8. the S2-approved three-file allowlist is current and the earlier names are
   explicitly superseded;
9. no approval is expanded into coding, integration, evaluation or freeze;
10. the evaluation decision log remains outside this registry's authority;
11. append-only amendment and supersession rules are internally consistent; and
12. the repository and documentation foundations are recorded as distinct
    checkpoints without invented ancestry or integration claims.

Only after that review may a separately authorized Git-integration task make
this registry canonical for the bounded decisions recorded here.
