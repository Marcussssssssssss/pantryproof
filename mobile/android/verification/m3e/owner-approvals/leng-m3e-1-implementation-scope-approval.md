# Leng M3E-1 Implementation Scope Approval Evidence

**Evidence source:** Executed owner statement supplied directly by the user.  
**Owner attribution:** Leng Wei Heng, as explicitly stated in the supplied text.  
**Scope candidate:** `M3E-1P-SCOPE-CANDIDATE-2026-11-05`  
**Approved scope document SHA-256:** `BAA1F6E3866E2E86D994AC43125C346D813295964BF327A1B9FFBC9C37D280C2`  
**Reference checkpoint:** `656c9824becdaf392f59ca510df392d82e4b7d0c`  
**Evidence received and recorded:** 2026-11-05 (Asia/Kuala_Lumpur)  
**Owner-stated approval date:** Not specified in the supplied statement.  
**Authentication note:** This record preserves the supplied textual owner
attribution. It does not claim an independently verified signature, identity,
or authentication mechanism.  
**Preservation note:** The statement below is reproduced verbatim.

## Verbatim owner statement

# PantryProof M3E-1 — Leng Independent Implementation Scope Approval

**Owner:** Leng Wei Heng\
**Capacity:** Python/backend implementation owner\
**Scope candidate:** `M3E-1P-SCOPE-CANDIDATE-2026-11-05`

**Verified scope SHA-256:** `BAA1F6E3866E2E86D994AC43125C346D813295964BF327A1B9FFBC9C37D280C2`

**Reference Git checkpoint:** `656c9824becdaf392f59ca510df392d82e4b7d0c`

**Decision: APPROVE — NO EXCEPTIONS**

I, Leng Wei Heng, confirm that I independently reviewed the complete authoritative M3E-1P implementation scope document, including Sections 5 and 6, against the jointly approved M3D-1 contract and S-06 agreement.

I approve the exact implementation scope described below.

### A. Leng-owned Python files

I approve creating only the following five Python implementation and test files:

1. `pipeline/presentation_v1/__init__.py`
2. `pipeline/presentation_v1/conformance.py`
3. `tests/presentation_v1_projection_support.py`
4. `tests/test_presentation_v1_conformance.py`
5. `tests/test_presentation_v1_projection.py`

I approve strict receipt-presentation-v1 validation, synthetic Contract V0 projection testing, immutable evidence preservation, exact identity and token integrity checks, and privacy-safe provenance handling.

No modification of protected Contract V0 definitions or research components is authorized.

### B. Shared synthetic fixtures

I approve the canonical fixture directory:

`tests/fixtures/receipt_presentation_v1/v1/`

The approved shared scope consists of:

- Exactly 32 canonical synthetic fixture cases.
- 17 expected ACCEPT outcomes.
- 15 expected REJECT outcomes.
- The manifest and README defined in Section 5.3.
- The exact fixture filenames, validation expectations and rejection semantics specified in Section 6.
- Raw-byte SHA-256 verification, manifest consistency and cross-language parity requirements defined in Section 6.1.

I agree to coordinate canonical fixture preparation.

Tai must independently review the canonical fixture bytes and expected results before they are frozen.

Both Kotlin and Python implementations must consume the same physical fixture set.

### C. Mandatory safeguards

I approve the following safeguards:

1. Implementation must remain inside the exact authorized file allowlists.
2. The M3D-1 authoritative contract and SHA-256 manifest must remain unchanged.
3. The S-06 agreement and deferred post-insufficient-gate presentation exception must remain unchanged.
4. Kotlin and Python must enforce the same approved validation semantics and rejection codes.
5. Neither implementation may silently normalize invalid input.
6. Fixture expectations and validators must not be weakened merely to obtain passing tests.
7. All test data must remain synthetic and reproducible.
8. Existing Android tests, Contract V0, B1/B2/B3 behavior and protected research contracts must be preserved.
9. Required regression testing and independent implementation review must be completed before Git integration.

### D. Explicit exclusions

This approval does not authorize:

- Real OCR activation or source-gate orchestration.
- B1/B2/B3 runtime integration.
- Real backend activation or Android runtime connection.
- Inventory persistence or synchronization.
- Scoring, calibration or proposed-method integration.
- Real-receipt or held-out evaluation.
- Modifications to protected research contracts.
- Git staging, committing, pushing, merging or rebasing.

All Git integration remains under Tai's separately controlled PowerShell workflow.

### E. Owner decision

I acknowledge Tai's recorded independent scope approval:

`TAI_M3E_1_IMPLEMENTATION_SCOPE_APPROVED`

I independently approve my five Python files and the exact shared fixture scope against the same M3E-1P candidate.

**Scope exceptions: None.**

My approval covers the exact implementation scope. Coding must follow the separately issued bounded implementation instructions and mandatory Git preflight.

**Leng-owner decision:**

`LENG_M3E_1_IMPLEMENTATION_SCOPE_APPROVED`

`M3E_1_IMPLEMENTATION_SCOPE_JOINTLY_APPROVED`

`REAL_BACKEND_ACTIVATION_NOT_READY`

`PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`
