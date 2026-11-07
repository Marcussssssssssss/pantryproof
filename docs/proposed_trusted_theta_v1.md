# Trusted Theta_A Structural Contract V1

Status: jointly approved structural implementation, synthetic-only. Operational
trust remains blocked.

This document describes the immutable records in
`pipeline/proposed/trusted_theta_contracts_v1.py`. They provide an auditable
shape for future trusted scorer evidence. They do **not** authenticate source
bytes, resolve an artifact, load a scorer, execute a model, establish empirical
validity, or authorize scoring, calibration, selection, correction or
persistence.

## Separation from existing configuration readiness

The existing `ConfigurationRefV1` remains the source-bound parent `Theta_A`
reference. Its `ConfigurationState.READY` value is structural metadata and is
not trusted-artifact readiness. `TrustedResolverStateV1` is a distinct enum with
`READY`, `NOT_READY` and `NOT_VALID` states.

A synthetic `TrustedScorerResolverResultV1(READY, ...)` proves only that the
record satisfies constructor invariants. It is not a real READY configuration.
No production resolver or trust root exists in this milestone.

## Manifest record

`TrustedThetaManifestV1` records:

- its schema, record, manifest ID and versions;
- the complete parent `Theta_A` reference;
- the exact `pantryproof-candidate-evidence-7-v1` schema and ordered
  `q_o, q_e, a_l, a_y, s_r, s_a, s_p` slots;
- versioned missing, not-applicable and pre-score-admission policies;
- scorer component and artifact identity, format, byte length and SHA-256
  metadata;
- the restricted canonical-JSON profile and declared manifest digest;
- registry, trust-entry, approval-authority and approval-record references;
- runtime, ABI and dependency-lock metadata;
- deterministic-execution and compatibility-policy references;
- numeric precision, scale and a closed cross-runtime rounding-policy name;
- offline snapshot, supersession and revocation references.

Kappa and Phi do not appear in this record. Calibration and selective
verification remain separate future stages.

All digest strings are required to be 64 lowercase hexadecimal characters and
to identify SHA-256. This is syntactic validation only. The implementation does
not recompute or authenticate those digests.

## Binding record

`TrustedScorerBindingV1` is the exact structural subset needed by a future raw
score record: parent Theta_A, manifest and artifact identity/digests, feature
schema and order, scorer component, and numeric policy. Its
`from_manifest(...)` factory copies those values without performing trust
resolution. A manifest carrying a revocation reference cannot produce a
structural READY binding.

## Resolver-result record

`TrustedScorerResolverResultV1` contains the source Theta_A, resolver component,
state, typed reason, retryability, optional registry snapshot, optional
manifest and binding, runtime fingerprint and ordered evidence references.

State rules are:

| State | Structural meaning |
|---|---|
| `READY` | Complete snapshot metadata, manifest, exact matching binding, runtime fingerprint and evidence references are present. Snapshot ID/version match the manifest's pinned offline snapshot. Reason is null and retryable is false. |
| `NOT_READY` | An approved prerequisite is absent. Binding is null, retryable is true, and the reason agrees with which snapshot/manifest evidence is actually present. |
| `NOT_VALID` | Available evidence contradicts the contract. Binding is null, retryable is false and contradiction evidence is present. |

`NOT_READY` reasons are limited to missing manifest, trust snapshot, artifact or
runtime dependency. Digest, signature/trust, Theta, schema, runtime,
revocation, rollback, supersession and determinism contradictions are
`NOT_VALID` reasons.

Reason/evidence coherence is fail-closed: missing trust snapshot requires all
snapshot metadata and the manifest to be null; missing manifest requires a
complete snapshot but a null manifest; missing artifact/runtime prerequisites
require both the pinned snapshot and structural manifest. A snapshot carried
with a manifest must use that manifest's offline snapshot ID and version.

Unexpected execution failures are not resolver states and must remain atomic
field-level failures in the scoring contract.

## Source equality and serialization boundary

The parent Theta_A, manifest and binding use complete immutable content
equality. A distinct but value-equal record is acceptable. Python object
identity is neither required nor serializable at this boundary.

The scoring codec explicitly serializes public fields. It must not serialize
private capture-once metadata or infer trust from IDs and hashes. Cross-runtime
decoding can establish only structural consistency and deterministic content,
not provenance authentication.

## Deferred operational work

The following remain outside this implementation:

- root-key or registry ownership and key lifecycle;
- signatures, registry access, snapshot distribution and rollback floors;
- revocation and supersession enforcement beyond structural references;
- artifact retrieval, verified-byte handles and TOCTOU protection;
- runtime inspection or dependency verification;
- a trained scorer, actual parameters or scorer execution;
- empirical validation, calibration, selection, controller and persistence;
- production creation of a READY resolver result.

`SM-06` therefore remains `BLOCKED`. This document and its tests do not change
the research status from `PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`.

## Synthetic conformance tests

The focused tests cover manifest identity and schema drift, digest grammar,
numeric policy, self-supersession, binding reconstruction, revocation,
READY/NOT_READY/NOT_VALID truth tables, Theta mismatch, nested-record
revalidation and the explicit distinction from legacy configuration readiness.

Synthetic IDs, digests and READY records in tests are contract fixtures only.
They must not be packaged or reported as operational approval evidence.
