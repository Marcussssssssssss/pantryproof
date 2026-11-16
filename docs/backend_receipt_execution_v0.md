# Backend receipt execution V0

Task: `PANTRYPROOF_LENG_I2B_L01_IMPLEMENTATION_01`

Status: synthetic-only implementation for independent technical review.

## Public interface

```python
def extract_adapted_receipt_v0(
    *,
    adapted_source: AdaptedOcrSource,
    gate_evaluator: Callable[[AdaptedOcrSource], SourceEvidenceGateResult],
) -> B2ExtractionResult:
    ...
```

Import directly from `pipeline.backend_receipt_execution_v0`. Package exports
and existing contracts are unchanged. All inputs are required and keyword-only.
The caller already owns the gate-free source package; this function does not
perform OCR, load an image, or invent an input or configuration identity.

## Execution and validation

1. Check the source type and rerun its existing record validation. Require a
   callable evaluator before starting execution.
2. Invoke that evaluator once with the exact supplied source object.
3. Rerun existing gate-record validation when the returned object is a gate
   record. Require its decision to be an actual `SourceEvidenceDecision` enum.
   Contract type annotations alone do not enforce this; accepting a string
   would bypass B2's enum-identity check for insufficient evidence.
4. Call existing `attach_gate_result()` with the original source and actual
   returned gate. Existing attachment rejects wrong types or receipt bindings.
5. Call existing `extract_b2()` once with the attached evidence and return its
   exact `B2ExtractionResult`, without reconstruction or replacement.

Source/gate validation failures prevent B2 invocation. Exceptions propagate
without wrapping, suppression, automatic retries or a partial return. The
function introduces no new error class or shared schema.

Exactly-once behavior applies to one valid invocation. Independent repeated
calls each execute their evaluator and B2 once. There is no request registry,
cross-process deduplication, cancellation or distributed exactly-once claim.
The injected evaluator is trusted to follow its own contract; this seam does
not authenticate its producer or prove its internal execution behavior.

## Source and output preservation

Attachment retains receipt/image IDs, source status, the original token tuple,
token objects, geometry, transcription, native OCR confidence and provenance.
Missing confidence remains `None`; extractor confidence is not filled from OCR
scores. The seam never filters, reorders or normalizes source observations.

A real `INSUFFICIENT` decision reaches unchanged B2, which returns no receipt
and retains `FALLBACK_NO_UPDATE` with the exact gate record. A sufficient gate
permits the genuine B2 pre-review automatic output. B2's structural extraction
status, including `FAILED` where applicable, is not recast as a technical
exception. No Presentation V1 envelope is emitted.

The function supplies no gate sufficiency criteria or status-to-gate policy.
Synthetic gate doubles test orchestration only; they are not approved
operational evaluators and do not establish OCR success or evidence quality.
The implementation relies on the existing immutable source contracts and does
not protect against coordinated hostile mutation inside an injected callback.

## Synthetic verification

The focused tests use real public OCR-adapter records and the actual B2
extractor. Spies check gate/attachment/B2 order and exact object continuity.
They cover sufficient output, insufficient fallback, wrong gate types and
identity, invalid decision enums, record revalidation, propagated failures,
preserved missing/native confidence, repeated independent execution and absence
of automatic downstream dependencies. All four source statuses are exercised
with clearly synthetic gate doubles to test preservation, not eligibility.

Authorized commands use the pinned project Python, bytecode disabled, plugin
autoload disabled, and pytest cache disabled:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTHONIOENCODING = 'utf-8'
& 'D:\Heng\FYP2\pantryproof\.venv\Scripts\python.exe' -B -m pytest -p no:cacheprovider -o 'addopts=' -q tests/test_backend_receipt_execution_v0.py
& 'D:\Heng\FYP2\pantryproof\.venv\Scripts\python.exe' -B -m pytest -p no:cacheprovider -o 'addopts=' -q tests/test_ocr_adapter.py tests/test_layout_b2.py
```

No canonical Presentation V1 fixture tests or full-suite runs are part of this
slice. Existing fixture bytes and their Windows checkout representation remain
untouched.

## Exclusions and next gates

No B1, B3, D3, confidence-recipe adapter, scoring, correction selection,
transport, server, persistence, inventory mutation or Android activation runs
here. Permanent c0 records are neither created nor changed. This is not a
complete receipt-processing backend or a production gate implementation.

Operational gate criteria, OCR invocation, resource limits, runtime deployment,
request/retry handling, V1 wire-identity bindings, runtime presentation and
failure mapping require separate decisions and authorization. Independent
technical review is required before Git integration.

`REAL_BACKEND_ACTIVATION_NOT_READY`

`PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`
