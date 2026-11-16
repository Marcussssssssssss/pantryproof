"""Independent synthetic acceptance for Design 03 Closure 01.

All primary cases use the real shared source records. Adversarial mutation
uses object.__setattr__ only in tests, before or after scope capture.
"""

from dataclasses import fields, replace
from decimal import Decimal
import ast
import inspect
from pathlib import Path
import struct
import sys
from unittest.mock import patch

import pytest

from pipeline.contracts import (
    FieldStatus, OcrSourceToken, Point, ReceiptFieldName, StructuredField,
)
import pipeline.proposed.native_confidence_recipe_v1 as native
from pipeline.proposed.native_confidence_recipe_v1 import (
    NativeConfidenceErrorCodeV1 as Code,
    NativeConfidenceErrorV1 as Error,
    NativeConfidenceProfileV1 as Profile,
    NativeConfidenceRoleV1 as Role,
    NativeConfidenceScopeStateV1 as State,
    NativeConfidenceScopeV1 as Scope,
)
from pipeline.proposed.bounded_numeric_ingress_v1 import NumericIngressError


# Synthetic fixture values only. Every test profile is this vector or an
# explicitly recorded override; no limit here is an operational default.
PROFILE = dict(
    max_native_int_bits=64,
    max_native_text_chars=65,
    max_coefficient_digits=64,
    max_quantum_exponent_magnitude=340,
    max_attempts=256,
    max_work_units=1_000_000,
    max_live_text_chars=100_000,
    max_live_digit_cells=100_000,
    max_live_int_format_limb_cells=1024,
    max_live_binary_bytes=4096,
    max_registry_entries=128,
    max_source_anchors=128,
    max_retained_int_bits=8192,
)


# Independent diagnostic oracle, derived from the reviewed call sites rather
# than imported from the implementation's legality table. None is an actual
# role/limit value; each row expands only its explicitly listed alternatives.
DIAGNOSTIC_ROWS = (
    (Code.PROFILE_INVALID, "profile", (None,), (None, *PROFILE)),
    (Code.SCOPE_CLOSED, "scope", (None,), (None,)),
    (Code.SOURCE_BINDING_ERROR, "source", tuple(Role), (None,)),
    (Code.UNSUPPORTED_NATIVE_TYPE, "value", tuple(Role), (None,)),
    (Code.NONFINITE_VALUE, "value", tuple(Role), (None,)),
    (Code.INVALID_NUMERIC_SHAPE, "source", (None,), (None,)),
    (Code.RUNTIME_INCOMPATIBLE, "runtime", (None,), (None,)),
    (Code.RUNTIME_INCOMPATIBLE, "text", tuple(Role), (None,)),
    (Code.UNREGISTERED_DECIMAL, "registry", (None,), (None,)),
    (Code.CONSTRUCTION_FAILURE, "registry", tuple(Role), (None,)),
    (Code.INTERNAL_FAILURE, "scope", (None, *Role), (None,)),
    (Code.INTERNAL_FAILURE, "registry", (None,), (None,)),
    (Code.RESOURCE_LIMIT, "source", (None,), ("max_source_anchors",)),
    (Code.RESOURCE_LIMIT, "budget", (None,), ("max_attempts",)),
    (Code.RESOURCE_LIMIT, "registry", tuple(Role), ("max_registry_entries",)),
    (Code.RESOURCE_LIMIT, "value", tuple(Role), ("max_native_int_bits",)),
    (Code.RESOURCE_LIMIT, "recipe.coefficient", tuple(Role), ("max_coefficient_digits",)),
    (Code.RESOURCE_LIMIT, "recipe.quantum_exponent", tuple(Role),
     ("max_quantum_exponent_magnitude",)),
    (Code.RESOURCE_LIMIT, "budget", tuple(Role), (
        "max_retained_int_bits", "max_live_binary_bytes", "max_live_text_chars",
        "max_live_digit_cells", "max_live_int_format_limb_cells")),
    (Code.RESOURCE_LIMIT, "profile", (None,), ("max_work_units",)),
    (Code.RESOURCE_LIMIT, "budget", (None,), ("max_work_units",)),
    (Code.RESOURCE_LIMIT, "runtime", (None,), ("max_work_units",)),
    (Code.RESOURCE_LIMIT, "registry", (None, *Role), ("max_work_units",)),
    (Code.RESOURCE_LIMIT, "source", tuple(Role), ("max_work_units",)),
    (Code.RESOURCE_LIMIT, "value", tuple(Role), ("max_work_units",)),
    (Code.RESOURCE_LIMIT, "text", tuple(Role), ("max_work_units",)),
    (Code.RESOURCE_LIMIT, "recipe.coefficient", tuple(Role), ("max_work_units",)),
)
EMITTED_DIAGNOSTICS = tuple(
    (code, location, role, limit)
    for code, location, roles, limits in DIAGNOSTIC_ROWS
    for role in roles for limit in limits
)


def profile(**overrides):
    return Profile(**(PROFILE | overrides))


def token(value, suffix="0"):
    result = OcrSourceToken(
        receipt_id="synthetic-receipt", token_id="synthetic-token-" + suffix,
        original_text="synthetic literal",
        polygon=(Point(0.0, 0.0), Point(1.0, 0.0), Point(0.0, 1.0)),
        raw_confidence=None,
    )
    object.__setattr__(result, "raw_confidence", value)
    return result


def extractor(value, status=FieldStatus.EXTRACTED):
    result = StructuredField(
        field_id="synthetic-date", receipt_id="synthetic-receipt",
        field_name=ReceiptFieldName.PURCHASE_DATE, status=status,
        value="2026-11-16" if status is FieldStatus.EXTRACTED else None,
        source_token_ids=("synthetic-token-0",),
        unresolved_reason=None if status is FieldStatus.EXTRACTED else "Not observed.",
    )
    object.__setattr__(result, "confidence", value)
    return result


def scope(source, kind="ocr", **overrides):
    return Scope(profile=profile(**overrides),
                 ocr_sources=(source,) if kind == "ocr" else (),
                 extractor_sources=(source,) if kind == "extractor" else ())


def convert(context, source, kind):
    if kind == "ocr":
        return context.convert_ocr_confidence(source=source)
    return context.convert_extractor_confidence(source=source)


def expect_code(code, function, *args, **kwargs):
    with pytest.raises(Error) as caught:
        function(*args, **kwargs)
    assert caught.value.code is code
    return caught.value


@pytest.mark.parametrize("kind", ["ocr", "extractor"])
@pytest.mark.parametrize("value", [
    0, 1, -1, 10, -(2**63), 2**64-1,
    0.0, -0.0, 0.1, -1.25, 1.0, 10.0, 1e15, 1e20, 1e-7,
    0.30000000000000004, 0.9999999999999999, 1.0000000000000002,
    float.fromhex("0x1.fffffffffffffp+1023"),
    -float.fromhex("0x1.fffffffffffffp+1023"),
    float.fromhex("0x1.0000000000000p-1022"),
    float.fromhex("0x0.0000000000001p-1022"),
    -float.fromhex("0x0.0000000000001p-1022"),
    float.fromhex("0x1.a36e2eb1c432ep-14"),
])
def test_exact_tuple_oracle_and_source_preservation(kind, value):
    source = token(value) if kind == "ocr" else extractor(value)
    original_fields = tuple(getattr(source, field.name) for field in fields(source))
    context = scope(source, kind)
    produced = convert(context, source, kind)
    # Independent legacy conversion, not a second call to the adapter parser.
    assert produced.as_tuple() == Decimal(str(value)).as_tuple()
    assert context.check_registered(value=produced) is produced
    assert all(getattr(source, field.name) is original
               for field, original in zip(fields(source), original_fields))
    assert context.registry_size == 1
    assert context.live_int_format_limb_cells == 0


@pytest.mark.parametrize("value,sign,digits,exponent", [
    (0.0, 0, "0", -1), (-0.0, 1, "0", -1),
    (10, 0, "10", 0), (10.0, 0, "100", -1),
    (1e15, 0, "10000000000000000", -1),
    (float.fromhex("0x1.fffffffffffffp+1023"), 0, "17976931348623157", 292),
    (float.fromhex("0x0.0000000000001p-1022"), 0, "5", -324),
    (0.30000000000000004, 0, "30000000000000004", -17),
])
def test_literal_representation_oracles(value, sign, digits, exponent):
    source = token(value)
    actual = scope(source).convert_ocr_confidence(source=source).as_tuple()
    assert actual == (sign, tuple(map(int, digits)), exponent)
    if type(value) is float and value == 0:
        assert struct.pack("!d", value).hex() == (
            "8000000000000000" if sign else "0000000000000000")


@pytest.mark.parametrize("kind", ["ocr", "extractor"])
def test_missing_is_not_zero_and_has_no_construction(kind):
    source = token(None) if kind == "ocr" else extractor(None)
    context = scope(source, kind)
    assert context.work_units == 28
    with patch.object(native.IngressContextV1, "construct_decimal") as constructor:
        assert convert(context, source, kind) is None
        assert context.work_units == 33
        assert context.attempts == 1
        assert context.registry_size == 0
        assert context.live_text_chars == context.live_digit_cells == 0
        constructor.assert_not_called()


@pytest.mark.parametrize("status", [FieldStatus.MISSING, FieldStatus.UNRESOLVED])
def test_missing_or_unresolved_extractor_preserves_absence(status):
    source = extractor(None, status)
    assert scope(source, "extractor").convert_extractor_confidence(source=source) is None
    invalid = extractor(0.5, status)
    expect_code(Code.SOURCE_BINDING_ERROR, scope, invalid, "extractor")


class Hostile:
    def __str__(self):
        raise AssertionError("str dispatch")
    def __repr__(self):
        raise AssertionError("repr dispatch")
    def __float__(self):
        raise AssertionError("float dispatch")
    def __eq__(self, other):
        raise AssertionError("equality dispatch")
    def __hash__(self):
        raise AssertionError("hash dispatch")


class HostileInt(int):
    __str__ = __repr__ = __float__ = Hostile.__str__


class HostileFloat(float):
    __str__ = __repr__ = __float__ = Hostile.__str__


@pytest.mark.parametrize("kind", ["ocr", "extractor"])
@pytest.mark.parametrize("value", [
    pytest.param(True, id="bool"), pytest.param(False, id="false"),
    pytest.param(HostileInt(1), id="int-subclass"),
    pytest.param(HostileFloat(0.5), id="float-subclass"),
    pytest.param(Hostile(), id="hostile"),
    pytest.param(Decimal("0.5"), id="opaque-decimal"),
    pytest.param("0.5", id="string"),
])
def test_unsupported_types_never_format_or_coerce(kind, value):
    source = token(value) if kind == "ocr" else extractor(value)
    with patch.object(native, "_format_native") as formatter:
        expect_code(Code.UNSUPPORTED_NATIVE_TYPE, scope, source, kind)
        formatter.assert_not_called()


@pytest.mark.parametrize("kind", ["ocr", "extractor"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_before_format(kind, value):
    source = token(value) if kind == "ocr" else extractor(value)
    with patch.object(native, "_format_native") as formatter:
        expect_code(Code.NONFINITE_VALUE, scope, source, kind)
        formatter.assert_not_called()


@pytest.mark.parametrize("name", list(PROFILE))
@pytest.mark.parametrize("bad", [
    pytest.param(True, id="bool"), pytest.param(0, id="zero"),
    pytest.param(-1, id="negative"), pytest.param(2**31, id="ceiling"),
    pytest.param(1.0, id="float"), pytest.param(HostileInt(1), id="subclass"),
])
def test_each_profile_field_is_exact_positive_bounded_integer(name, bad):
    error = expect_code(Code.PROFILE_INVALID, profile, **{name: bad})
    assert error.limit_field == name


@pytest.mark.parametrize("name", list(PROFILE))
def test_profile_revalidated_before_scope_and_snapshotted(name):
    changed = profile()
    object.__setattr__(changed, name, 0)
    expect_code(Code.PROFILE_INVALID, Scope, profile=changed, ocr_sources=(), extractor_sources=())


@pytest.mark.parametrize("name", list(PROFILE))
def test_missing_required_profile_slot_is_closed_profile_error(name):
    changed = profile()
    object.__delattr__(changed, name)
    error = expect_code(Code.PROFILE_INVALID, Scope, profile=changed,
                        ocr_sources=(), extractor_sources=())
    assert error.limit_field == name and isinstance(error.__cause__, AttributeError)


def test_profile_snapshot_survives_later_caller_mutation():
    source = token(0.5)
    configured = profile(max_attempts=1)
    context = Scope(profile=configured, ocr_sources=(source,), extractor_sources=())
    object.__setattr__(configured, "max_attempts", 100)
    context.convert_ocr_confidence(source=source)
    error = expect_code(Code.RESOURCE_LIMIT, context.convert_ocr_confidence, source=source)
    assert error.limit_field == "max_attempts"


def test_profile_class_and_container_closure():
    class SubProfile(Profile):
        def __post_init__(self):
            pass  # An adversarial subclass bypasses construction checks.
    expect_code(Code.PROFILE_INVALID, Scope, profile=SubProfile(**PROFILE),
                ocr_sources=(), extractor_sources=())
    expect_code(Code.PROFILE_INVALID, Scope, profile=Hostile(), ocr_sources=(), extractor_sources=())
    expect_code(Code.INVALID_NUMERIC_SHAPE, Scope, profile=profile(),
                ocr_sources=[], extractor_sources=())
    expect_code(Code.INVALID_NUMERIC_SHAPE, Scope, profile=profile(),
                ocr_sources=(), extractor_sources=Hostile())


@pytest.mark.parametrize("width", [63, 64, 65])
@pytest.mark.parametrize("negative", [False, True])
def test_integer_width_bound_precedes_format(width, negative):
    value = (1 << width) - 1
    source = token(-value if negative else value)
    if width > 64:
        with patch.object(native, "_format_native") as formatter:
            assert expect_code(Code.RESOURCE_LIMIT, scope, source).limit_field == "max_native_int_bits"
            formatter.assert_not_called()
    else:
        assert scope(source).convert_ocr_confidence(source=source).as_tuple() == Decimal(str(source.raw_confidence)).as_tuple()


def test_large_admitted_integer_and_runtime_guard_boundary():
    source = token((1 << 4300) - 1)
    context = scope(source, max_native_int_bits=4300, max_native_text_chars=4301,
                    max_coefficient_digits=4300)
    value = context.convert_ocr_confidence(source=source)
    assert len(value.as_tuple().digits) == 1295
    assert value.as_tuple() == Decimal(str(source.raw_confidence)).as_tuple()
    assert sys.get_int_max_str_digits() == 4300
    # Independently establish runtime guard; these integers are not adapter inputs.
    assert len(str(10**4299)) == 4300
    with pytest.raises(ValueError):
        str(10**4300)
    assert sys.get_int_max_str_digits() == 4300


@pytest.mark.parametrize("width", [4299, 4300, 4301])
def test_profile_width_runtime_envelope(width):
    if width == 4301:
        expect_code(Code.PROFILE_INVALID, profile, max_native_int_bits=width,
                    max_native_text_chars=width+1)
    else:
        assert profile(max_native_int_bits=width, max_native_text_chars=width+1)


@pytest.mark.parametrize("text_cap", [64, 65, 66])
def test_text_profile_boundary(text_cap):
    if text_cap == 64:
        expect_code(Code.PROFILE_INVALID, profile, max_native_text_chars=text_cap)
    else:
        source = token(2**64-1)
        scope(source, max_native_text_chars=text_cap).convert_ocr_confidence(source=source)


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_coefficient_boundary_and_recoverable_failure(limit):
    source = token(10)
    context = scope(source, max_coefficient_digits=limit)
    if limit < 2:
        error = expect_code(Code.RESOURCE_LIMIT, context.convert_ocr_confidence, source=source)
        assert error.limit_field == "max_coefficient_digits"
        assert context.state is State.OPEN
        assert context.registry_size == context.live_text_chars == context.live_digit_cells == 0
    else:
        assert context.convert_ocr_confidence(source=source).as_tuple().digits == (1, 0)


@pytest.mark.parametrize("limit", [2, 3, 4])
def test_quantum_boundary(limit):
    source = token(0.001)
    context = scope(source, max_quantum_exponent_magnitude=limit)
    if limit < 3:
        error = expect_code(Code.RESOURCE_LIMIT, context.convert_ocr_confidence, source=source)
        assert error.limit_field == "max_quantum_exponent_magnitude"
        assert context.state is State.OPEN
    else:
        assert context.convert_ocr_confidence(source=source).as_tuple().exponent == -3


def test_hand_calculated_float_and_integer_work_schedule():
    source = token(0.5)
    context = scope(source)
    assert context.work_units == 37  # 26 + 1 + 1 + 1 + 8
    value = context.convert_ocr_confidence(source=source)
    # 1+1 entry; 2+1 source; 25 format; 121 parse; 1 scan; 2 construct; 4 publish.
    assert context.work_units == 195
    assert (context.live_text_chars, context.live_digit_cells) == (1, 1)
    assert context.check_registered(value=value) is value
    assert context.work_units == 201
    source = token(10)
    context = scope(source)
    assert context.work_units == 33  # 26 + 1 + 1 + 1 + four captured bits
    context.convert_ocr_confidence(source=source)
    assert context.work_units == 85  # +5 +12 +26 +2 +3 +4
    assert context.retained_int_bits == 4


@pytest.mark.parametrize("limit", [194, 195, 196])
def test_total_work_exact_boundary_prevents_construction(limit):
    source = token(0.5)
    context = scope(source, max_work_units=limit)
    original = native.IngressContextV1.construct_decimal
    with patch.object(native.IngressContextV1, "construct_decimal", autospec=True,
                      side_effect=original) as constructor:
        if limit < 195:
            error = expect_code(Code.RESOURCE_LIMIT, context.convert_ocr_confidence, source=source)
            assert error.limit_field == "max_work_units"
            assert context.state is State.EXHAUSTED
            constructor.assert_not_called()
        else:
            context.convert_ocr_confidence(source=source)
            assert context.work_units == 195
            assert constructor.call_count == 1


def test_repeated_rejections_keep_charges_and_attempts():
    source = token(0.001)
    context = scope(source, max_quantum_exponent_magnitude=1, max_attempts=2,
                    max_work_units=339)
    for expected_work in (188, 339):
        expect_code(Code.RESOURCE_LIMIT, context.convert_ocr_confidence, source=source)
        assert context.work_units == expected_work
        assert context.registry_size == context.live_text_chars == context.live_digit_cells == 0
        assert context.state is State.OPEN
    assert context.attempts == 2
    expect_code(Code.RESOURCE_LIMIT, context.convert_ocr_confidence, source=source)
    assert context.state is State.EXHAUSTED
    assert context.work_units == 339
    expect_code(Code.SCOPE_CLOSED, context.convert_ocr_confidence, source=source)
    assert context.work_units == 339


def test_repeated_rejections_cannot_bypass_work_budget():
    source = token(0.001)
    context = scope(source, max_quantum_exponent_magnitude=1, max_work_units=338)
    expect_code(Code.RESOURCE_LIMIT, context.convert_ocr_confidence, source=source)
    assert context.work_units == 188
    error = expect_code(Code.RESOURCE_LIMIT, context.convert_ocr_confidence, source=source)
    assert error.limit_field == "max_work_units"
    assert context.work_units == 218  # Second parse reservation was refused.
    assert context.state is State.EXHAUSTED and context.attempts == 2
    assert context.registry_size == context.live_text_chars == context.live_digit_cells == 0
    expect_code(Code.SCOPE_CLOSED, context.convert_ocr_confidence, source=source)
    assert context.work_units == 218


@pytest.mark.parametrize("limit", [119, 120, 121])
def test_live_text_boundary_before_format(limit):
    source = token(0.5)
    context = scope(source, max_live_text_chars=limit)
    with patch.object(native, "_format_native", wraps=native._format_native) as formatter:
        if limit < 120:
            expect_code(Code.RESOURCE_LIMIT, context.convert_ocr_confidence, source=source)
            formatter.assert_not_called()
        else:
            context.convert_ocr_confidence(source=source)
            assert context.live_text_chars == 1


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_live_digit_boundary_before_format(limit):
    source = token(0.5)
    context = scope(source, max_coefficient_digits=1, max_live_digit_cells=limit)
    with patch.object(native, "_format_native", wraps=native._format_native) as formatter:
        if limit < 2:
            expect_code(Code.RESOURCE_LIMIT, context.convert_ocr_confidence, source=source)
            assert context.live_text_chars == 0
            formatter.assert_not_called()
        else:
            context.convert_ocr_confidence(source=source)
            assert context.live_digit_cells == 1


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_live_integer_limb_boundary(limit):
    source = token(10)
    context = scope(source, max_live_int_format_limb_cells=limit)
    if limit < 2:
        with patch.object(native, "_format_native") as formatter:
            expect_code(Code.RESOURCE_LIMIT, context.convert_ocr_confidence, source=source)
            formatter.assert_not_called()
    else:
        context.convert_ocr_confidence(source=source)
    assert context.live_int_format_limb_cells == 0


@pytest.mark.parametrize("limit", [7, 8, 9])
def test_binary_snapshot_boundary(limit):
    source = token(-0.0)
    if limit < 8:
        expect_code(Code.RESOURCE_LIMIT, scope, source, max_live_binary_bytes=limit)
    else:
        context = scope(source, max_live_binary_bytes=limit)
        assert context.live_binary_bytes == 8
        context.close()
        assert context.live_binary_bytes == 0


@pytest.mark.parametrize("limit", [3, 4, 5])
def test_retained_integer_bit_boundary(limit):
    source = token(10)
    if limit < 4:
        expect_code(Code.RESOURCE_LIMIT, scope, source, max_retained_int_bits=limit)
    else:
        assert scope(source, max_retained_int_bits=limit).retained_int_bits == 4


@pytest.mark.parametrize("count", [1, 2, 3])
def test_anchor_count_boundary(count):
    sources = tuple(token(None, str(i)) for i in range(count))
    if count > 2:
        expect_code(Code.RESOURCE_LIMIT, Scope, profile=profile(max_source_anchors=2),
                    ocr_sources=sources, extractor_sources=())
    else:
        context = Scope(profile=profile(max_source_anchors=2), ocr_sources=sources,
                        extractor_sources=())
        assert context.source_count == count


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_registry_limit_and_repeated_fresh_objects(limit):
    source = token(0.5)
    context = scope(source, max_registry_entries=limit)
    values = [context.convert_ocr_confidence(source=source) for _ in range(limit)]
    assert len({id(value) for value in values}) == limit
    assert context.registry_size == limit
    with patch.object(native, "_format_native") as formatter:
        error = expect_code(Code.RESOURCE_LIMIT, context.convert_ocr_confidence, source=source)
        assert error.limit_field == "max_registry_entries"
        formatter.assert_not_called()


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_attempt_limit_includes_missing_and_registration_checks(limit):
    source = token(None)
    context = scope(source, max_attempts=limit)
    for _ in range(limit):
        expect_code(Code.UNREGISTERED_DECIMAL, context.check_registered, value=Hostile())
    assert context.attempts == limit
    expect_code(Code.RESOURCE_LIMIT, context.convert_ocr_confidence, source=source)
    assert context.state is State.EXHAUSTED


def test_work_limits_apply_to_setup_and_cumulative_storage():
    expect_code(Code.RESOURCE_LIMIT, Scope, profile=profile(max_work_units=25),
                ocr_sources=(), extractor_sources=())
    empty = Scope(profile=profile(max_work_units=26), ocr_sources=(), extractor_sources=())
    assert empty.work_units == 26
    source = token(0.5)
    context = scope(source, max_live_text_chars=120)
    context.convert_ocr_confidence(source=source)
    expect_code(Code.RESOURCE_LIMIT, context.convert_ocr_confidence, source=source)
    assert context.live_text_chars == 1
    source2 = token(10)
    expect_code(Code.RESOURCE_LIMIT, Scope, profile=profile(max_retained_int_bits=7),
                ocr_sources=(source2, token(10, "other")), extractor_sources=())


def test_cumulative_digit_binary_and_anchor_alias_accounting():
    source = token(0.5)
    context = scope(source, max_coefficient_digits=1, max_live_digit_cells=3)
    context.convert_ocr_confidence(source=source)
    context.convert_ocr_confidence(source=source)
    assert context.live_digit_cells == 2
    expect_code(Code.RESOURCE_LIMIT, context.convert_ocr_confidence, source=source)
    assert context.live_digit_cells == 2
    alias = token(source.raw_confidence, "alias")
    assert alias.raw_confidence is source.raw_confidence
    expect_code(Code.RESOURCE_LIMIT, Scope, profile=profile(max_live_binary_bytes=15),
                ocr_sources=(source, alias), extractor_sources=())
    context = Scope(profile=profile(max_live_binary_bytes=16),
                    ocr_sources=(source, alias), extractor_sources=())
    assert context.source_count == 2 and context.live_binary_bytes == 16


def test_recoverable_rejection_traceback_does_not_pin_formatted_buffers():
    source = token(0.001)
    context = scope(source, max_quantum_exponent_magnitude=1)
    error = expect_code(Code.RESOURCE_LIMIT, context.convert_ocr_confidence, source=source)
    traceback = error.__traceback__
    saw_conversion = False
    while traceback is not None:
        if traceback.tb_frame.f_code.co_name == "_convert":
            saw_conversion = True
            for name in ("text", "coefficient", "recipe", "result", "produced"):
                assert traceback.tb_frame.f_locals[name] is None
        traceback = traceback.tb_next
    assert saw_conversion
    assert context.state is State.OPEN


@pytest.mark.parametrize("kind", ["ocr", "extractor"])
@pytest.mark.parametrize("change", ["equal-copy", "native-equal-copy", "zero-sign", "missing"])
def test_source_binding_is_capture_once(kind, change):
    source = token(-0.0) if kind == "ocr" else extractor(-0.0)
    context = scope(source, kind)
    if change == "equal-copy":
        changed = replace(source)
        assert changed == source and changed is not source
    else:
        changed = source
        replacement = {"native-equal-copy": float("-0.0"), "zero-sign": 0.0,
                       "missing": None}[change]
        assert replacement is not (source.raw_confidence if kind == "ocr" else source.confidence)
        object.__setattr__(changed, "raw_confidence" if kind == "ocr" else "confidence", replacement)
    expect_code(Code.SOURCE_BINDING_ERROR, convert, context, changed, kind)
    assert context.state is State.ABORTED
    assert context.registry_size == context.source_count == 0


def test_missing_cannot_become_fabricated_and_status_cannot_change():
    source = token(None)
    context = scope(source)
    object.__setattr__(source, "raw_confidence", 0.9)
    expect_code(Code.SOURCE_BINDING_ERROR, context.convert_ocr_confidence, source=source)
    source = extractor(None)
    context = scope(source, "extractor")
    object.__setattr__(source, "status", FieldStatus.MISSING)
    expect_code(Code.SOURCE_BINDING_ERROR, context.convert_extractor_confidence, source=source)


def test_duplicate_foreign_wrong_role_and_shared_original_anchors():
    source = token(0.5)
    expect_code(Code.SOURCE_BINDING_ERROR, Scope, profile=profile(),
                ocr_sources=(source, source), extractor_sources=())
    expect_code(Code.SOURCE_BINDING_ERROR, Scope, profile=profile(),
                ocr_sources=(Hostile(),), extractor_sources=())
    a, b = scope(source), scope(source)
    first, second = (context.convert_ocr_confidence(source=source) for context in (a, b))
    assert first == second and first is not second
    expect_code(Code.UNREGISTERED_DECIMAL, a.check_registered, value=second)
    assert a.state is State.OPEN
    assert a.check_registered(value=first) is first
    expect_code(Code.SOURCE_BINDING_ERROR, b.convert_extractor_confidence, source=source)
    expect_code(Code.SOURCE_BINDING_ERROR, scope(source).convert_ocr_confidence, source=Hostile())


def test_registration_rechecks_live_source():
    source = token(0.5)
    context = scope(source)
    value = context.convert_ocr_confidence(source=source)
    object.__setattr__(source, "raw_confidence", 0.1)
    expect_code(Code.SOURCE_BINDING_ERROR, context.check_registered, value=value)
    assert context.state is State.ABORTED


@pytest.mark.parametrize("bad", [None, 42, "private-receipt", "text\ninjected", Hostile()])
def test_closed_diagnostic_tokens(bad):
    error = Error(Code.RESOURCE_LIMIT, bad, role=bad, limit_field=bad)
    assert str(error) == "RESOURCE_LIMIT: scope"
    assert error.role is error.limit_field is None


def test_diagnostic_closure_valid_roles_and_unknown_code():
    # The former all-role/all-limit cross product was the reviewed defect:
    # budget-role resource errors support only these five actual reservations.
    for role in Role:
        for name in ("max_retained_int_bits", "max_live_binary_bytes",
                     "max_live_text_chars", "max_live_digit_cells",
                     "max_live_int_format_limb_cells"):
            error = Error(Code.RESOURCE_LIMIT, "budget", role=role, limit_field=name)
            assert error.role is role and error.limit_field == name
    with pytest.raises(TypeError, match="^code must be a NativeConfidenceErrorCodeV1$"):
        Error(Hostile(), Hostile())
    with pytest.raises(TypeError):
        Scope(profile=profile(), ocr_sources=(), extractor_sources=()).convert_ocr_confidence(
            source=Hostile(), path="private-receipt")


@pytest.mark.parametrize("code,location,role,limit", EMITTED_DIAGNOSTICS)
def test_every_emitted_diagnostic_combination_is_preserved(code, location, role, limit):
    error = Error(code, location, role=role, limit_field=limit)
    assert (error.code, error.location, error.role, error.limit_field) == (
        code, location, role, limit)
    tokens = [code.value, location]
    if role is not None:
        tokens.append(role.value)
    if limit is not None:
        tokens.append(limit)
    assert str(error) == ": ".join(tokens)


def test_review_counterexample_reduces_to_fixed_fallback():
    error = Error(Code.NONFINITE_VALUE, "registry", role=Role.OCR_CONFIDENCE,
                  limit_field="max_work_units")
    assert (error.code, error.location, error.role, error.limit_field) == (
        Code.NONFINITE_VALUE, "scope", None, None)
    assert str(error) == "NONFINITE_VALUE: scope"


def test_invalid_diagnostic_cross_products_have_no_schema_escape():
    assert len(EMITTED_DIAGNOSTICS) == len(set(EMITTED_DIAGNOSTICS)) == 66
    oracle = set(EMITTED_DIAGNOSTICS)
    locations = ("scope", "profile", "runtime", "source", "value", "text",
                 "recipe.sign", "recipe.coefficient", "recipe.quantum_exponent",
                 "budget", "registry")
    checked = 0
    for code in Code:
        for location in locations:
            for role in (None, *Role):
                for limit in (None, *PROFILE):
                    error = Error(code, location, role=role, limit_field=limit)
                    expected = ((code, location, role, limit) if
                                (code, location, role, limit) in oracle else
                                (code, "scope", None, None))
                    assert (error.code, error.location, error.role, error.limit_field) == expected
                    checked += 1
    assert checked == 5082


@pytest.mark.parametrize("code", list(Code))
def test_fixed_fallback_is_idempotent_for_every_existing_code(code):
    error = Error(code, "scope")
    assert (error.code, error.location, error.role, error.limit_field) == (
        code, "scope", None, None)
    assert str(error) == code.value + ": scope"


def test_hostile_and_foreign_tokens_cannot_be_sanitized_into_an_emitted_combo():
    import enum
    class ForeignRole(enum.Enum):
        OCR_CONFIDENCE = "OCR_CONFIDENCE"
    class FakeRole:
        @property
        def __class__(self):
            raise AssertionError("class dispatch")
        __str__ = __repr__ = __hash__ = Hostile.__str__
        __eq__ = Hostile.__eq__
    class StringSubclass(str):
        __str__ = __repr__ = __hash__ = Hostile.__str__
        __eq__ = Hostile.__eq__
    # Enum members cannot be subclassed; a foreign Enum with the same label
    # and an object pretending to have that class must both remain invalid.
    for role in (Hostile(), ForeignRole.OCR_CONFIDENCE, FakeRole(),
                 "OCR_CONFIDENCE", StringSubclass("OCR_CONFIDENCE")):
        error = Error(Code.RESOURCE_LIMIT, "registry", role=role,
                      limit_field="max_work_units")
        assert (error.location, error.role, error.limit_field) == ("scope", None, None)
    for location, role, limit in (
        (StringSubclass("value"), Role.OCR_CONFIDENCE, None),
        ("value", Role.OCR_CONFIDENCE, Hostile()),
        ("value", Role.OCR_CONFIDENCE, "participant-001"),
        ("file:///private/receipt.jpg", Role.OCR_CONFIDENCE, None),
        ("value", Role.OCR_CONFIDENCE, StringSubclass("max_work_units")),
    ):
        error = Error(Code.NONFINITE_VALUE, location, role=role, limit_field=limit)
        assert str(error) == "NONFINITE_VALUE: scope"


def test_constructing_diagnostics_has_no_scope_or_accounting_effect():
    source = token(0.5)
    context = scope(source)
    value = context.convert_ocr_confidence(source=source)
    def snapshot():
        return (context.state, context.attempts, context.work_units,
                context.registry_size, context.source_count,
                context.live_text_chars, context.live_digit_cells,
                context.live_int_format_limb_cells, context.live_binary_bytes,
                context.retained_int_bits, context._ingress.constructions,
                context._ingress.work_units, context._ingress.registry_size)
    before = snapshot()
    for row in EMITTED_DIAGNOSTICS:
        code, location, role, limit = row
        Error(code, location, role=role, limit_field=limit)
        Error(code, "file:///private/receipt.jpg", role=Hostile(), limit_field=Hostile())
    assert snapshot() == before
    assert context.check_registered(value=value) is value


def test_actual_error_sites_emit_only_declared_combinations():
    class TrackedError(Error):
        def __init__(self, code, location, *, role=None, limit_field=None):
            assert (code, location, role, limit_field) in EMITTED_DIAGNOSTICS
            super().__init__(code, location, role=role, limit_field=limit_field)
            assert (self.location, self.role, self.limit_field) == (location, role, limit_field)
    with patch.object(native, "NativeConfidenceErrorV1", TrackedError):
        for kind in ("ocr", "extractor"):
            source = token(float("inf")) if kind == "ocr" else extractor(float("inf"))
            expect_code(Code.NONFINITE_VALUE, scope, source, kind)
            source = token(0.001) if kind == "ocr" else extractor(0.001)
            context = scope(source, kind, max_quantum_exponent_magnitude=1)
            expect_code(Code.RESOURCE_LIMIT, convert, context, source, kind)
            expect_code(Code.SOURCE_BINDING_ERROR, convert, context, Hostile(), kind)
        expect_code(Code.RESOURCE_LIMIT, Scope, profile=profile(max_work_units=25),
                    ocr_sources=(), extractor_sources=())


def test_runtime_pin_and_guard_recheck_never_change_setting():
    with patch.object(native.sys, "version", "unapproved runtime"):
        expect_code(Code.RUNTIME_INCOMPATIBLE, Scope, profile=profile(),
                    ocr_sources=(), extractor_sources=())
    source = token(0.5)
    context = scope(source)
    with patch.object(native.sys, "get_int_max_str_digits", return_value=0), \
            patch.object(native, "_format_native") as formatter:
        expect_code(Code.RUNTIME_INCOMPATIBLE, context.convert_ocr_confidence, source=source)
        formatter.assert_not_called()
    assert context.state is State.ABORTED
    assert sys.get_int_max_str_digits() == 4300


@pytest.mark.parametrize("failure", [
    pytest.param(MemoryError("synthetic"), id="memory"),
    pytest.param(KeyboardInterrupt(), id="interrupt"),
    pytest.param(RuntimeError("synthetic"), id="unexpected"),
])
def test_initialization_failure_never_publishes_scope(failure):
    with patch.object(native, "_verify_runtime", side_effect=failure):
        if isinstance(failure, RuntimeError):
            error = expect_code(Code.INTERNAL_FAILURE, Scope, profile=profile(),
                                ocr_sources=(), extractor_sources=())
            assert error.__cause__ is failure
        else:
            with pytest.raises(type(failure)) as caught:
                Scope(profile=profile(), ocr_sources=(), extractor_sources=())
            assert caught.value is failure


@pytest.mark.parametrize("bad_text", ["0.5junk", "+0.5", "01.0", "1e+999", "nan", "", "x"*25])
def test_unexpected_formatter_output_is_not_an_ordinary_outcome(bad_text):
    source = token(0.5)
    context = scope(source)
    with patch.object(native, "_format_native", return_value=bad_text):
        expect_code(Code.RUNTIME_INCOMPATIBLE, context.convert_ocr_confidence, source=source)
    assert context.state is State.ABORTED
    assert context.registry_size == 0


@pytest.mark.parametrize("failure", [
    pytest.param(MemoryError("synthetic"), id="native-memory"),
    pytest.param(KeyboardInterrupt(), id="interrupt"),
    pytest.param(RuntimeError("synthetic"), id="unexpected"),
])
def test_formatter_failures_abort_and_preserve_classification(failure):
    source = token(0.5)
    context = scope(source)
    with patch.object(native, "_format_native", side_effect=failure):
        if isinstance(failure, RuntimeError):
            error = expect_code(Code.INTERNAL_FAILURE, context.convert_ocr_confidence, source=source)
            assert error.__cause__ is failure
        else:
            with pytest.raises(type(failure)) as caught:
                context.convert_ocr_confidence(source=source)
            assert caught.value is failure
    assert context.state is State.ABORTED
    assert context.registry_size == context.source_count == 0
    expect_code(Code.SCOPE_CLOSED, context.convert_ocr_confidence, source=source)


@pytest.mark.parametrize("failure", [
    pytest.param(MemoryError("synthetic"), id="chained-memory"),
    pytest.param(KeyboardInterrupt(), id="interrupt"),
    pytest.param(ValueError("synthetic"), id="construction"),
])
def test_v1_exception_chain_and_no_publication(failure):
    source = token(0.5)
    context = scope(source)
    with patch("pipeline.proposed.bounded_numeric_ingress_v1.Decimal", side_effect=failure):
        if isinstance(failure, ValueError):
            error = expect_code(Code.CONSTRUCTION_FAILURE, context.convert_ocr_confidence, source=source)
            assert isinstance(error.__cause__, NumericIngressError)
            assert error.__cause__.__cause__ is failure
        else:
            with pytest.raises(type(failure)) as caught:
                context.convert_ocr_confidence(source=source)
            assert caught.value is failure
    assert context.state is State.ABORTED
    assert context.registry_size == 0


@pytest.mark.parametrize("after_append", [False, True])
def test_publication_failure_discards_private_partial_state(after_append):
    source = token(0.5)
    context = scope(source)
    previous = context.convert_ocr_confidence(source=source)
    original = context._publish
    def fail(produced):
        if after_append:
            original(produced)
        raise MemoryError("synthetic publication")
    with patch.object(context, "_publish", side_effect=fail):
        with pytest.raises(MemoryError):
            context.convert_ocr_confidence(source=source)
    assert context.state is State.ABORTED
    assert context.registry_size == context.source_count == 0
    assert context.live_text_chars == context.live_digit_cells == context.live_binary_bytes == 0
    expect_code(Code.SCOPE_CLOSED, context.check_registered, value=previous)


def test_close_and_keyword_only_api():
    source = token(0.5)
    context = scope(source)
    for method in (Scope.convert_ocr_confidence, Scope.convert_extractor_confidence):
        parameters = inspect.signature(method).parameters
        assert tuple(parameters) == ("self", "source")
        assert parameters["source"].kind is inspect.Parameter.KEYWORD_ONLY
    context.close()
    assert context.state is State.CLOSED
    assert context.source_count == context.registry_size == 0
    expect_code(Code.SCOPE_CLOSED, context.convert_ocr_confidence, source=source)


def test_legacy_consumers_keep_their_own_domains_and_missingness():
    from pipeline.proposed.feature_construction import _decimal_confidence, FeatureConstructionIntegrityError
    from pipeline.proposed.suspicion import _decimal_from_number
    for number in (-1.25, 0.0, -0.0, 0.5, 1.0, 2.0):
        source = token(number)
        produced = scope(source).convert_ocr_confidence(source=source)
        assert _decimal_from_number(number, "synthetic").as_tuple() == produced.as_tuple()
        if 0 <= number <= 1:
            assert _decimal_confidence(number, "synthetic").as_tuple() == produced.as_tuple()
        else:
            with pytest.raises(FeatureConstructionIntegrityError):
                _decimal_confidence(number, "synthetic")


def test_no_producer_consumer_or_inventory_execution():
    tree = ast.parse(Path(native.__file__).read_text(encoding="utf-8"))
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert [name for name in imports if name and name.startswith("pipeline")] == [
        "pipeline.contracts", "pipeline.proposed.bounded_numeric_ingress_v1"]
    from pipeline.proposed import suspicion, feature_construction
    from pipeline import layout_b2, baseline_b3
    with patch.object(suspicion, "detect_suspicion", side_effect=AssertionError("producer")), \
            patch.object(feature_construction, "_slot_values", side_effect=AssertionError("consumer")), \
            patch.object(baseline_b3, "parse_generic_date", side_effect=AssertionError("parser")), \
            patch.object(layout_b2, "_extracted_field", side_effect=AssertionError("extractor")):
        source = token(0.5)
        context = scope(source)
        assert context.convert_ocr_confidence(source=source).as_tuple() == (0, (5,), -1)
