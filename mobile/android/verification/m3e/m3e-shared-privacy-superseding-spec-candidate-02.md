# PantryProof M3E — Shared Privacy Policy Consolidation Candidate

**Document:** `M3E-SHARED-PRIVACY-SUPERSEDING-SPEC-CANDIDATE-02`  
**Status:** **REVISED SUPERSEDING CONTROLLING SPECIFICATION CANDIDATE — NOT APPROVED**  
**Intended approvers:** Tai Yong Xin (Kotlin/Android) and Leng Wei Heng (Python/backend)  
**Date:** 2026-11-08  
**Rule:** Neither this draft nor its checksum grants implementation or Git integration authorization.

## 0. Purpose, authority, evidence and limits

The original, complete *verbatim* approved SPP-01–SPP-09 document has **not** been recovered. This file is therefore **not** a recovered original, not a transcribed original approval, and not yet the authoritative policy. It assembles the previously supplied joint *proposal* text, the approved SPP-05-specific handoff, the original Kotlin R1–R3 test examples, and candidate language that would require **fresh joint approval** to supersede missing originals. Code must not be modified from this file alone.

| Evidence | Independently confirmed SHA-256 | Evidence role |
|---|---|---|
| `M3E-SPP05-SPEC-HANDOFF-01_EVIDENCE_BOUND_COPY.md` | `5EB535E37EF2EACF4D3266135C15D797BB486C5D257EA1EFCA45DDB559E62078` | SPP-05 final delimiter decisions and D01–D44 expectations; explicitly incomplete source |
| `ReceiptPresentationV1ValidatorTest.kt` (Kotlin R3) | `37C3AF59509972AA7339E5D4E2164851761D3B96CEC68AA1566B9A4625EEA902` | Original R1–R3 test inputs and assertions |
| `conformance.py` (Python R6) | `75F44B561D3B1BBD93509C476DFC23A129741DB4B1E7117EACD94FED0D3AE8FA` | Existing Python reference implementation, **not** the newly proposed policy |
| `test_presentation_v1_conformance.py` | `EA9B4D7F3960138B0B04B477860D2BE13A0C7AF9FAA32FFA4A883BC2BC3C425B` | Existing Python synthetic tests |

**Evidence hierarchy:** Existing M3D authoritative contracts and their canonical fixture manifest remain unchanged; the jointly approved SPP-05-specific findings remain preserved; all previously supplied full-policy draft language reproduced or summarized below is **proposed** and must receive explicit, identical new owner approvals before becoming controlling.

## 1. Proposed SPP-01 — Protected-marker catalogue and recognition

Initial ASCII marker tokens, compared case-insensitively **after** the SPP-03 detection-only mapping:

`participant`, `reference`, `ref`, `evaluation`, `annotation`, `ground truth`, `held out`.

For the two multiword markers, permit one or more of normalized spaces, `_`, or `-` between the component words. A marker match requires that the code point directly before and after its full span (when present) is **not** an ASCII letter or ASCII digit. Consequently `Ref` can match but `Refresh2`, `Refill2`, and `Refactor2` are not protected-marker matches. Matching a marker by itself does not reject safe prose; evaluate the *following context* under SPP-04/05/06.

**Source status:** Catalogue and ASCII boundaries from Tai's earlier supplied proposed specification and Leng's shared-direction acceptance; not available as a verified verbatim originally approved SPP-01.

## 2. Proposed SPP-02 — Qualifiers

Only `id` and `case` are protected identifier qualifiers, each requiring full ASCII-token boundaries. `identifier`, `identity`, `casework`, and `idempotent` are not qualifier matches; they are not rejected merely by an `id`/`case` prefix. Qualifiers without a preceding recognized marker are not covered by this marker-specific policy (other existing privacy rules still apply). `Participant ID` is a rejectable incomplete structured qualifier; `Participant identifier was unavailable.` is proposed to ACCEPT.

**Source status:** Prior proposed SPP-02 and final amendment candidate; superseding approval necessary.

## 3. Proposed SPP-03 — Detection-only mappings

Operate on Unicode **scalar values**. Before checking marker-specific reasons, construct a private detection view without modifying the raw reason, serialized bytes, or exact raw-string duplicate comparisons:

1. Map U+FF01–U+FF5E to U+0021–U+007E by subtracting 0xFEE0 (fullwidth ASCII range only).
2. Map U+0009–U+000D, U+0020, U+0085, U+00A0, U+1680, U+2000–U+200A, U+2028–U+2029, U+202F, U+205F, U+3000 to U+0020 SPACE.
3. Collapse consecutive resulting U+0020 SPACE characters into a single U+0020 SPACE.
4. Map ASCII U+0041–U+005A to U+0061–U+007A. Do **not** use locale-sensitive or arbitrary Unicode folding; do not apply NFC, NFKC, transliteration, or arbitrary stripping.
5. Preserve all punctuation and nonmapped characters in the detection view. Existing URI/path policies apply to the raw string **and** the detection view, without weakening their original semantics.

**Explicit new candidate concerning invisible characters (not previously frozen as an exact table):** Reject a reason containing any of U+00AD, U+034F, U+061C, U+180E, U+200B–U+200F, U+202A–U+202E, U+2060–U+206F, U+FEFF. This is a finite code-point catalogue for cross-runtime reproducibility, proposed for joint approval. Do not imply it is exhaustive for all Unicode formatting characters or an original approved table.

## 4. Proposed SPP-04 — Structured prefixes

Immediately after a recognized protected marker, after optional normalized spaces, treat any of `:` `=` `#` `.` `_` `-` as a structured-label indicator and reject with `REJECT_UNSAFE_PROVENANCE` when no earlier structural result wins. This includes incomplete fragments such as `Reference:`, `Reference -` and `Ref #`, and chains such as `Reference ==id 7`, `Reference - - evidence` and `Participant :# 001`. A space followed by exact qualifier `id`/`case` also rejects. A space followed by an ASCII digit rejects. A normal explanatory alphabetic word is not rejected by this clause by itself.

**Source status:** Synthesized from prior explicit joint proposal, R1–R3 test expectations, and SPP-05 handoff; fresh approval required as part of the superseding complete specification.

## 5. SPP-05 — Identifier extraction, delimiters and wrappers (revised normative proposal)

The approved **SPP-05-specific** D1–D9 decisions and exact 21-code-point delimiter catalogue are preserved in **Appendix A**; the original D01–D44 handoff test expectations remain in **Appendix B**. The rules in this section are a **new, explicit superseding proposal** that resolves Leng's Section-5 objection to the previous *first protected-value unit* boundary. Both owners must approve this new scope before implementation.

### SPP-05-S1 — Recognition versus detection scope

1. Identify each recognized marker with the exact SPP-01 ASCII-token boundaries and catalogue. A marker's occurrence does **not** by itself cause a rejection.
2. For **each recognized marker occurrence**, define `POST_MARKER_SPAN` as **every Unicode scalar after the end of that marker through the end of the detection-view reason**. It is *not* restricted to the first word, first balanced wrapper, first identifier atom, first sentence, or first digit-free explanatory word. Do not stop upon encountering another protected marker; process that marker separately as well. Multiple matches may produce the same unsafe-provenance finding, with no change to the rejection taxonomy.
3. Evaluate SPP-04 structured-prefix/qualifier rules at each marker's immediate tail first (as a boolean privacy finding, **not** as a new global error priority), then run the full-span SPP-05 scanner. No single early ACCEPT may prevent a later token from being inspected.
4. `The participant can review the result.` and `Reference evidence was unavailable.` remain ACCEPT absent another rule; neither contains a protected identifier-shaped later atom. `Reference evidence A12`, `Reference evidence (A12)`, `Reference information 123`, and `Reference version 2` are now proposed **REJECT**. The last example intentionally **supersedes** the candidate-01 ACCEPT expectation; this broad scan has a documented possible false-positive cost for ordinary prose such as version numbers. Do not present it as inherited approval.

### SPP-05-S2 — Finite delimiter extraction

Use **exactly** the 21 Unicode scalar delimiters in Appendix A, SPP-05-D3. After SPP-03 detection-view normalization and marker recognition, separate `POST_MARKER_SPAN` into maximal nonempty **complete atoms** bounded only by U+0020 SPACE or these 21 delimiters. Work left-to-right and examine **every** atom, not just the first. Delimiters and spaces are not discarded from the original span; retain the complete span separately for wrapper validation and original-value preservation. Period (`.`), underscore (`_`), and hyphen-minus (`-`) are `ID_CHAR`, not approved delimiters. Unsupported ASCII characters (including `@` and `+`) are not approved delimiters and remain **inside** their complete atom.

### SPP-05-S3 — Core and punctuation classification

For each complete atom, after SPP-06C's mandatory **complete-atom Unicode classification** described in Section 6:

- If the complete atom is ASCII-only, locate **all** maximal contiguous runs of `ID_CHAR = [A-Za-z0-9._-]` within that atom. If **any** run contains U+0030–U+0039, record `REJECT_UNSAFE_PROVENANCE` (SPP-05-D2/D8). Do not require punctuation or identifier qualifiers to recognize these digit-bearing runs.
- Also reject an ASCII-only atom that contains any **unsupported ASCII punctuation** as an ambiguous structured value. For this rule, unsupported punctuation means a scalar from U+0021–U+007E that is **not** an ASCII letter, ASCII digit, one of the 21 approved delimiters, or one of `.`, `_`, `-`. Such punctuation remains part of the complete atom, must never be silently stripped, and includes `@`, `+`, `/`, `\`, `` ` ``, `%`, `&`, `*`, etc. This is a **new superseding ambiguity decision**, not an assertion that SPP-05-D8 by itself previously rejected digit-free `@note`.
- Consequently, `Reference @note`, `Reference @A12`, `Reference A12+`, `Reference A12+B34`, and `Reference A12/path` are **REJECT**. The preexisting URI/path checks still run independently and may also reject these inputs; their rules are **not replaced or weakened**.
- An ASCII-only atom of digit-free `ID_CHAR` values is not rejected by SPP-05 solely for being uppercase or containing `_`, `-`, or `.`; exact qualifiers and SPP-04 still apply to the marker's immediate tail. Safe balanced wrappers around ordinary words are retained as in D5/D9.

### SPP-05-S4 — Wrappers, Unicode and precedence

Run the **unchanged, approved SPP-05-D9 wrapper stack** against the entire `POST_MARKER_SPAN` (including delimiter characters), not against stripped atoms. Any incomplete, unmatched or misnested structural wrapper yields the existing `REJECT_UNSAFE_PROVENANCE` finding; do not introduce a new rejection code. SPP-06C is evaluated on every complete atom **after delimiter partitioning but before ASCII run splitting**. SPP-08's existing validation traversal and reason-local error precedence are unaffected by this broadened privacy *detection scope*.

**Review caveat:** Scanning the complete post-marker remainder is intentionally conservative. It can reject normal explanations containing later digits or non-ASCII words. This is a specific, newly proposed owner choice motivated by the requirement that an earlier safe word cannot conceal a later identifier; owners must ratify this consequence explicitly before authorizing code.

## 6. Proposed SPP-06 — Unicode and ambiguity (explicit ordering)

### SPP-06-O1 — Fixed ordering, independent of runtime regex/Unicode categories

The following order is **normative for the new candidate** and replaces any ambiguous 'first atom' references in candidate-01. It does **not** change the already approved envelope-validation traversal or reason-level rejection precedence.

1. Maintain the original unmodified reason and perform preexisting URI/path checks against it as they operate today. Separately check the **finite SPP-03 invisible-codepoint list** on the raw reason; if present, record an unsafe-provenance privacy finding. Never erase an invisible code point to make a value acceptable.
2. Construct the private detection view **once**, applying SPP-03 in order: fullwidth U+FF01–U+FF5E mapping, listed whitespace-to-U+0020 mapping, repeated-space collapse, then ASCII A–Z lowercase mapping. No NFKC/NFC, locale or additional script folding. Test the unchanged URI/path predicates on this detection view as well; check their literal criteria without replacing them with new policies.
3. Recognize every protected marker using SPP-01 boundaries, and check the marker's immediate SPP-04 structured prefix or exact SPP-02 qualifier. For each marker, define the **full remainder of the reason** as `POST_MARKER_SPAN` (Section 5), with no first-word shortcut.
4. On the full `POST_MARKER_SPAN`, **recognize but do not delete** the 21 approved delimiters and U+0020 spaces. Extract every maximal **complete atom** between those delimiters/spaces. Preserve the original full span and its wrappers in parallel; do not perform SPP-06C on a partially stripped or ASCII-only prefix. A curly quote (when one of the 21 approved delimiters) is a boundary, not part of the atom.
5. For **each complete atom**, first run SPP-06C: **if any remaining scalar is greater than U+007F, record `REJECT_UNSAFE_PROVENANCE` for that complete atom**. This handles Cyrillic, Arabic-Indic digits and non-ASCII natural-language false positives without script-property APIs. Fullwidth ASCII has already been mapped before this check; `Reference P００１` therefore reaches the ASCII digit-bearing core check as `p001`.
6. Only for a complete atom that is ASCII-only, inspect **all maximal `ID_CHAR` runs** for ASCII digits and inspect all remaining unsupported ASCII punctuation as defined in SPP-05-S3. Do not split on unsupported punctuation before this step; it cannot conceal a digit-bearing run.
7. Independently run the unchanged SPP-05-D9 wrapper-balance algorithm on the **full, unstripped post-marker span**. Add the approved incomplete-structure unsafe-provenance finding when applicable, even if an atom has separately triggered a finding.
8. Apply the separate proposed **mixed ASCII/non-ASCII structured-label** check to the full detection view: locate a maximal label token with at least one ASCII letter and one remaining non-ASCII scalar, bounded by normalized space or SPP-04 punctuation and immediately followed, after optional normalized spaces, by SPP-04 punctuation. Reject as ambiguous, including the acknowledged `Café: unavailable` false-positive case. Purely non-ASCII labels are not automatically treated as English markers.
9. Return privacy findings into the **existing** reason-validation point; use the already approved SPP-08 precedence. No global scan is inserted before envelope/source/gate/field checks.

### SPP-06-O2 — Demonstrative order-dependent examples

| Reason | Atom after approved delimiter partition | First applicable marker-specific decision | Proposed outcome |
|---|---|---|---|
| `Reference “résumé”` | `résumé` (curly quotes are approved delimiters) | SPP-06C non-ASCII atom | REJECT |
| `Reference A12é` | `a12é` | SPP-06C **before** ASCII run matching | REJECT |
| `Reference @A12` | `@a12` (unsupported `@` is not stripped) | SPP-05-S3 digit-bearing ASCII run/unsupported punctuation | REJECT |
| `Reference @note` | `@note` | SPP-05-S3 unsupported ASCII ambiguity | REJECT |
| `Reference P００１` | `p001` after fullwidth mapping | SPP-05-S3 ASCII digit-bearing run | REJECT |
| `Reference evidence A12` | `evidence`, then `a12` | Scan **all** complete atoms | REJECT |
| `Reference evidence was unavailable.` | `evidence`, `was`, `unavailable.` | No applicable finding | ACCEPT (if no other rule applies) |

All proposed REJECT results map to the **existing** `REJECT_UNSAFE_PROVENANCE` when no earlier structural outcome wins. The Unicode false-positive and extra full-tail scanning costs are explicit new proposed policy decisions.

## 7. Proposed SPP-07 — Synthetic conformance expectations

One frozen **new** synthetic matrix should include the recorded D01–D44 cases (Appendix B), exact Kotlin R1–R3 cases (Appendix C), and extra Unicode and structured-tail cases (Appendix D). Each test must compare the same raw Unicode scalar input, expected ACCEPT/REJECT, and for REJECT the agreed error code; gate, MISSING, UNRESOLVED, and raw-JSON entry points are tested separately. Do not claim that legacy Python R6 already implements the newly proposed rule changes.

The full existing 32 canonical `receipt-presentation-v1` fixtures must remain byte-identical, with the approved 17 ACCEPT/15 REJECT expectations and manifest hashes. The new synthetic matrix must be a **separate fixture** only after explicit shared file authorization.

## 8. Proposed SPP-08 — Inherited M3D precedence and URI/path rules (independently identifiable)

**No global reordering.** Existing M3D `receipt-presentation-v1` schema/state semantics and the implemented validator traversal remain authoritative until independently reviewed code changes are authorized. This superseding policy only adds privacy findings when the *existing traversal* reaches a reason. No schema changes, result-code additions, or modifications to the 32 canonical fixtures are proposed.

### SPP-08-E1 — Baseline documents and implementation anchors

| Source | Independently verified SHA-256 (provided review sources) | What to check |
|---|---|---|
| `receipt-presentation-v1-draft.md` | `1E56F3C82716E889E46DEEE898233C2C143FDD6122F715A1C8E32EADCCCB01E5` | M3D schema, status and issue-code constraints |
| `shared-decision-register.md` | `5C3284D54C604CC71293DDC4FD3EB87E2B8099A38DF4CA9A915403BB667DBB16` | Joint decisions and unchanged contract boundaries |
| `contract-closure-proposal.md` | `A3FD591589D9433EBA4C2F64743E0353E19978915AAE9BF1ACFE6F0E4B9F8EEC` | M3D closure and accepted source relationships |
| `fixture-expansion-proposal.md` | `D7E40604AE3DC67FE291414AC817739F2B05DA9CE334C1D7379536FB1CA71293` | Canonical fixture family and expectations |
| `s06-failure-stage-clarification.md` | `003D4348924EE5A5D54B1EE9354EA36DFC4DDEE29FF46FFB3DB6966BFE904269` | S-06 outcome/stage behavior |
| `conformance.py` (Python R6) | `75F44B561D3B1BBD93509C476DFC23A129741DB4B1E7117EACD94FED0D3AE8FA` | Existing Python code behavior, NOT proof of the proposed new policy |
| `ReceiptPresentationV1Validator.kt` (Kotlin R3) | `3F6CF1A2347169B8F41C1A44EE2BA69F4170D96B389503062F13488CD3345810` | Existing Android code behavior, NOT proof of the proposed new policy |

These source hashes identify the review inputs available here, not a verification of a particular local Git HEAD or a claim that all files are in either owner's present checkout.

### SPP-08-E2 — Validation-order anchors, not invented priorities

- **Kotlin R3:** `ReceiptPresentationV1Validator.kt:71–77` validates source → failure → evidence → gate → extraction → receipt → outcome matrix after the envelope checks. Gate reasons at lines **132–161** validate nonblank, exact raw duplicate detection, insufficient-gate cardinality, then privacy. MISSING/UNRESOLVED field values at lines **357–383** validate contradictory value/confidence, required and nonblank absence reason, then privacy.
- **Python R6:** `conformance.py:546–575` validates gate raw reason nonblank, exact raw duplicate, insufficient-gate cardinality, then privacy; `conformance.py:788–803` checks absent-field value/confidence constraints before reason privacy. These are source anchors for independent review; they do not authorize moving checks in either language.
- **Error-code binding:** Both runtimes use existing `REJECT_UNSAFE_PROVENANCE` for unsafe reason text. Duplicate gate reasons retain `REJECT_GATE_STATE`; contradictory MISSING/UNRESOLVED fields retain `REJECT_CONTRADICTORY_FIELD_STATE`; an incomplete/mismatched wrapper only produces unsafe-provenance when an earlier applicable validation error has not already won.
- **Raw-value distinction:** Detection-view normalization affects *privacy matching only*. Gate duplicates continue to compare **exact raw strings**, including Unicode encodings, not their detection views.

### SPP-08-E3 — Existing URI and path protection, separately testable

The existing URI/path reason predicates are **not superseded** by SPP-05. Keep the six identified classes and their runtime-specific supported checks: URI-shaped `scheme:nonspace` (`conformance.py:219–222`; Kotlin `:709`); Windows drive/UNC paths (Python `:223–227`; Kotlin `:710–712`); Unix absolute paths (Python `:228–231`; Kotlin `:713`); labelled paths (Python `:232–235`; Kotlin `:714–717`); traversal/backslash and relative paths (Python `:236–242`; Kotlin `:718–722`); forward-slash relative compounds (Python `:243–250`; Kotlin `:723–727`). Their detection on raw reasons is retained. SPP-03 additionally proposes applying the *same existing predicates* to the detection view, without removing any raw check or silently changing their matching grammar.

**Required independent tests:** URI-shaped `OCR:failed`, Unix/path-like `Input/output processing failed.`, a Windows drive/UNC case, labelled file/path case, traversal/relative-path case, and a forward-slash compound, as well as raw duplicates and contradictory field states. Where a test input is rejected by multiple privacy predicates, the final unchanged code remains `REJECT_UNSAFE_PROVENANCE`; do not infer which predicate ran first from the public code alone.

These anchors make inherited behavior identifiable but **do not mean any proposed Python/Kotlin revision has already passed parity review**.

## 9. Proposed SPP-09 — Preservation and integration gates

After approval of an exact byte-hashed document: authorize separately bounded Python and Kotlin implementation changes. Leng retains Python ownership (anticipated `pipeline/presentation_v1/conformance.py` and `tests/test_presentation_v1_conformance.py`); Tai retains Kotlin ownership (`ReceiptPresentationV1Validator.kt`, `ReceiptPresentationV1ValidatorTest.kt`). Do not modify M3D, canonical 32 fixtures, Android UI, scoring algorithms, actual OCR, operational trust, or held-out evaluation. Test both runtimes against identical inputs, independently review conformance, and require distinct Git integration permission. Approving this candidate does **not** automatically authorize these actions.

## 10. Deterministic draft validation procedure (for review; NOT IMPLEMENTATION AUTHORITY)

```text
INPUT: original reason; existing envelope and reason-validation context

# Existing authorized traversal; do NOT reorder or short-circuit earlier errors.
1. At the already established reason-validation point, preserve original checks:
   gate nonblank -> raw exact-string duplicates -> cardinality -> privacy;
   absent field contradictions -> required/nonblank absence reason -> privacy.
2. Run the existing raw URI/path checks unchanged. Record the existing privacy
   finding if any matches; do not replace or skip their legacy checks.
3. Record unsafe provenance for any scalar in the exact SPP-03 invisible list.
4. Build the privacy-only detection view by the SPP-03 fixed code-point steps.
5. Run the SAME existing URI/path predicates on the detection view; leave raw
   reason and raw duplicate comparisons untouched.
6. In the detection view, apply the independent mixed-script label check and
   recognize ALL protected-marker occurrences using fixed SPP-01 boundaries.
7. For EACH marker occurrence, evaluate immediate SPP-04 punctuation/qualifier.
   Set POST_MARKER_SPAN = detection_view[marker_end : end_of_reason].
   DO NOT stop at the first word, first value unit, first digit-free atom,
   punctuation sentence break or a later protected marker.
8. On POST_MARKER_SPAN, recognize the 21 approved delimiters and U+0020 SPACE;
   create ALL maximal complete atoms between them. Retain the full original
   span for wrapper balancing. Do not treat unsupported ASCII as a delimiter.
9. FOR EACH complete atom IN ORDER:
      IF any scalar > U+007F:
          record REJECT_UNSAFE_PROVENANCE under SPP-06C
      ELSE:
          locate ALL maximal ID_CHAR runs within atom;
          IF any run contains ASCII 0–9: record unsafe-provenance finding;
          IF any unsupported ASCII punctuation occurs (SPP-05-S3):
              record unsafe-provenance finding, including `@note`.
10. Validate SPP-05-D9 wrapper balancing on the unstripped POST_MARKER_SPAN;
    if incomplete/mismatched/unmatched, record existing unsafe-provenance.
11. Resolve findings only at this reason's original validation point under
    unchanged SPP-08 rules, preserving earlier structural results.
```

**Explicit new choices:** Complete-tail scanning changes the prior *candidate* acceptance of `Reference version 2` and `Reference version ٢`; `Reference @note` now explicitly rejects; Unicode atoms are classified after approved delimiter extraction but before ASCII core splitting. These require **fresh joint approval** of the exact bytes of this revised candidate.

## 11. Exact pending owner decisions (one consolidated review)

1. **Authority:** Ratify this as a **new superseding full SPP-01–SPP-09 policy** and NOT a verbatim recovery; both owners must approve the same verified SHA-256 bytes.
2. **Leng correction C01 / Section 5:** Approve complete `POST_MARKER_SPAN` scanning across *all subsequent atoms*, not the first-value-unit shortcut. This catches `Reference evidence A12` and `Reference evidence 123` but **intentionally changes** previously proposed `Reference version 2` and `Reference version ٢` from ACCEPT to **REJECT**, with acknowledged ordinary-prose false positives.
3. **Leng correction C02 / Sections 5–6:** Approve the precise ordering: SPP-03 detection view → marker recognition → SPP-04 check → 21-delimiter partition → **SPP-06C on each whole complete atom** → ASCII ID-run/unsupported punctuation checks → unchanged wrapper balancing on the original full suffix. Approve the finite invisible-codepoint list and mixed-script ambiguity rule, including documented false-positive scope.
4. **Leng correction C03 / Sections 8 and 11:** Explicitly ratify `Reference @note` as `REJECT_UNSAFE_PROVENANCE` (absent an earlier structural error), with `@` remaining outside the 21 delimiters; retain the independently identified M3D/source-gate/field precedence and *all six existing URI/path predicate classes*, with no replacement or weakening.
5. **SPP-05 carry-forward:** Preserve the exact 21 delimiters; D8/D9 behavior; F01–F03 and D28 resolutions; and the approved binding `EXISTING_INCOMPLETE_STRUCTURE_FINDING → REJECT_UNSAFE_PROVENANCE`. Treat Appendices A–D as traceability of older evidence/proposals, **not** as independently approved contradictory rule text.
6. **Change control:** Ratify the revised synthetic expectations below, and confirm this approval does **not** authorize source/test modifications, shared fixture writing, Git operations, Android activation or real-data evaluation. Implementation and Git integration require separate, bounded authorizations.

### Revised candidate-02 matrix — normative if and only if jointly approved

| Case ID | Exact input | Candidate-02 outcome | Reason / difference from candidate-01 |
|---|---|---|---|
| C02-01 | `Reference evidence A12` | REJECT_UNSAFE_PROVENANCE | Later digit-bearing atom cannot be hidden behind a safe first word |
| C02-02 | `Reference evidence (A12)` | REJECT_UNSAFE_PROVENANCE | Later wrapped digit-bearing core |
| C02-03 | `Reference information 123` | REJECT_UNSAFE_PROVENANCE | Later numeric-only token; conservative fail-closed choice |
| C02-04 | `Reference version 2` | **REJECT_UNSAFE_PROVENANCE** | **Overrides old EXTRA-03 ACCEPT proposal**; recognized potential prose false positive |
| C02-05 | `Reference version ٢` (`٢` = U+0662) | **REJECT_UNSAFE_PROVENANCE** | **Overrides old P-070 ACCEPT proposal**; later non-ASCII atom |
| C02-06 | `Reference evidence was unavailable.` | ACCEPT | No protected-looking atom or wrapper defect |
| C02-07 | `Reference @note` | **REJECT_UNSAFE_PROVENANCE** | Explicit C03 decision; unsupported `@` is not a delimiter |
| C02-08 | `Reference @A12` | REJECT_UNSAFE_PROVENANCE | Unsupported punctuation and digit-bearing core |
| C02-09 | `Reference “résumé”` | REJECT_UNSAFE_PROVENANCE | Unicode curly quotes delimit first; SPP-06C sees whole `résumé` atom |
| C02-10 | `Reference A12é` | REJECT_UNSAFE_PROVENANCE | SPP-06C sees complete Unicode atom before ASCII splitting |
| C02-11 | `Reference P００１` | REJECT_UNSAFE_PROVENANCE | Fullwidth ASCII mapped first; SPP-05 sees ASCII digit-bearing core |
| C02-12 | `Reference (note)` | ACCEPT | Balanced safe explanatory wrapper |
| C02-13 | `Reference (note` | REJECT_UNSAFE_PROVENANCE | Incomplete wrapper uses approved existing code |
| C02-14 | `Reference note)` | REJECT_UNSAFE_PROVENANCE | Unmatched closer uses approved existing code |
| C02-15 | `Reference A12,` | REJECT_UNSAFE_PROVENANCE | Mandatory delimiter bypass case retained |
| C02-16 | `Participant (P001)` | REJECT_UNSAFE_PROVENANCE | Mandatory wrapped identifier case retained |
| C02-17 | `The participant can review the result.` | ACCEPT | No identifier-shaped or Unicode atom after marker |
| C02-18 | `The participant can review 2 options.` | REJECT_UNSAFE_PROVENANCE | Explicit conservative false positive of complete-tail scan |
| C02-19 | `Café: unavailable` | REJECT_UNSAFE_PROVENANCE | Explicit candidate mixed-script-label false positive |
| C02-20 | `Imej café tidak tersedia.` | ACCEPT | No recognized protected marker or structured mixed-script label |
| C02-21 | Duplicate identical unsafe gate reasons | REJECT_GATE_STATE | Existing raw-duplicate precedence, not privacy-first |
| C02-22 | Contradictory MISSING field with unsafe reason | REJECT_CONTRADICTORY_FIELD_STATE | Existing field-state precedence |
| C02-23 | `OCR:failed` | REJECT_UNSAFE_PROVENANCE | Existing URI-shaped diagnostic rule retained |
| C02-24 | `Input/output processing failed.` | REJECT_UNSAFE_PROVENANCE | Existing relative forward-slash protection retained |

**Supersession note:** Appendix D's P-070 and EXTRA-03 ACCEPT outcomes are **historical proposal evidence only**. If candidate-02 is jointly approved, C02-04/C02-05 above control; Appendix D is intentionally left unaltered to preserve its evidence provenance. The original 32 canonical fixture cases and their expectations remain unchanged. Any discovered conflict between this new rule and a canonical fixture must be raised before code modification; do not rewrite fixtures to make tests pass.

**Disposition now:** `M3E_SUPERSEDING_SPEC_CANDIDATE_02_READY_FOR_EXACT_BYTE_JOINT_REVIEW` — **NOT FROZEN / NO IMPLEMENTATION AUTHORIZATION**

---

## Appendix A — Verified SPP-05 final delimiter source text

The following block is copied from the hash-verified evidence-bound handoff, Section 1, and retains its original warnings and authority restrictions.

## 1. Normative SPP-05 final delimiter decisions (consolidated)

### SPP-05-D1 — Protected value context

Only spans identified by the **existing approved protected-marker recognition policy** as protected-marker values are subject to the identifier-specific extraction procedure. This document does not invent or expand the protected-marker vocabulary. It does not treat every ordinary occurrence of a word such as “reference” in natural-language prose as a protected value without the existing recognition policy's determination.

Mandatory privacy examples (each final reason: `REJECT_UNSAFE_PROVENANCE`, subject to the approved earlier-gate precedence where relevant):

- `Reference A12,`
- `Reference A12)`
- `Reference (A12)`
- `Participant (P001)`

### SPP-05-D2 — ASCII identifier core

`ID_CHAR = [A-Za-z0-9._-]`, defined by exact ASCII code-point comparisons: A–Z = U+0041..U+005A; a–z = U+0061..U+007A; ASCII digits = U+0030..U+0039; period = U+002E; underscore = U+005F; hyphen-minus = U+002D.

A nonempty maximal contiguous `ID_CHAR` run containing at least one ASCII digit is an identifier-shaped core in the protected value context. Period, underscore and hyphen are part of the core, not punctuation to strip. Digit-free ASCII words are not rejected *solely* by this identifier-core check; other SPP provisions still apply. An `ID_CHAR`-only core may be immediately surrounded by recognized delimiters, normalized whitespace, or unsupported characters; no such surrounding material may conceal a digit-bearing core.

### SPP-05-D3 — Recognized textual delimiters

The **exact 21 code points** are:

| Family | Members | Exact Unicode scalar values |
|---|---|---|
| Parentheses | `(` `)` | U+0028, U+0029 |
| Square brackets | `[` `]` | U+005B, U+005D |
| Braces | `{` `}` | U+007B, U+007D |
| ASCII quotation | `"` `'` | U+0022, U+0027 |
| Curly double quotation | `“` `”` | U+201C, U+201D |
| Curly single quotation | `‘` `’` | U+2018, U+2019 |
| Double guillemets | `«` `»` | U+00AB, U+00BB |
| Single guillemets | `‹` `›` | U+2039, U+203A |
| Separating punctuation | `,` `;` `:` `!` `?` | U+002C, U+003B, U+003A, U+0021, U+003F |

Delimiters can appear before or after the identifier core, singly, repeatedly and in mixed combinations. They are removed only for extraction/comparison, **not** silently deleted from the original value span used by wrapper or structural validation. Unbalanced punctuation must never prevent detection of the identifier core.

Non-delimiters include `.` (U+002E), `_` (U+005F), `-` (U+002D), `/` (U+002F), `\` (U+005C), and backtick (U+0060). The first three remain `ID_CHAR`; the others do not become authorized delimiters. Existing URI and path restrictions remain unchanged.

### SPP-05-D4 — Normalized whitespace

The existing approved shared normalization stage runs before SPP-05. At the SPP-05 boundary, normalized whitespace is treated as U+0020 SPACE, as provided by that stage. The **set of original whitespace code points to normalize is not reconstructed here**.

Spaces may occur between a protected marker, delimiters and a candidate core. Example: `Reference ( A12 )` exposes `A12`. Do not join independent alphanumeric fragments separated by spaces. Do not accept potentially split or malformed values when an existing ambiguity rule requires fail-closed rejection.

### SPP-05-D5 — Safe explanations and digit-free words

Recognized balanced wrappers do not by themselves make digit-free natural language unsafe. These are proposed ACCEPT cases where no other provision applies: `Reference note,`, `Reference (note)`, `Reference information is unavailable.`, `The reference has been removed.`, `Reference N_A`, and `No participant information was retained.`

Do not turn a single word's absence of ASCII digits into unconditional acceptance: malformed wrappers, unsupported tokens, URI/path restrictions, marker rules and the other SPP checks still run.

### SPP-05-D6 / SPP-06C — Unicode and fullwidth compatibility

The corrected agreed outcomes are:

- `Reference résumé` — REJECT under the prior SPP-06C Unicode-token rule; **the earlier D29 ACCEPT expectation was revoked**. No Unicode natural-language exception for an identifier value position was jointly approved.
- `Reference A12é` — REJECT under SPP-06C for a Unicode-containing identifier-shaped atom.
- `Participant P00１` — REJECT after the already approved fullwidth normalization maps fullwidth `１` to ASCII `1`, exposing `P001` to SPP-05. This is the **corrected D28 governing-rule reference**.

Never silently drop a non-ASCII suffix, transliterate it, classify Unicode digits as ASCII digits without the approved normalization, or accept an ASCII prefix while ignoring a Unicode-containing complete atom. The exact scope, order and additional branches of the full original SPP-06C must be obtained from the approved document.

### SPP-05-D7 — Rejection precedence and URI/path preservation

SPP-05 produces existing findings only. Do not create a new reason code or change traversal. SPP-08 determines final rejection according to its already approved reason-level precedence; **earlier gate-state and contradictory-field rejections retain priority**. Existing URI/path restrictions retain their existing checks and priorities. The exact full priority table is not supplied in the source material available for this handoff and cannot be invented.

### SPP-05-D8 — Unsupported ASCII bypass prevention (F02)

A character outside both `ID_CHAR` and the 21-code-point delimiter catalogue must never be silently stripped or treated as a permitted delimiter. For each nonempty protected-value atom bounded by U+0020 SPACE and/or approved delimiters:

1. If the atom contains non-ASCII after approved normalization, pass the **complete atom** through the unchanged SPP-06C classification.
2. Otherwise identify all maximal contiguous `ID_CHAR` runs within the atom.
3. If any such run contains an ASCII digit, record the existing unsafe-provenance finding even when unsupported ASCII characters surround it.
4. Preserve unsupported characters for other existing structural, ambiguity and URI/path validators; do not silently accept an otherwise ambiguous value.
5. If no digit-bearing run exists, SPP-05 alone does not reject it as a protected identifier; other existing rules still decide.

Thus `Reference @A12`, `Reference A12+`, `Reference @@A12`, `Reference A12++`, and `Reference A12+B34` all produce `REJECT_UNSAFE_PROVENANCE` when that is the applicable highest-precedence finding. `@` and `+` have **not** been added to the delimiter catalogue. For `Reference @note`, there is no SPP-05 digit-bearing core; the existing ambiguity/structure rule decides the final result, which is **not supplied**.

### SPP-05-D9 — Incomplete wrappers (F03) and final code binding

Existing 21 delimiters are unchanged. The structural wrapper pairs are:

- `(` → `)`; `[` → `]`; `{` → `}`
- `“` → `”`; `‘` → `’`; `«` → `»`; `‹` → `›`
- Symmetric ASCII `"` ↔ `"`; `'` ↔ `'`

Commas, semicolons, colons, exclamation marks and question marks are textual separators, not balancing wrappers.

Read the normalized protected-value span from left to right by Unicode code point. Push the expected closing wrapper for an opening asymmetric wrapper. A closing asymmetric wrapper must match the top of the stack; otherwise the structure is incomplete. For an ASCII symmetric quote, close an identical top-of-stack quote, otherwise open that quotation. A nonempty stack at end-of-input is incomplete. A mismatched/unmatched closing wrapper is incomplete. Digit-bearing identifier detection still runs even when wrapper parsing fails.

**Approved explicit binding:**

`EXISTING_INCOMPLETE_STRUCTURE_FINDING` → `REJECT_UNSAFE_PROVENANCE`

When an otherwise structurally valid protected-marker value contains an incomplete, unmatched, or mismatched wrapper, record the existing `REJECT_UNSAFE_PROVENANCE` finding. Never introduce a new code or bypass SPP-08 precedence, including earlier gate-state and contradictory-field rejections. Balanced digit-free explanations (e.g., `Reference (note)`) remain accepted absent other violations.

## Appendix B — SPP-05 D01–D44 candidate matrix, copied from verified handoff

The expectations below are the *proposed policy expectations*, **not** independently demonstrated executable Python/Kotlin outcomes.

| ID | Exact synthetic input | Proposed outcome | Rule/rationale |
|---|---|---|---|
| D01 | `Reference A12,` | REJECT — unsafe provenance | SPP-05 trailing comma; mandatory |
| D02 | `Reference A12)` | REJECT — unsafe provenance | SPP-05 core despite trailing unmatched wrapper; mandatory |
| D03 | `Reference (A12)` | REJECT — unsafe provenance | SPP-05 wrapped core; mandatory |
| D04 | `Participant (P001)` | REJECT — unsafe provenance | SPP-05 wrapped core; mandatory |
| D05 | `Reference ,A12` | REJECT | Leading delimiter exposes digit-bearing core |
| D06 | `Reference ((A12))` | REJECT | Repeated balanced wrappers expose core |
| D07 | `Reference A12,,` | REJECT | Repeated trailing delimiters expose core |
| D08 | `Reference ([A12]),` | REJECT | Mixed delimiters expose core |
| D09 | `Reference "A12"` | REJECT | ASCII double quotation |
| D10 | `Reference 'A12'` | REJECT | ASCII single quotation |
| D11 | `Reference “A12”` | REJECT | Curly quotations |
| D12 | `Reference ( A12 )` | REJECT | Normalized spaces between wrapper and core |
| D13 | `Reference A12),”` | REJECT | Mixed delimiters + core; wrapper errors do not bypass detection |
| D14 | `Evaluation "E-004"` | REJECT | Hyphen remains `ID_CHAR` |
| D15 | `Reference A12.` | REJECT | Period remains `ID_CHAR` |
| D16 | `Reference A12_` | REJECT | Underscore remains `ID_CHAR` |
| D17 | `Reference A12-` | REJECT | Hyphen remains `ID_CHAR` |
| D18 | `Reference 123` | REJECT | Digit-bearing numeric ASCII core |
| D19 | `Reference note,` | ACCEPT | Digit-free word + ordinary separator |
| D20 | `Reference (note)` | ACCEPT | Balanced digit-free explanation |
| D21 | `Reference information is unavailable.` | ACCEPT | Safe ASCII explanation; no other violation assumed |
| D22 | `The reference has been removed.` | ACCEPT | Safe natural-language prose |
| D23 | `Reference N_A` | ACCEPT | Digit-free ASCII token |
| D24 | `Reference ()` | REJECT | Empty protected-value structure; existing fail-closed rule |
| D25 | `Reference ((` | REJECT — unsafe provenance | Incomplete wrappers, D9 explicit binding |
| D26 | `Reference (note` | REJECT — unsafe provenance | Incomplete wrapper, D9 explicit binding |
| D27 | `Reference A12é` | REJECT | SPP-06C non-ASCII value atom |
| D28 | `Participant P00１` | REJECT | Approved fullwidth normalization followed by SPP-05 |
| D29 | `Reference résumé` | REJECT | Corrected SPP-06C Unicode-token rule (not ACCEPT) |
| D30 | `Reference A12/path` | REJECT | Existing URI/path restrictions and unsafe identifier detection |
| D31 | `Reference A12\path` | REJECT | Existing path restrictions and unsafe identifier detection |
| D32 | `No participant information was retained.` | ACCEPT | Safe natural-language explanation |
| D33 | `Reference @A12` | REJECT — unsafe provenance | D8 unsupported ASCII prefix bypass |
| D34 | `Reference A12+` | REJECT — unsafe provenance | D8 unsupported ASCII suffix bypass |
| D35 | `Reference @@A12` | REJECT — unsafe provenance | D8 repeated unsupported prefix |
| D36 | `Reference A12+B34` | REJECT — unsafe provenance | D8 multiple identifier runs |
| D37 | `Reference (note` | REJECT — unsafe provenance | D9 incomplete opening wrapper; duplicates D26 intentionally |
| D38 | `Reference (note)` | ACCEPT | D9 balanced safe explanation; duplicates D20 intentionally |
| D39 | `Reference ((note))` | ACCEPT | D9 repeated balanced wrappers |
| D40 | `Reference ([note)]` | REJECT — unsafe provenance | D9 mismatched nesting |
| D41 | `Reference "note` | REJECT — unsafe provenance | D9 unclosed quote |
| D42 | `Reference "note"` | ACCEPT | D9 balanced ASCII quotes |
| D43 | `Reference note)` | REJECT — unsafe provenance | D9 unmatched closing wrapper |
| D44 | `Reference A12)` | REJECT — unsafe provenance | D8/D9 identifier detection despite unmatched wrapper; duplicates D02 intentionally |

## Appendix C — Kotlin R1–R3 original regression inputs, recovered from actual tests

The uploaded hash-verified `ReceiptPresentationV1ValidatorTest.kt` contains these precise values, with `UNSAFE_PROVENANCE` asserted for gate, missing, unresolved and raw-JSON validation pathways. A new superseding policy should retain these expectations unless owners explicitly change them.

| Source revision | Input | Existing Kotlin expected code |
|---|---|---|
| R1 | `Participant :# 001` | `REJECT_UNSAFE_PROVENANCE` |
| R1 | `Participant ID: # 001` | `REJECT_UNSAFE_PROVENANCE` |
| R1 | `Reference: # 001` | `REJECT_UNSAFE_PROVENANCE` |
| R2 | `Participant - 001` | `REJECT_UNSAFE_PROVENANCE` |
| R2 | `Reference - A12` | `REJECT_UNSAFE_PROVENANCE` |
| R2 | `Evaluation _ case 012` | `REJECT_UNSAFE_PROVENANCE` |
| R2 | `Participant . 001` | `REJECT_UNSAFE_PROVENANCE` |
| R3 | `Ref#:ID 123` | `REJECT_UNSAFE_PROVENANCE` |
| R3 | `Reference #: id 001` | `REJECT_UNSAFE_PROVENANCE` |
| R3 | `Reference ==id 7` | `REJECT_UNSAFE_PROVENANCE` |
| R3 | `Reference - - evidence` | `REJECT_UNSAFE_PROVENANCE` |

## Appendix D — Additional previously proposed SPP test cases and evidence status

The following values were explicitly supplied in the earlier proposed 55-case amendment plus its P-056–P-074 extension. **These are historical, not candidate-02 normative outcomes; P-070 and EXTRA-03 are expressly superseded by C02-05 and C02-04 above.** These are proposal expectations requiring final ratification; some change existing Python R6/Kotlin R3 behavior. Textual display of Unicode characters is insufficient for byte parity: each shared artifact must also serialize exact UTF-8 bytes and code-point metadata.

| ID | Input | Proposed expectation | Source/rule |
|---|---|---|---|
| P-056 | `Reference А12` (U+0410 Cyrillic A) | REJECT | SPP-06C |
| P-057 | `Reference A١٢` (U+0661 U+0662) | REJECT | SPP-06C |
| P-058 | `Reference ١٢` | REJECT | SPP-06C |
| P-059 | `Reference café` | REJECT | SPP-06C, documented false positive |
| P-060 | `Reference 证据` | REJECT | SPP-06C |
| P-061 | `Reference ABC` | ACCEPT | Digit-free ASCII first token |
| P-062 | `Reference ABC-DEF` | ACCEPT | Digit-free ASCII first token |
| P-063 | `Reference A12` | REJECT | SPP-05 digit-bearing core |
| P-064 | `Participant P001` | REJECT | SPP-05 digit-bearing core |
| P-065 | `Reference A_12` | REJECT | SPP-05 digit-bearing core |
| P-066 | `Reference evidence` | ACCEPT | Plain explanation |
| P-067 | `Participant identifier` | ACCEPT | `identifier` is not `id` qualifier |
| P-068 | `Reference P００１` | REJECT | Fullwidth mapping then SPP-05 |
| P-069 | `Imej café tidak tersedia.` | ACCEPT | No protected English marker |
| P-070 | `Reference version ٢` | ACCEPT | First-token scope: `version` |
| P-071 | Duplicate `Reference А12` + `Reference А12` | Existing gate-state REJECT | SPP-08 raw duplicate precedence |
| P-072 | Contradictory MISSING state + `Reference А12` | Existing contradictory-state REJECT | SPP-08 field precedence |
| P-073 | Blank `U+0020 U+0009` | Existing nonblank/state REJECT | SPP-08 |
| P-074 | Raw pair `Reference A12` + `Reference A１２` | Both privacy REJECT but not duplicates | SPP-08 raw duplicate equality |
| EXTRA-01 | `Reference @note` | **UNDECIDED** — propose REJECT | Unsupported ASCII, ambiguity policy |
| EXTRA-02 | `Café: unavailable` | **NEW PROPOSAL: REJECT** | Mixed label / possible false positive |
| EXTRA-03 | `Reference version 2` | ACCEPT under proposed first-unit boundary | Avoid scanning later prose |
| EXTRA-04 | `Reference evidence2` | REJECT | Digit-bearing first unit |
| EXTRA-05 | `Participant identifier was unavailable.` | ACCEPT | Exact qualifier boundary |
| EXTRA-06 | `Reference - - evidence` | REJECT | SPP-04 punctuation chain / Kotlin R3 existing test |
| EXTRA-07 | `Ｐａｒｔｉｃｉｐａｎｔ：００１` | REJECT | Fullwidth mapping |
| EXTRA-08 | `Partіcipant:001` (U+0456 Cyrillic `і`) | NEW PROPOSAL: REJECT | Mixed-script structured label |
| EXTRA-09 | `Reference` + U+200B + `:A12` | NEW PROPOSAL: REJECT | Invisible character blocklist |
| EXTRA-10 | `Reference A12,` | REJECT | SPP-05-D01 delimiter |

## Appendix E — Source boundary, integrity and next procedure

- Protected M3D source contracts and existing canonical fixtures **are not being rewritten**; this proposal is a separate conversation artifact, not a repository change.
- The existing Python R6 hash proves **source identity**, not compliance with the new policy; present Python R6 behavior may differ intentionally.
- The existing Kotlin R3 source/test hashes prove **source identity**, not compliance with the new policy.
- Approval request to both owners must contain the **same exact file bytes and SHA-256**. Any edits require a new hash and new review.
- Independent review must examine affected source, test changes, per-case code/parity, zero-fixture-regression, and original source-bound precedence. Then separate Git integration authorization is necessary.

**Disposition now:** `M3E_SUPERSEDING_SPEC_CANDIDATE_02_READY_FOR_EXACT_BYTE_JOINT_REVIEW` — **NOT APPROVED / NO IMPLEMENTATION AUTHORIZATION**.
