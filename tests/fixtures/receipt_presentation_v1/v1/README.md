# Receipt Presentation V1 synthetic conformance fixtures

**Status:** IMPLEMENTATION CANDIDATE — SYNTHETIC_ONLY

This directory is the single physical fixture set consumed by the Kotlin and
Python M3E-1 conformance tests. It is test data, not a runtime API, backend
gateway, OCR result set, evaluation corpus, or authorization for real receipt
processing.

## Contents

- `manifest.json` lists exactly 32 fixture wrappers: 17 expected `ACCEPT`
  results and 15 deterministic rejection results.
- `fixtures/` contains those exact raw UTF-8 files.
- The wrapper members are `fixtureStatus`, `scenario`, `expectedResult`,
  optional `consumerContext`, and `envelope`. Only the nested `envelope`
  is passed to production conformance decoding and validation.
- Fixtures 06, 07, and 08 preserve the historical draft bytes exactly.
  Fixtures 01–05 and 09 are approved successors. All remaining cases are new
  approved synthetic scenarios.

## Integrity and usage

Hash every fixture as raw bytes, including its final newline. Do not
parse/reserialize before SHA-256 verification. A harness must reject duplicate
or unknown wrapper members, verify `expectedResult` against the manifest, fail
on missing or unlisted JSON fixtures, and fail if zero cases execute.

`38-duplicate-json-key.json` intentionally contains a duplicate
`schemaVersion` key and must be read with duplicate-aware parsing. All other
fixture files and the manifest are ordinary strict JSON.

The `SYNTHETIC_FIXTURE` source type is valid only in fixture mode. IDs and
provenance are fictional and privacy-safe. Fixtures 67 and 67a represent
genuine structurally valid synthetic Contract V0 output shapes with preserved
`OCR_FAILED` and `RECEIVED` source-processing statuses; neither status is
reinterpreted as OCR success. The Python projection test reconstructs their
Contract V0 objects and requires exact equality with both nested envelope
objects. The deferred failure after an insufficient gate is outside V1 JSON
conformance and is intentionally absent.

These bytes are not frozen for cross-language parity until Tai's independent
fixture review and the required implementation review are recorded. Validators
or expected outcomes must not be weakened to make tests pass.
