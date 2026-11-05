# Receipt Presentation V1 — Shared Decision Register

`DRAFT_NOT_APPROVED — SYNTHETIC_ONLY`

**Milestone:** TAI-LENG-M3D-0  
**Owners:** Tai Yong Xin and Leng Wei Heng  
**Date:** 2026-11-04  
**Current state:** `M3D_FULL_CONTRACT_APPROVAL_PENDING`  
**Recorded shared decision:** `S06_SHARED_OWNER_DESIGN_AGREED`

This register contains only decisions that affect the proposed synthetic
`receipt-presentation-v1` contract. It is not an implementation authorization
and does not reopen protected methodology or evaluation decisions.

## 1. Tai consolidated review

Tai's review should record one consolidated disposition against the following
Android boundary:

| ID | Android approval point | Draft position | Status |
|---|---|---|---|
| T-01 | API 26 DTO/parsing feasibility | JSON contains only platform-neutral primitives; money/date/quantity remain strings until validation | Pending Tai review |
| T-02 | Incomplete automatic fields | Use a new immutable automatic presentation model; do not force missing/unresolved data into current typed `Receipt` | Pending Tai review |
| T-03 | Manual Review mapping | Derive a separate editable string draft; retain automatic IDs, values, statuses, reasons, token references, and producer/source metadata unchanged | Pending Tai review |
| T-04 | Source labeling and demo isolation | `LOCAL_IMAGE` processing and fixture data never fall back to mock fields; existing synthetic demo stays outside this envelope | Pending Tai review |
| T-05 | Unit-price optionality | `UNIT_PRICE/MISSING` initializes a blank optional field and remains nonblocking; `UNRESOLVED` remains visibly unresolved | Pending Tai review |
| T-06 | Quantity/inventory separation | Preserve positive decimal receipt quantity without rounding; do not alter or automatically feed the existing integer inventory model | Pending Tai review |
| T-07 | Failure/version behavior | Reject unsupported schema/enum/role states before UI mapping; map stable failure codes to localized safe text | Pending Tai review |

**Tai consolidated disposition:** `PENDING`

Suggested recorded values after review: `APPROVE_DRAFT`,
`APPROVE_WITH_LISTED_CHANGES`, or `REJECT_WITH_REASON`.

## 2. Leng consolidated review

Leng's review should record one consolidated disposition against the following
backend boundary:

| ID | Backend approval point | Draft position | Status |
|---|---|---|---|
| L-01 | Contract V0 projection | Preserve exact seven roles, field statuses, original values, reasons, native confidence, identities, gate decision, extraction status, and pre-review stage | Pending Leng review |
| L-02 | Python serialization feasibility | Produce the proposed shape deterministically without changing B1/B2/B3 semantics or using proposed/evaluation serializers | Pending Leng review |
| L-03 | Stable identities | Receipt, image, gate, row, field, and token IDs remain stable and internally referential for one automatic result | Pending Leng review |
| L-04 | Token provenance | Emit an ordered token-ID registry sufficient to validate field references while omitting OCR text and geometry | Pending Leng review |
| L-05 | Original/canonical values | Retain exact `StructuredField.value` and emit a separately traceable canonical presentation value without correction claims | Pending Leng review |
| L-06 | Gate/source metadata | Project a recorded gate only when it exists; do not invent a new Contract V0 decision; redact paths/URIs from provenance | Pending Leng review |
| L-07 | Producer/failure metadata | Supply opaque producer/version metadata and later map orchestrator failures into the approved outer taxonomy | Pending Leng review |

**Leng consolidated disposition:** `PENDING`

Suggested recorded values after review: `APPROVE_DRAFT`,
`APPROVE_WITH_LISTED_CHANGES`, or `REJECT_WITH_REASON`.

## 3. Shared approval points

The following decisions require one joint outcome. They are phrased as concrete
choices rather than separate questionnaires for each owner.

| ID | Decision | Draft recommendation | Why joint approval is required | Status |
|---|---|---|---|---|
| S-01 | Exact value representation | Keep both immutable `originalAutomaticValue` and canonical `presentationValue` | Current backend money may retain currency/grouping text; Android needs decimal strings without losing the original | Pending |
| S-02 | Canonical value grammar | Money: non-negative plain decimal with exactly two fractional digits. Date: valid ISO `YYYY-MM-DD`. Quantity: positive plain decimal with no exponent/rounding; jointly set maximum scale | Contract V0 uses strings and does not freeze these transport grammars | Pending |
| S-03 | Array ordering | Make JSON array order normative; exact receipt/item role order; item row array order is source order; no redundant row index | Contract V0 preserves tuple order but does not define a JSON ordering field | Pending |
| S-04 | Identity/reference grammar | Use nonblank opaque ASCII tokens without slash, backslash, URI scheme, drive prefix, or whitespace | Android needs correlation while backend must avoid leaking machine-local references | Pending |
| S-05 | Source type and digest | Allow `LOCAL_IMAGE`; reserve `SYNTHETIC_FIXTURE` for tests only; keep SHA-256 nullable until privacy review | Digest linkability and fixture/live separation cross both ownership boundaries | Pending |
| S-06 | Gate absence and failure taxonomy | Four terminal outcomes; all four Contract V0 evidence statuses are conditionally permitted for genuine available and insufficient-evidence results; the narrower agreed technical-failure matrix remains; post-insufficient presentation failure is deferred outside V1 JSON conformance | Contract V0 defines recorded decisions, not product lifecycle/failure states | `S06_SHARED_OWNER_DESIGN_AGREED` |
| S-07 | Unknown JSON members | Choose fail-closed rejection within schema V1, or explicitly approve ignore-unknown additive evolution; duplicate keys always reject | Parser and serializer must implement the same compatibility policy | Pending |
| S-08 | Extraction-status consistency | Decide whether the presentation validator merely preserves Contract V0 status or recomputes B1/B2 completeness consistency | `ReceiptOutput` accepts the enum but does not enforce the B1/B2 derivation | Pending |
| S-09 | Missing/unresolved evidence | Permit empty or resolvable token references for both statuses; require a nonblank reason; decide whether reasons remain free text or gain versioned codes | Contract V0 permits token references and free-text reasons for both states | Pending |
| S-10 | External price evidence | Omit it from V1; absence says nothing about reference availability. Add only as a separately typed later extension/version | Contract V0 keeps external reference separate and does not bind it to an item row here | Pending |
| S-11 | Producer identity field | Keep `producerId` opaque and `producerVersion` required; do not encode B1/B2/B3 as a closed enum | The schema needs traceability without selecting the production extractor in M3D-0 | Pending |

**Joint contract disposition:** `M3D_FULL_CONTRACT_APPROVAL_PENDING`

S-06 is not reopened by the remaining review. S-01 through S-05 and S-07
through S-11 remain pending, as do T-01 through T-07 and L-01 through L-07.
The deferred post-insufficient transport/error-handling case remains outside V1
JSON conformance and outside this approval.

Approval must identify the accepted schema/fixture revision. A change to field
names, nullability, enum spelling, ordering, identity semantics, or canonical
value grammar requires updated fixtures and both-side review.

## 4. Explicitly deferred decisions

These are later architecture/methodology decisions and do not block review of
the synthetic contract shape:

- executable OCR and source-gate orchestration;
- selection of B1, B2, B3, or another producer for the live UI;
- Android runtime packaging, on-device inference, or a development-only bridge;
- correction, candidate generation, scoring, calibration, and thresholds;
- human-reviewed output/writeback contracts;
- SQLite, durable receipt history, or inventory persistence;
- network/security realization beyond the no-path/no-URI presentation rule; and
- real-receipt, reference, annotation, or held-out evaluation.

No implementation approval is requested until Tai and Leng complete the two
consolidated reviews and the shared decisions above.

## Classification

`DRAFT_NOT_APPROVED — SYNTHETIC_ONLY`

`S06_SHARED_OWNER_DESIGN_AGREED`

`M3D_FULL_CONTRACT_APPROVAL_PENDING`

`REAL_BACKEND_ACTIVATION_NOT_READY`

`PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`
