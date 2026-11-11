# D1 purchase-date source discovery

D1 implements the source-only profile accepted in the 70,546-byte D0 contract
`PANTRYPROOF_D0_FINAL_CONTRACT_DECISION_CANDIDATE_2026-11-11.md`.
Its raw SHA-256 is
`EF23BFA3D5628F028773AF2D8F2977509C2B8386857E2B8E4F650711D333EBBA`.

## Calling the profile

Import `discover_purchase_date_sources_v1` and
`validate_date_discovery_result_v1` directly from
`pipeline.proposed.purchase_date_source_discovery_v1`. Supply the exact
stored `ReceiptSourceEvidence`, `B2ExtractionResult`, `ConfigurationRefV1`,
and a `DateDiscoveryMethodProfileV1` using the accepted literals and full
`DateDiscoveryLimitsV1` vector. A caller may supply a source-consistent
`CandidateRecordV1` as `existing_c0`. The profile requires its independently
computed `profile_content_id`. Its preimage is the profile's typed projection
with that ID omitted, prefixed by `pantryproof-date-discovery-profile-v1` and
one NUL byte.

The result retains the five input roots, the exact B2 purchase-date field
when available, and the exact tokens and supplied original. An EXTRACTED
date without a supplied c0 has its own source-only state. MISSING and
UNRESOLVED preserve their stored field and reason. Genuine insufficient
fallback retains its gate and disposition, emits two context diagnostics,
and skips the scan. Source-consistent c0 association and explicit Theta_A
equality establish consistency of the supplied graph. They provide no
independent D3 membership, historical configuration provenance or execution
attestation.

## Evidence and identity

Each stored OCR region produces one observation in tuple order. The approved
single-region DATE, PURCHASE DATE and TRANSACTION DATE grammar preserves raw
code-point spans. The public B3 parser receives the literal body or whole
region. Its day-first then month-first ambiguity order is preserved.
Repeated ISO values group by first occurrence with all contributing
derivations. These unranked proposals carry `SOURCE_DISCOVERY_ONLY` authority.

The local typed JSON projection retains declaration-complete fields and
explicit nulls. It distinguishes enum tokens, strings, booleans, integers
and binary64 values, including signed zero. Sorted ASCII keys, compact
separators and UTF-8 scalar encoding define canonical bytes. Each hash
preimage is ASCII domain, one NUL byte, and the canonical projection.
The context envelope holds all five roots, including both occurrences of
the source in a structured graph. Every record preimage omits only its own
ID. The result includes complete children and their IDs.

| ID | Domain |
|---|---|
| Profile | `pantryproof-date-discovery-profile-v1` |
| Context | `pantryproof-date-discovery-context-v1` |
| Original anchor | `pantryproof-date-original-anchor-v1` |
| Observation | `pantryproof-date-source-observation-v1` |
| Derivation | `pantryproof-date-source-derivation-v1` |
| Proposal | `pantryproof-date-source-proposal-v1` |
| Result | `pantryproof-date-source-result-v1` |

The encoding is Python-local under `pantryproof-date-source-typed-json/1`.
The pinned CPython build is `3.13.7 (tags/v3.13.7:bcee1c3, Aug 14 2025,
14:15:11) [MSC v.1944 64 bit (AMD64)]` with Unicode `15.1.0`.
The parser ruleset is `B3-generic-rules-v0`, its reviewed raw module hash
is `f417ca5158af5fcb0a0f5757a01e75b708f59a07bc358d93a7eb7ef04c4abb4e`,
and the structured extractor is `B2-layout-graph-v0`. The runtime checks
the exact profile declarations and runtime versions. Raw module bytes
are checked during preflight.

## Validation and failure

The exact limit vector is `(500000, 48, 4194304, 512, 64, 2048, 512, 512,
1024, 2048, 16777216)` in `DateDiscoveryLimitsV1` field order. Occurrence
counting charges aliases each time. The canonical budget includes the
domain and NUL. The encoder streams bounded chunks. Equal limits pass
and overflow raises a closed resource error at the applicable schema path.

Validation checks top-level types and profile, bounded nested shapes and
versions, source and B2 links, Theta_A and original association, then
the profile and context IDs before parser work. Scanning and append
limits precede child and result hashing. Reuse reconstructs the complete
expected result from the retained roots and compares fields and source
references. Supplied collection lengths are checked before iteration.
Use quiescent inputs throughout a call. An exception returns no partial
result. Error messages contain only the closed code, with separate schema
path and optional resource-limit field.

## Synthetic conformance scope

The new suite covers D1-T01 through D1-T19 with synthetic typed graphs,
an independent lexical regex, explicit calendar outcomes, independently
listed canonical fields and separate JSON/SHA-256 oracles. It checks the
reachable token, point, code-point and output maxima, plus isolated guards
for limits whose full-graph boundaries are unreachable or depend on other
caps. D1-T20 is the external before/after Git and file-hash comparison
recorded in the implementation report. Only the new synthetic suite is
within this execution scope.

This component emits observations and unranked proposals only. Existing
production, scoring, D3, persistence and Android interfaces are outside
its authority.
