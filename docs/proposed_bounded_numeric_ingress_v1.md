# Bounded Numeric Ingress Recipe Helper V1

**Classification:** D3 BOUNDED NUMERIC INGRESS — INTERNAL PROOF-OF-CONCEPT  
**Owner:** Leng Wei Heng  
**Design authority:** PANTRYPROOF_D3_V0_NUMERIC_INGRESS_BOUNDARY_DESIGN_01 §4–§6  
**Status:** Standalone proof-of-concept, not operationally wired  

## 1. Scope

This module provides a versioned, single-invocation Decimal construction
context with a checked profile and local counters.  It admits only
controlled finite recipes specified as exact `(sign, coefficient,
quantum_exponent)` triples and constructs `Decimal` values via the tuple
form `Decimal((sign, digit_tuple, exponent))`.

**What this module provides:**

- Private finite recipe constructor with explicit pre-work profile checks.
- Cumulative work-unit reservation for construction.
- Construction-count limits.
- Coefficient-length and exponent-magnitude bounds.
- Local exact-reference registration and identity verification.
- Exact type enforcement (bool rejection before int, hostile subclass
  rejection).
- Deterministic, ordered error categories with closed schema paths.
- Independence from the ambient `decimal` context (precision, rounding,
  Emin, Emax, traps).

**What this module does NOT provide:**

- Operational validation of real pipeline data.
- Full-object-graph admission or whole-route operand validation.
- Cross-process or cross-invocation safety guarantees.
- Source authentication or provenance verification.
- Production numeric ceilings or default limits.
- Public package export or pipeline integration.
- Wire-format validation or codec changes.
- Any modification to existing files or shared interfaces.

## 2. API

### `NumericIngressErrorCode` (enum)

Typed rejection categories in prescribed precedence order:

| Code | Description |
| --- | --- |
| `PROFILE_INVALID` | Profile limit is not a valid positive int within ceiling |
| `INVALID_SHAPE` | Type, grammar, or canonical-form violation |
| `RESOURCE_LIMIT` | Coefficient length, work budget, or construction budget exceeded |
| `UNREGISTERED_DECIMAL` | Object not registered in this context |
| `INVALID_NUMERIC_VALUE` | Exponent out of declared range |
| `CONSTRUCTION_ERROR` | Unexpected failure during tuple construction |

### `NumericIngressError(ValueError)`

Attributes:
- `code: NumericIngressErrorCode` — typed category
- `path: str` — closed schema path
- `limit_field: str | None` — name of the exceeded limit, if applicable

Error messages contain only declared code, path, and limit-name tokens.
The code must be an exact `NumericIngressErrorCode`, otherwise construction
raises `TypeError` with a fixed message without formatting the supplied value.

The synthetic operand-role vocabulary is exactly `field`, `field.amount`,
and `field.confidence`. `construct_decimal` and `check_registered` require
an exact native string naming one of these roles. Undeclared roles fail with
`PROFILE_INVALID` at `path` before construction, budget checks or identity lookup.

Direct exception construction accepts those role paths and their generated
`.sign`, `.coefficient`, and `.quantum_exponent` children. It also accepts
`profile`, `path`, and `profile.` followed by one of the four profile-field
names below. Every other path selects the fixed fallback `path`. No input
characters are substituted and no `?` token is emitted.

The exact limit-name vocabulary is `max_coefficient_digits`,
`max_exponent_magnitude`, `max_constructions`, and `max_work_units`.
Absent or undeclared limit names become `None` and are omitted from the message.
Exact-type checks precede membership checks, avoiding hostile conversion,
formatting, hashing and equality methods on rejected objects.

These roles describe this standalone synthetic proof. Vocabulary membership
establishes a diagnostic label only. Source authentication, historical
provenance and production-schema authority require separate evidence.

### `IngressProfileV1` (frozen dataclass)

Caller-supplied closed limits.  All fields must be explicit positive
`int` values, each bounded by `2**31 - 1`.  There are no defaults.

| Field | Description |
| --- | --- |
| `max_coefficient_digits` | Maximum number of coefficient digits (D) |
| `max_exponent_magnitude` | Maximum absolute value of quantum exponent |
| `max_constructions` | Maximum `construct_decimal` calls permitted |
| `max_work_units` | Cumulative work-unit budget |

### `IngressContextV1`

Single-invocation construction context.

Context initialization requires the exact `IngressProfileV1` class and
independently revalidates all four fields as exact positive native integers
within the existing helper ceiling. It snapshots them into private integers.
Later mutation of the caller's profile does not change the context's limits.
This assumes trusted context internals and quiescent initialization.

**Properties:**
- `constructions: int` — count of successful constructions
- `work_units: int` — cumulative work units consumed
- `registry_size: int` — number of registered Decimal objects

**`construct_decimal(sign, coefficient, quantum_exponent, path) → Decimal`**

Construct a bounded Decimal from an exact recipe:

1. Require a declared synthetic operand role, then check construction budget.
2. Exact type checks — `type(x) is int` (rejects `bool` subclass),
   `type(x) is str` (rejects subclasses).
3. Sign range check (must be 0 or 1).
4. Coefficient length check *before* scanning (rejects overlength
   as `RESOURCE_LIMIT`).
5. ASCII digit validation and canonical form (no redundant leading
   zeros except single `"0"`).
6. Exponent magnitude bounds.
7. Work-unit reservation (cost = 1 + coefficient length).
8. Digit tuple construction and `Decimal((sign, digits, exponent))`.
9. Counter commit and identity registration.

Failed construction does not change any counters or the registry.

**`check_registered(value, path) → Decimal`**

Verify that *value* is a registered Decimal from this context, using
exact object identity (`is`), not value equality.

## 3. Recipe Contract

A valid recipe consists of:

- **`sign`**: Exact native `int` value 0 (positive) or 1 (negative).
- **`coefficient`**: Exact native `str`, nonempty, containing only ASCII
  digits `0`–`9`, with no redundant leading zeros (except the single
  zero digit `"0"`).
- **`quantum_exponent`**: Exact native `int`.

The constructed value is `coefficient × 10^quantum_exponent` with the
separate sign.  All trailing zeros, the sign of zero, and the quantum
exponent are preserved exactly in the Decimal tuple representation.

No context-based conversion or rounding is involved in recipe
construction.

## 4. Validation Order and Error Precedence

Errors are reported in the following deterministic order:

0. **Declared operand role** → `PROFILE_INVALID` at `path`
1. **Construction budget** → `RESOURCE_LIMIT`
2. **Type shape** (sign, coefficient, exponent types) → `INVALID_SHAPE`
3. **Sign range** → `INVALID_SHAPE`
4. **Coefficient length** (before scanning) → `RESOURCE_LIMIT`
5. **Coefficient grammar** (digits and canonical form) → `INVALID_SHAPE`
6. **Exponent magnitude** → `INVALID_NUMERIC_VALUE`
7. **Work budget** → `RESOURCE_LIMIT`
8. **Tuple construction** → `CONSTRUCTION_ERROR`

## 5. Identity Registration

Each successfully constructed Decimal is registered in the context's
internal registry, keyed by `id()` and confirmed by `is`.

**What registration provides:**
- Proof that the object was constructed through this specific context.
- Exact object identity verification at consumption edges.

**What registration does NOT provide:**
- Source authentication or membership proof.
- Configuration authority or provenance.
- Cross-process or cross-invocation identity.
- Semantic correctness beyond construction validity.
- Protection against malicious in-process code modification.

The registry holds strong references.  If Python recycles an `id()` for
a new object (e.g., after the original is garbage-collected), the `is`
check prevents false positives.

## 6. Known Boundaries

- The `2**31 - 1` ceiling on profile limits is a practical upper bound;
  no production limit is proposed.
- Work-unit cost per construction is `1 + len(coefficient)`.  This does
  not model peak native allocation, elapsed time, or downstream
  processing cost.
- This proof-of-concept does not address the `4+5N+2E` operand
  validation count required for full V0 admission (Design 02 §4).
- The identity registry is per-context and per-invocation only.

## 7. Relationship to Existing Components

- **D3/V0 Preflight (Slice 01):** Independent.  The preflight validates
  whole-object shapes (`Point`, `OcrSourceToken`, etc.) and rejects all
  Decimal as `UNSUPPORTED_SCALAR`.  This module constructs bounded
  Decimals; they do not call each other.
- **Suspicion, ranking, feature construction:** These are Leng-owned
  Decimal producers.  Future adoption would wire them through this
  module's recipe interface.  No such wiring is included here.
- **OCR/B2/B3/V0 contracts:** Tai-owned or shared.  Not modified.
- **D1, D2, G2A:** Separate workstreams.  Not affected.
- **Scoring, constraints, controller:** Not wired.

## 8. Test Coverage

15 test categories with synthetic data only:

1. Valid bounded recipes (positive, negative, zero, trailing zeros)
2. Empty/malformed/non-ASCII coefficients
3. Coefficient digit-length boundaries (below/equal/one-over)
4. Quantum exponent boundaries (both ends)
5. Invalid sign values (2, -1, True, None)
6. Oversized integers and hostile subclasses
7. Signed zero preservation
8. Distinct quantum representations of equal values
9. Registered identity vs unregistered value-equal Decimal
10. Deterministic error precedence (first violation wins)
11. Budget exhaustion and failure atomicity
12. No Decimal construction before validation (monkeypatch instrumented)
13. No uncontrolled conversion/formatting/dispatch on rejected inputs
14. Repeated construction and bounded registry
15. Independence from ambient decimal context

Additional coverage includes profile revalidation and independent snapshots,
closed role and child-path membership, fixed diagnostic fallback, exact limit
names, hostile diagnostic objects, corrected permissive path tests, and
rejection before construction or identity work with unchanged counters.
