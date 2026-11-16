# Native confidence recipe V1

D3 BOUNDED NUMERIC INGRESS — STANDALONE SYNTHETIC PROOF-OF-CONCEPT

Authority: accepted `PANTRYPROOF_D3_NATIVE_CONFIDENCE_BOUNDARY_DESIGN_03`
and `PANTRYPROOF_D3_NATIVE_CONFIDENCE_BOUNDARY_DESIGN_03_CLOSURE_01`,
available as the owner's supplied conversational design baseline. Numeric
Ingress Design 01 and Bounded Revalidation Design 02 remain unchanged.

This component has no production wiring or package export. It does not
authenticate OCR, B2 execution, source bytes, configuration manifests, D3
membership or operational admission. It does not traverse whole receipts.

## Interface

```python
NativeConfidenceProfileV1(
    max_native_int_bits=...,
    max_native_text_chars=...,
    max_coefficient_digits=...,
    max_quantum_exponent_magnitude=...,
    max_attempts=...,
    max_work_units=...,
    max_live_text_chars=...,
    max_live_digit_cells=...,
    max_live_int_format_limb_cells=...,
    max_live_binary_bytes=...,
    max_registry_entries=...,
    max_source_anchors=...,
    max_retained_int_bits=...,
)
scope = NativeConfidenceScopeV1(
    profile=profile, ocr_sources=original_token_tuple,
    extractor_sources=original_field_tuple,
)
value = scope.convert_ocr_confidence(source=original_token)
value = scope.convert_extractor_confidence(source=original_field)
same_value = scope.check_registered(value=value)
scope.close()
```

All arguments above are keyword-only at the scope boundary. Limits have no
defaults. Profiles are frozen slotted records. Scope creation revalidates
and snapshots all 13 limits; subsequent caller profile mutation does not
change those snapshots. Exact positive integers at most `2**31-1` are
required. Booleans and subclasses fail before numeric dispatch.

## Native and source admission

Only exact `OcrSourceToken` and `StructuredField` source objects from
`pipeline.contracts` are supported. Anchor containers must be exact tuples.
Anchors are visited in supplied OCR order followed by supplied extractor
order; duplicate source objects are rejected. Fields, IDs, literal text and
polygons are not reconstructed or whole-record-revalidated.

Confidence admits exact builtin `int`, exact finite builtin `float`, or
`None`. Existing opaque Decimal, booleans, subclasses, strings and arbitrary
objects are rejected without coercion or representation inspection.

Each anchor captures the exact source and native confidence object once.
Float snapshots are eight network-order IEEE bytes, preserving negative
zero. Integer widths are captured before formatting. Extractor status is
captured by identity; only EXTRACTED, MISSING and UNRESOLVED are permitted.
MISSING/UNRESOLVED confidence must be None. EXTRACTED confidence may be None.

Conversion accepts no independent value argument. Foreign/value-equal source
copies, wrong-role sources, replacement confidence objects and changed
extractor statuses are rejected. Even a distinct equal-valued native object
is a substitution under this component-local policy. An unchanged original
source may be explicitly anchored in multiple independent scopes.

Missing confidence returns None and does not construct/register a Decimal.
No native confidence-domain limit is introduced: finite negative values and
values above one remain representable. Existing suspicion domains and
feature [0,1] checks remain the responsibility of their unchanged consumers.
Threshold Decimals and ranking-similarity Decimals are outside this API.

## Runtime requirements and representation

The accepted pin is CPython 3.13.7, build `bcee1c3`, MSC v.1944, 64-bit
AMD64; the complete `sys.version` string is checked. Unicode is 15.1.0.
Requirements include radix 2, 53 mantissa bits, max/min exponent 1024/-1021,
rounds 1, short float repr and an IEEE little-endian eight-byte double.
Native integer digits are 30-bit/four-byte; default guard 4300, check
threshold 640 and active integer-string guard 4300. Decimal module 1.70,
libmpdec 4.0.0 and capacity sufficient for the profile are required.

The active integer-string guard is rechecked on every public conversion or
registration attempt. A mismatch aborts before source processing. No global
guard, Decimal context, rounding or other runtime setting is changed.

`B = max_native_int_bits` must be at most 4300; thus `ceil(B/30) <= 1000`
also holds. This keeps the inspected CPython integer formatter below its
large-integer branch and conservatively below the decimal digit guard.
`max_native_text_chars >= max(24, B+1)` is required. These are synthetic
runtime-compatibility restrictions, not operational confidence policy.

For admitted integer width b, text envelope U is max(1,b+1), including sign.
For finite floats, U is 24 ASCII characters. Binary64 shortest round-trip
significant digits need at most 17; scientific exponent lies in [-324,308].
Fixed-format padding also keeps the canonical coefficient at most 17 digits.
The conservative absolute quantum bound is 340 (=324+16).

The adapter uses builtin `str(value)`, preserving current
`Decimal(str(value)).as_tuple()` behavior. It never uses `Decimal.from_float`,
normalize, quantize, rounding or exponent-sized zero expansion.

Generated ASCII integer grammar: `-?(0|[1-9][0-9]*)`.

Generated finite-float grammar:
`-?((0|[1-9][0-9]*)\.[0-9]+|[1-9](\.[0-9]+)?e[+-][0-9]{2,3})`.

This parser grammar is used only for text from the pinned builtin formatter;
there is no public text-input API. Parse sign, mantissa and at most three
exponent digits; concatenate mantissa digits, strip only redundant leading
zeros, preserve trailing zeros and use quantum = explicit exponent minus
fractional-digit count. All-zero coefficients retain one zero. Unexpected
generated text aborts as RUNTIME_INCOMPATIBLE.

Examples: native 10 -> (0,"10",0); 10.0 -> (0,"100",-1);
-0.0 -> (1,"0",-1); minimum subnormal -> (0,"5",-324).
Complete tuple equivalence, including zero sign and quantum, is required.

## Exact logical charge schedule

Work is a versioned logical measure, not CPU cycles or a time bound.
Let a be captured anchors, S total anchors, r successful results, b native
integer width, U the text envelope, d actual canonical coefficient length,
n=ceil(b/30), and s=1+n+floor(n/99). Float scratch s is zero.

| Event | Nonrefundable work charge before the event |
| --- | ---: |
| Fixed initialization | 26 (one setup, 13 profile checks, ten runtime groups, two containers) |
| Anchor duplicate scan | 1+a |
| Anchor read/type/status check | 1 |
| Integer width inspection | 1 |
| Accepted integer capture | b |
| Float finite check | 1 |
| Float snapshot processing | 8 |
| Public operation entry | 1 and one attempt |
| Runtime guard recheck | 1 |
| Source lookup | 1+S |
| Live source/native/status check | 1 |
| Integer formatting | 1+n*s+2*n+s+U |
| Float formatting | 25 (one foreign-call token plus 24-character envelope) |
| Parsing/coefficient preparation | 1+5*U |
| V1 coefficient scan | d |
| V1 construction | 1+d |
| Registration/publication | 4*(r+1) |
| Registered-result lookup | 1+2*r, plus entry/guard and source check if found |

The captured immutable native object's width proof is reused on conversion;
the width/capture charge is not repeated. Each repeated conversion still
charges entry, source checks, formatting, parsing and construction anew.
V1 scan/construction/publication work is fully prepaid before invoking V1.
The private V1 context independently retains its own existing counters.

Before formatting, reserve 5*U text/character slots, 2*min(D,U) digit cells
where D is the coefficient cap, and integer scratch s. The parser uses two
bounded passes, a bounded character collection, one join and at most one
leading-zero slice. Temporary buffers are released only after local buffer
references are cleared. Recoverable-error tracebacks must not retain them.

Each successful retained result uses d text slots, d logical Decimal digit
cells and one registry entry. Construction temporarily reserves a result
slot before publication. Captured sources retain one anchor slot each,
integer widths summed per anchor, and eight binary bytes per float anchor.
Aliases in distinct source records are charged per captured occurrence.

Work reservations commit immediately before work and are never refunded,
including failed conversions. Temporary reservations are released when no
longer live. At equality a reservation succeeds; one over fails before the
next disallowed operation. Subtraction-based remaining-capacity checks are
used. None consumes entry/guard/source charges and no format/construction
charges. Registration checks also consume attempts/work.

Expected per-value coefficient/quantum rejection can leave an open scope;
spent work remains spent. Exhausted cumulative attempt/work/live-storage or
registry capacity stops further processing. Repeated failures cannot reset
budgets. Fixed-cost refusals after exhaustion and caller-side repeated scope
creation are outside a single invocation's cumulative work guarantee.

These budgets bound logical text/digit/reference quantities and known
integer-format scratch cells. They do not bound allocator headers,
fragmentation, native dtoa scratch, dictionary capacity bytes, GC timing or
transitive memory of the pre-existing source records. No byte-exact peak
native-memory, execution-time or operational capacity claim is made.

## Identity, diagnostics and failures

The V1 context is private. It uses unchanged `field.confidence` diagnostics;
V1's synthetic vocabulary is not extended into an operational schema.
The adapter retains strong references to produced Decimals and checks `is`.
Equal foreign Decimals are rejected without inspecting their representation.
Live source identity is rechecked before admitting an already produced value.
There is no value-based memoization or serialized proof token.

Local roles: OCR_CONFIDENCE and EXTRACTOR_CONFIDENCE. Closed locations:
scope, profile, runtime, source, value, text, recipe.sign,
recipe.coefficient, recipe.quantum_exponent, budget, registry.
Only the 13 declared limit names can appear in a limit diagnostic. Unknown
tokens use fixed fallbacks without str/repr/hash/equality dispatch on them.
The public conversion methods take no path/role argument.

Amendment 01 additionally enforces the complete combination matrix below.
Independent membership of each token is insufficient. Invalid raw tokens
must not be sanitized into a different valid emitted combination.

Local error codes: PROFILE_INVALID, SCOPE_CLOSED, SOURCE_BINDING_ERROR,
UNSUPPORTED_NATIVE_TYPE, NONFINITE_VALUE, INVALID_NUMERIC_SHAPE,
RESOURCE_LIMIT, RUNTIME_INCOMPATIBLE, UNREGISTERED_DECIMAL,
CONSTRUCTION_FAILURE and INTERNAL_FAILURE. Messages contain no source IDs,
source text or numeric values. Standard tracebacks/causes are not automatic
privacy-sanitized logging and must not be published as source evidence.

Precedence: scope state, attempt budget, entry/guard work and runtime,
source lookup/check work and exact binding, missingness, result capacity,
temporary reservations, formatting, parsing, coefficient/quantum limits,
V1 scan/construction/publication reservations, construction, full association,
then return. Scope creation checks profile/runtime/container shape before
capturing anchors. Invalid anchors never publish a scope.

States are OPEN, EXHAUSTED, ABORTED and CLOSED. Source substitution or runtime
incompatibility aborts. Expected per-value rejection preserves charges and
does not necessarily exhaust. Expected foreign Decimal admission rejection
leaves an otherwise open scope open. Construction/internal failures abort.
MemoryError and interrupts abort and propagate. An underlying MemoryError
chained by V1 is propagated as the original native resource failure.

V1 can update counters before registry insertion. No V1 transactionality is
claimed. A failure discards access to the private V1 context and clears all
adapter entries/anchors. No new successful result is returned, even if an
internal append occurred before failure. Earlier raw immutable Decimals
remain ordinary values but cannot be admitted through an aborted scope.
close releases owned references. Work/attempt history is not reset.

The ownership assumption is exclusive, synchronous, quiescent application
use. Deliberate coordinated mutation of trusted code/private metadata,
historical mutation followed by restoration, and malicious in-process
introspection are outside this local integrity guarantee.

## Synthetic profiles and independent verification

The base test vector, in profile field order, is:

`(64, 65, 64, 340, 256, 1000000, 100000, 100000, 1024, 4096, 128, 128, 8192)`.

All tests use this exact vector or explicit overrides in the test source:

| Field | Override values (including deliberately invalid profiles) |
| --- | --- |
| Native bits | 4299, 4300, 4301 |
| Text cap | 64, 65, 66; paired large-width caps 4300, 4301, 4302 |
| Coefficient cap | 1, 2, 3, 4300 |
| Quantum cap | 1, 2, 3, 4 |
| Attempts | 1, 2, 3 |
| Work | 25, 26, 194, 195, 196, 338, 339 |
| Live text | 119, 120, 121 |
| Live digits | 1, 2, 3 |
| Integer scratch limbs | 1, 2, 3 |
| Binary snapshots | 7, 8, 9, 15, 16 |
| Registry entries | 1, 2, 3 |
| Source anchors | 2 |
| Retained integer bits | 3, 4, 5, 7 |

Each of the 13 fields also has exact-type/range rejection cases for True,
0, -1, 2**31, 1.0 and a hostile int subclass; forced post-construction zero
mutation is tested. A caller's attempted max_attempts mutation to 100 after
scope creation verifies snapshot independence. No synthetic number is an
approved production limit.

Missing required profile slots are also rejected as closed PROFILE_INVALID
errors, with the original AttributeError retained as the cause.

Primary tests use actual shared source classes. Independent oracles include
legacy Decimal(str(native)).as_tuple(), literal expected tuples/IEEE bytes,
guard-boundary behavior and hand-calculated work totals (float 0.5: setup
37, conversion total 195, registered check total 201; integer 10: setup 33,
conversion total 85). Fault injection covers formatting, initialization,
V1 construction and publication including append-before-failure.

Tests cover all resource boundaries, missingness, subclasses, opaque Decimal,
source/native/status substitution, cross-context identity, cumulative live
storage, repeated failures, closed diagnostics, runtime mismatch and no
producer/consumer calls. Existing consumer domain tests remain independent.

Run with the pinned interpreter, bytecode/plugin autoload/cache disabled:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTEST_ADDOPTS = ''
& '.\.venv\Scripts\python.exe' -B -m pytest -p no:cacheprovider -o 'addopts=' -q tests/test_proposed_native_confidence_recipe_v1.py
```

Independent review is required. There is no D2/D3 activation, shared-contract
change, scoring, calibration, selection, controller, inventory, persistence,
Android integration, real-receipt processing or evaluation authorization.

## Original implementation verification record (pre-amendment)

Implementation baseline: feature/self-correction at
e2aaab4cb50ebc5c69820c4e4114e3a93c4027d0. PR #57 was independently verified
MERGED at acf949665cc50bd827bc3831bd5d13acfab98388. The cached main reference
is stale; live main was 3e24945afdea1b7bfe019cee8e925ec2b289e1f4. No fetch or
baseline synchronization occurred.

Using the interpreter/options above, the final dedicated suite passed 277
tests. All test_proposed_*.py files passed 1329 tests plus 371 subtests.
The focused existing V1/suspicion/features/shared/core-contract suites passed
284 tests plus 84 subtests. Baseline/core/OCR suites passed 158 tests plus
92 subtests. These overlapping runs must not be summed.

The complete tests directory reported 1724 passed, 1625 subtests passed and
33 failures: the existing presentation canonical-fixture test's 32 manifest
subtests plus its aggregate assertion. All 32 working fixture files have
CRLF-only differences from their canonical Git blobs. All 32 Git blobs
match manifest hashes and byte lengths. The failure was reproduced in a
fresh process running only that pre-existing test, without importing this
adapter. Example: fixture 01 is 6427 worktree bytes versus 6246 canonical
bytes. core.autocrlf is true. No fixture, manifest or Git setting was changed.
The full suite is therefore not reported as passing.

Additional commands, with the same interpreter, -B, cache and plugin settings:

```powershell
# Focused existing regressions
python -B -m pytest -p no:cacheprovider -o 'addopts=' -q tests/test_proposed_bounded_numeric_ingress_v1.py tests/test_proposed_suspicion.py tests/test_proposed_feature_construction.py tests/test_proposed_contracts.py tests/test_contracts.py
# Baseline/core
python -B -m pytest -p no:cacheprovider -o 'addopts=' -q tests/test_contracts.py tests/test_ocr_adapter.py tests/test_baseline_b1.py tests/test_layout_b2.py tests/test_baseline_b3.py
# Broad proposed-method set (PowerShell supplies the file arguments)
$proposedFiles = @(Get-ChildItem -LiteralPath tests -Filter 'test_proposed_*.py' | Sort-Object Name | ForEach-Object {$_.FullName})
python -B -m pytest -p no:cacheprovider -o 'addopts=' -q @proposedFiles
# Complete synthetic suite; existing fixture failure described above
python -B -m pytest -p no:cacheprovider -o 'addopts=' -q --tb=no tests
```

The shorthand python in this block denotes the pinned .venv executable,
not global Python. Non-writing compile(), UTF-8/BOM/final-newline and trailing
whitespace checks passed on the new Python artifacts. No Git integration
or independent-review approval is implied by these local results.

## Independent review amendment 01: exact diagnostic combinations

Finding D3-NCR-REVIEW-01: the initial constructor checked each token in
isolation. It therefore accepted NONFINITE_VALUE at registry with an OCR
role and max_work_units. The amendment adds an explicit local emission
matrix without changing any numeric, source, runtime or accounting path.

In the following matrix, N means None, O means OCR_CONFIDENCE and E means
EXTRACTOR_CONFIDENCE. Alternatives expand only within the same row. P means
the 13 declared profile fields in the interface above. There are exactly
66 emitted combinations, including resource-helper call-site expansions.

| Code | Location | Role | Limit field |
| --- | --- | --- | --- |
| PROFILE_INVALID | profile | N | N or P |
| SCOPE_CLOSED | scope | N | N |
| SOURCE_BINDING_ERROR | source | O, E | N |
| UNSUPPORTED_NATIVE_TYPE | value | O, E | N |
| NONFINITE_VALUE | value | O, E | N |
| INVALID_NUMERIC_SHAPE | source | N | N |
| RUNTIME_INCOMPATIBLE | runtime | N | N |
| RUNTIME_INCOMPATIBLE | text | O, E | N |
| UNREGISTERED_DECIMAL | registry | N | N |
| CONSTRUCTION_FAILURE | registry | O, E | N |
| INTERNAL_FAILURE | scope | N, O, E | N |
| INTERNAL_FAILURE | registry | N | N |
| RESOURCE_LIMIT | source | N | max_source_anchors |
| RESOURCE_LIMIT | budget | N | max_attempts |
| RESOURCE_LIMIT | registry | O, E | max_registry_entries |
| RESOURCE_LIMIT | value | O, E | max_native_int_bits |
| RESOURCE_LIMIT | recipe.coefficient | O, E | max_coefficient_digits |
| RESOURCE_LIMIT | recipe.quantum_exponent | O, E | max_quantum_exponent_magnitude |
| RESOURCE_LIMIT | budget | O, E | max_retained_int_bits, max_live_binary_bytes, max_live_text_chars, max_live_digit_cells, max_live_int_format_limb_cells |
| RESOURCE_LIMIT | profile | N | max_work_units |
| RESOURCE_LIMIT | budget | N | max_work_units |
| RESOURCE_LIMIT | runtime | N | max_work_units |
| RESOURCE_LIMIT | registry | N, O, E | max_work_units |
| RESOURCE_LIMIT | source | O, E | max_work_units |
| RESOURCE_LIMIT | value | O, E | max_work_units |
| RESOURCE_LIMIT | text | O, E | max_work_units |
| RESOURCE_LIMIT | recipe.coefficient | O, E | max_work_units |

Derivation: profile errors name the invalid profile field; source capture and
lookup supply O/E; container-shape errors are roleless; global scope/runtime
checks are roleless; conversion text/construction failures have O/E; internal
errors can arise at scope creation, conversion, or registered lookup.
_exhaust supplies anchor/attempt/result limits, _reserve supplies the five
live/retained limits, and _charge supplies max_work_units only at the listed
call-site locations and roles. No emitted site needs broader combinations.

For a valid code with any unsupported combination, preserve the code and
reduce the remaining fields to location scope, role None, limit None. The
message is exactly CODE: scope. This fixed fallback exists for every code;
it is not an additional claim that such a combination is an ordinary emitted
failure. It is idempotent. Invalid codes retain the fixed TypeError.

Validate exact string/enum types and bounded lengths before hashing or
comparing the combination. Role subclasses, foreign enums and objects
pretending to have the enum class are not accepted. No unrelated limit can
be attached to NONFINITE_VALUE or another ordinary error. PROFILE_INVALID
retains its explicitly legitimate profile-field diagnostics.

Tests independently declare the 66-row expansion, preserve every valid
tuple and check 5082 code/location/role/limit cross products, fixed fallbacks,
hostile tokens, source-data non-disclosure, actual emitted sites and scope
counter/state immutability during error construction. Three focused tests
failed against the original constructor before correction. The previous
diagnostic test's all-role/all-limit resource cross product was narrowed to
the five actual budget reservations because that expectation embodied the
reviewed defect; its preservation assertions and every numeric/source test
remain intact.

Final amendment results with the pinned runtime and non-writing options:

| Suite | Result | Exit |
| --- | --- | ---: |
| Dedicated native-confidence | 359 passed | 0 |
| Existing V1/suspicion/features/shared/core contracts | 284 passed; 84 subtests passed | 0 |
| Baseline/core/OCR | 158 passed; 92 subtests passed | 0 |
| Broader proposed-method | 1411 passed; 371 subtests passed | 0 |
| Complete synthetic suite | 1806 passed; 1625 subtests passed; 33 reported failures | 1 |
| Isolated existing canonical-fixture test | 32 failed subtests and one failed aggregate assertion | 1 |

These overlapping suites must not be summed. There are no adapter test
failures. The full suite is not passing on this checkout.

The CRLF issue is separate and independently reproduced without importing
the adapter. HEAD e2aaab4 has no .gitattributes, and effective text/eol
attributes on the canonical fixture path are unspecified. core.autocrlf is
true. All 32 working fixtures differ from canonical Git bytes only by CRLF;
all 32 canonical blobs match the frozen manifest hashes and byte lengths.

Remote main at 3e24945afdea1b7bfe019cee8e925ec2b289e1f4 contains attribute
blob 1a0ce94bf147698fc770b83446e1ee1ed7f5c060, introduced by commit
3d01595cbc64a63e696044c9f7c3a91fffca68a2:

```gitattributes
/tests/fixtures/receipt_presentation_v1/v1/manifest.json text eol=lf
/tests/fixtures/receipt_presentation_v1/v1/fixtures/*.json text eol=lf
```

A separately authorized, controlled main-based checkout with these rules
applied, canonical bytes reverified and the reviewed adapter carried over
is needed for authoritative main-based full-suite validation. No checkout,
fetch, fixture rewrite, attribute edit or Git configuration change was made
in this amendment. Local adapter technical review can proceed independently
of that separate integration-validation gate.

PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN
