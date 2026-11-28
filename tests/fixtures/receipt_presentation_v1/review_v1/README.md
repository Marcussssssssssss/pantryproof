# Proposed receipt review fixtures

The [review contract](../../../../docs/review_contract.md) defines the wire schema. This directory contains 17 synthetic cases, including ten accepts and seven expected rejections, plus five deterministic byte-limit cases in the manifest. These are proposed interoperability tests pending joint ratification.

Read `manifest.json` and verify each listed file's SHA-256 and byte length on its exact UTF-8 bytes. Strictly decode the fixture container and use its `consumerContext` for the validator. Pass the half-open byte slice of the original top-level `envelope` object, braces included, to the byte entry point. Do not reserialize it. Container metadata is test-only. A successful validation reports `ACCEPT` with no error path. A failure must match both `expectedResult` and `expectedPath`. The manifest and fixture metadata agree.

The valid fixtures cover all seven roles, c0, policy-verified correction, retained originals, review-required alternatives, unverified drafts, ineligible c0, optional missing unit price, all four price states, pantry mapping, gate fallback and pre-resolution failure. A description token includes a supplementary Unicode character before the cited span to exercise code-point indexing. Cases 13 and 14 keep the exact decimal `0.750` with and without a literal unit in the linked quantity token. A price basis and pantry reference unit are present independently. The negative cases isolate invalid candidate and field links, unsupported review version, inconsistent probability availability, request/image mismatch and coordinate-frame mismatch. Expected dimensions are supplied as the test-only `expectedImageWidth` and `expectedImageHeight` pair where needed.

Validate each `envelope.presentation` independently with the unchanged V1 validator. All embedded payloads have valid V1 structure. Cases 15 and 16 fail only when validated with their intentionally different expected IDs. The frozen Presentation V1 fixture set remains canonical for bare V1. Both runtimes should exercise the same physical review fixture files after implementation.

## Byte-limit cases

For each `byteLimitCases` entry, take the exact `envelope` object bytes from `baseFixture`. Find the embedded top-level `presentation` object using Section 2.5 of the contract. Insert exactly `spaceCount` ASCII spaces (byte `0x20`) at the indicated location, keeping all other bytes unchanged.

| Location | Insert immediately |
| --- | --- |
| `insidePresentation` | After the embedded `presentation` opening brace |
| `beforePresentation` | Before that opening brace, outside the measured object |
| `insideWrapper` | After the review wrapper's opening brace |

Check the generated `bodySha256`, `bodyByteLength` and `presentationByteLength` in the manifest. Then use the base fixture context and verify the expected result and error path. The cases exercise inclusive 1 MiB embedded and 2 MiB wrapper limits, one byte over each limit, and whitespace outside the embedded object. The base object's literal UTF-8 text exercises byte counting.

Explicit response-schema selection, response mismatch and HTTP status/size handling belong in focused transport checks. Untouched versus explicitly unresolved state, bulk approval, inventory unit confirmation, both confirmation modes, atomic persistence, replay and deletion belong in Kotlin-local verification. The wire fixtures contain no local review or persistence state.
