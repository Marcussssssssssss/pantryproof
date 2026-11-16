"""Synthetic tests for bounded numeric ingress recipe helper v1.

D3 BOUNDED NUMERIC INGRESS — INTERNAL PROOF-OF-CONCEPT

15 test categories covering the Design 01 §6 synthetic proof plan:
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
12. No Decimal construction before validation
13. No uncontrolled conversion/formatting/dispatch on rejected inputs
14. Repeated construction and bounded registry
15. Independence from ambient decimal context

Hardening additions (pre-publication):
 H1. Path closure — invalid/unsafe paths rejected before appearing in errors
 H2. Profile subclass bypass — exact type check for IngressContextV1 profile

Owner: Leng Wei Heng
Design authority: PANTRYPROOF_D3_V0_NUMERIC_INGRESS_BOUNDARY_DESIGN_01 §6
"""

from __future__ import annotations

import decimal
from decimal import Decimal
from unittest.mock import patch

import pytest

from pipeline.proposed.bounded_numeric_ingress_v1 import (
    IngressContextV1,
    IngressProfileV1,
    NumericIngressError,
    NumericIngressErrorCode,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_profile(**overrides: int) -> IngressProfileV1:
    """Create a test profile with small explicit limits."""
    defaults = dict(
        max_coefficient_digits=10,
        max_exponent_magnitude=20,
        max_constructions=50,
        max_work_units=500,
    )
    defaults.update(overrides)
    return IngressProfileV1(**defaults)


class _HostileInt(int):
    """int subclass with trapping methods — must be rejected."""

    def __eq__(self, other: object) -> bool:
        raise RuntimeError("HostileInt.__eq__ invoked")

    def __hash__(self) -> int:
        raise RuntimeError("HostileInt.__hash__ invoked")

    def __bool__(self) -> bool:
        raise RuntimeError("HostileInt.__bool__ invoked")

    def __repr__(self) -> str:
        raise RuntimeError("HostileInt.__repr__ invoked")


class _HostileStr(str):
    """str subclass with trapping methods — must be rejected."""

    def __len__(self) -> int:
        raise RuntimeError("HostileStr.__len__ invoked")

    def __iter__(self):
        raise RuntimeError("HostileStr.__iter__ invoked")

    def __eq__(self, other: object) -> bool:
        raise RuntimeError("HostileStr.__eq__ invoked")

    def __hash__(self) -> int:
        raise RuntimeError("HostileStr.__hash__ invoked")


# ===================================================================
# Category 1: Valid bounded recipes
# ===================================================================

class TestValidBoundedRecipes:
    """Positive, negative, zero, and trailing-zero recipes."""

    def test_positive_integer(self) -> None:
        ctx = IngressContextV1(_default_profile())
        d = ctx.construct_decimal(0, "42", 0, "field")
        assert d == Decimal("42")
        assert d.as_tuple() == (0, (4, 2), 0)

    def test_negative_integer(self) -> None:
        ctx = IngressContextV1(_default_profile())
        d = ctx.construct_decimal(1, "42", 0, "field")
        assert d == Decimal("-42")
        assert d.as_tuple() == (1, (4, 2), 0)

    def test_positive_zero(self) -> None:
        ctx = IngressContextV1(_default_profile())
        d = ctx.construct_decimal(0, "0", 0, "field")
        assert d == Decimal("0")
        assert d.as_tuple() == (0, (0,), 0)

    def test_fractional_value(self) -> None:
        ctx = IngressContextV1(_default_profile())
        d = ctx.construct_decimal(0, "123", -2, "field")
        assert d == Decimal("1.23")
        assert d.as_tuple() == (0, (1, 2, 3), -2)

    def test_trailing_zeros_preserved(self) -> None:
        ctx = IngressContextV1(_default_profile())
        d = ctx.construct_decimal(0, "1000", -2, "field")
        assert d.as_tuple() == (0, (1, 0, 0, 0), -2)
        # Value is 10.00 but tuple preserves trailing zeros
        assert d == Decimal("10.00")

    def test_large_exponent(self) -> None:
        ctx = IngressContextV1(_default_profile())
        d = ctx.construct_decimal(0, "5", 10, "field")
        assert d == Decimal("5E+10")
        assert d.as_tuple() == (0, (5,), 10)

    def test_negative_exponent(self) -> None:
        ctx = IngressContextV1(_default_profile())
        d = ctx.construct_decimal(0, "1", -20, "field")
        assert d.as_tuple() == (0, (1,), -20)

    def test_single_digit_coefficient(self) -> None:
        ctx = IngressContextV1(_default_profile())
        d = ctx.construct_decimal(0, "7", 0, "field")
        assert d == Decimal("7")
        assert d.as_tuple() == (0, (7,), 0)


# ===================================================================
# Category 2: Empty/malformed/non-ASCII coefficients
# ===================================================================

class TestMalformedCoefficients:
    """Empty, non-ASCII, and non-digit coefficient strings."""

    def test_empty_coefficient(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "", 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.INVALID_SHAPE

    def test_non_digit_coefficient(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "12a3", 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.INVALID_SHAPE

    def test_non_ascii_digit_coefficient(self) -> None:
        ctx = IngressContextV1(_default_profile())
        # Arabic-Indic digit ٣ (U+0663) — not an ASCII digit
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "\u0663", 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.INVALID_SHAPE

    def test_whitespace_coefficient(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, " 1 ", 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.INVALID_SHAPE

    def test_negative_sign_in_coefficient(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "-5", 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.INVALID_SHAPE

    def test_dot_in_coefficient(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "1.5", 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.INVALID_SHAPE

    def test_redundant_leading_zeros(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "007", 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.INVALID_SHAPE

    def test_single_zero_allowed(self) -> None:
        ctx = IngressContextV1(_default_profile())
        d = ctx.construct_decimal(0, "0", 0, "field")
        assert d == Decimal("0")


# ===================================================================
# Category 3: Coefficient digit-length boundaries
# ===================================================================

class TestCoefficientLengthBoundaries:
    """Below/equal/one-over the max_coefficient_digits limit."""

    def test_below_limit(self) -> None:
        p = _default_profile(max_coefficient_digits=5)
        ctx = IngressContextV1(p)
        d = ctx.construct_decimal(0, "1234", 0, "field")
        assert d == Decimal("1234")

    def test_at_limit(self) -> None:
        p = _default_profile(max_coefficient_digits=5)
        ctx = IngressContextV1(p)
        d = ctx.construct_decimal(0, "12345", 0, "field")
        assert d == Decimal("12345")

    def test_one_over_limit(self) -> None:
        p = _default_profile(max_coefficient_digits=5)
        ctx = IngressContextV1(p)
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "123456", 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.RESOURCE_LIMIT
        assert exc_info.value.limit_field == "max_coefficient_digits"


# ===================================================================
# Category 4: Quantum exponent boundaries
# ===================================================================

class TestExponentBoundaries:
    """Both ends of the quantum exponent range."""

    def test_at_positive_limit(self) -> None:
        p = _default_profile(max_exponent_magnitude=10)
        ctx = IngressContextV1(p)
        d = ctx.construct_decimal(0, "1", 10, "field")
        assert d.as_tuple() == (0, (1,), 10)

    def test_over_positive_limit(self) -> None:
        p = _default_profile(max_exponent_magnitude=10)
        ctx = IngressContextV1(p)
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "1", 11, "field")
        assert exc_info.value.code == NumericIngressErrorCode.INVALID_NUMERIC_VALUE
        assert exc_info.value.limit_field == "max_exponent_magnitude"

    def test_at_negative_limit(self) -> None:
        p = _default_profile(max_exponent_magnitude=10)
        ctx = IngressContextV1(p)
        d = ctx.construct_decimal(0, "1", -10, "field")
        assert d.as_tuple() == (0, (1,), -10)

    def test_over_negative_limit(self) -> None:
        p = _default_profile(max_exponent_magnitude=10)
        ctx = IngressContextV1(p)
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "1", -11, "field")
        assert exc_info.value.code == NumericIngressErrorCode.INVALID_NUMERIC_VALUE
        assert exc_info.value.limit_field == "max_exponent_magnitude"

    def test_zero_exponent_always_valid(self) -> None:
        p = _default_profile(max_exponent_magnitude=1)
        ctx = IngressContextV1(p)
        d = ctx.construct_decimal(0, "5", 0, "field")
        assert d == Decimal("5")


# ===================================================================
# Category 5: Invalid sign values
# ===================================================================

class TestInvalidSignValues:
    """Sign must be exact int 0 or 1. Reject bool, out-of-range, None."""

    def test_sign_two(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(2, "1", 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.INVALID_SHAPE

    def test_sign_negative_one(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(-1, "1", 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.INVALID_SHAPE

    def test_sign_true(self) -> None:
        """True is bool, a subclass of int — must be rejected."""
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(True, "1", 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.INVALID_SHAPE

    def test_sign_false(self) -> None:
        """False is bool — must be rejected even though int(False)==0."""
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(False, "1", 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.INVALID_SHAPE

    def test_sign_none(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(None, "1", 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.INVALID_SHAPE


# ===================================================================
# Category 6: Oversized integers and hostile subclasses
# ===================================================================

class TestHostileSubclasses:
    """Hostile int/str subclasses with trapping methods must be rejected
    at exact-type check before any dispatch."""

    def test_hostile_int_sign(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(_HostileInt(0), "1", 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.INVALID_SHAPE

    def test_hostile_str_coefficient(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, _HostileStr("123"), 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.INVALID_SHAPE

    def test_hostile_int_exponent(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "1", _HostileInt(0), "field")
        assert exc_info.value.code == NumericIngressErrorCode.INVALID_SHAPE

    def test_float_sign_rejected(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0.0, "1", 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.INVALID_SHAPE

    def test_float_exponent_rejected(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "1", 0.0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.INVALID_SHAPE

    def test_profile_with_bool_limit(self) -> None:
        """Profile limits must also be exact int, not bool."""
        with pytest.raises(NumericIngressError) as exc_info:
            _default_profile(max_coefficient_digits=True)
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID


# ===================================================================
# Category 7: Signed zero preservation
# ===================================================================

class TestSignedZeroPreservation:
    """Positive and negative zero are distinct tuple representations."""

    def test_positive_zero_tuple(self) -> None:
        ctx = IngressContextV1(_default_profile())
        d = ctx.construct_decimal(0, "0", -2, "field")
        assert d.as_tuple() == (0, (0,), -2)

    def test_negative_zero_tuple(self) -> None:
        ctx = IngressContextV1(_default_profile())
        d = ctx.construct_decimal(1, "0", -2, "field")
        assert d.as_tuple() == (1, (0,), -2)

    def test_signed_zeros_different_tuples(self) -> None:
        ctx = IngressContextV1(_default_profile())
        pos = ctx.construct_decimal(0, "0", -2, "field")
        neg = ctx.construct_decimal(1, "0", -2, "field")
        assert pos.as_tuple() != neg.as_tuple()
        assert pos.as_tuple()[0] == 0
        assert neg.as_tuple()[0] == 1


# ===================================================================
# Category 8: Distinct quantum representations of equal values
# ===================================================================

class TestDistinctQuantumRepresentations:
    """1.0 vs 1.00 are numerically equal but have different tuples."""

    def test_different_scale_same_value(self) -> None:
        ctx = IngressContextV1(_default_profile())
        d1 = ctx.construct_decimal(0, "10", -1, "field")   # 1.0
        d2 = ctx.construct_decimal(0, "100", -2, "field")  # 1.00
        # Numerically equal
        assert d1 == d2
        # But distinct tuple representations
        assert d1.as_tuple() != d2.as_tuple()
        assert d1.as_tuple() == (0, (1, 0), -1)
        assert d2.as_tuple() == (0, (1, 0, 0), -2)

    def test_integer_vs_fractional_one(self) -> None:
        ctx = IngressContextV1(_default_profile())
        d1 = ctx.construct_decimal(0, "1", 0, "field")
        d2 = ctx.construct_decimal(0, "10", -1, "field")
        assert d1 == d2
        assert d1.as_tuple() != d2.as_tuple()

    def test_distinct_objects(self) -> None:
        """Equal-valued Decimals from different recipes are distinct objects."""
        ctx = IngressContextV1(_default_profile())
        d1 = ctx.construct_decimal(0, "10", -1, "field")
        d2 = ctx.construct_decimal(0, "100", -2, "field")
        assert d1 is not d2


# ===================================================================
# Category 9: Registered identity vs unregistered Decimal
# ===================================================================

class TestRegisteredIdentity:
    """Exact registered reference accepted; external Decimals rejected."""

    def test_registered_decimal_accepted(self) -> None:
        ctx = IngressContextV1(_default_profile())
        d = ctx.construct_decimal(0, "42", 0, "field")
        result = ctx.check_registered(d, "field")
        assert result is d

    def test_unregistered_value_equal_decimal_rejected(self) -> None:
        """A value-equal Decimal from outside the context is rejected."""
        ctx = IngressContextV1(_default_profile())
        ctx.construct_decimal(0, "42", 0, "field")
        external = Decimal("42")
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.check_registered(external, "field")
        assert exc_info.value.code == NumericIngressErrorCode.UNREGISTERED_DECIMAL

    def test_decimal_from_different_context_rejected(self) -> None:
        """A Decimal from a different context is unregistered here."""
        ctx1 = IngressContextV1(_default_profile())
        ctx2 = IngressContextV1(_default_profile())
        d = ctx1.construct_decimal(0, "42", 0, "field")
        with pytest.raises(NumericIngressError) as exc_info:
            ctx2.check_registered(d, "field")
        assert exc_info.value.code == NumericIngressErrorCode.UNREGISTERED_DECIMAL

    def test_none_rejected(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.check_registered(None, "field")
        assert exc_info.value.code == NumericIngressErrorCode.UNREGISTERED_DECIMAL

    def test_string_rejected(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.check_registered("42", "field")
        assert exc_info.value.code == NumericIngressErrorCode.UNREGISTERED_DECIMAL

    def test_opaque_nonfinite_decimal_rejected(self) -> None:
        """Infinity and NaN Decimals are always unregistered."""
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.check_registered(Decimal("Inf"), "field")
        assert exc_info.value.code == NumericIngressErrorCode.UNREGISTERED_DECIMAL

        with pytest.raises(NumericIngressError) as exc_info:
            ctx.check_registered(Decimal("NaN"), "field")
        assert exc_info.value.code == NumericIngressErrorCode.UNREGISTERED_DECIMAL


# ===================================================================
# Category 10: Deterministic error precedence
# ===================================================================

class TestDeterministicErrorPrecedence:
    """First violation wins per Design 01 §4 order."""

    def test_shape_before_resource(self) -> None:
        """An invalid-shape sign is reported before any resource check."""
        p = _default_profile(max_constructions=1)
        ctx = IngressContextV1(p)
        # Exhaust construction budget
        ctx.construct_decimal(0, "1", 0, "field")
        # Both RESOURCE_LIMIT (budget exhausted) and INVALID_SHAPE (bad sign)
        # RESOURCE_LIMIT comes first because construction budget is checked
        # before per-field shape validation
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(True, "1", 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.RESOURCE_LIMIT

    def test_sign_shape_before_coefficient_shape(self) -> None:
        """Sign type is checked before coefficient."""
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(True, "", 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.INVALID_SHAPE
        assert "sign" in exc_info.value.path

    def test_coefficient_shape_before_exponent_value(self) -> None:
        """Coefficient grammar is checked before exponent range."""
        p = _default_profile(max_exponent_magnitude=5)
        ctx = IngressContextV1(p)
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "abc", 100, "field")
        assert exc_info.value.code == NumericIngressErrorCode.INVALID_SHAPE
        assert "coefficient" in exc_info.value.path

    def test_coefficient_length_before_digit_scan(self) -> None:
        """Overlength coefficient fails as RESOURCE_LIMIT before scanning."""
        p = _default_profile(max_coefficient_digits=3)
        ctx = IngressContextV1(p)
        # "12345" is 5 digits, limit is 3
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "12345", 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.RESOURCE_LIMIT
        assert exc_info.value.limit_field == "max_coefficient_digits"

    def test_exponent_before_work_reservation(self) -> None:
        """Out-of-range exponent is checked before work budget."""
        p = _default_profile(max_exponent_magnitude=5, max_work_units=2)
        ctx = IngressContextV1(p)
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "1", 100, "field")
        assert exc_info.value.code == NumericIngressErrorCode.INVALID_NUMERIC_VALUE


# ===================================================================
# Category 11: Budget exhaustion and failure atomicity
# ===================================================================

class TestBudgetExhaustionAndAtomicity:
    """Resource limits, failure atomicity, counter consistency."""

    def test_construction_budget_exact(self) -> None:
        p = _default_profile(max_constructions=3, max_work_units=100)
        ctx = IngressContextV1(p)
        for i in range(3):
            ctx.construct_decimal(0, str(i + 1), 0, "field")
        assert ctx.constructions == 3
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "4", 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.RESOURCE_LIMIT
        assert exc_info.value.limit_field == "max_constructions"

    def test_work_budget_exhaustion(self) -> None:
        # work_cost = 1 + len(coefficient)
        # "12345" costs 1+5=6 work units
        p = _default_profile(max_work_units=10)
        ctx = IngressContextV1(p)
        ctx.construct_decimal(0, "12345", 0, "field")  # 6 units
        assert ctx.work_units == 6
        # "12345" would cost 6 more, total 12 > 10
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "12345", 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.RESOURCE_LIMIT
        assert exc_info.value.limit_field == "max_work_units"

    def test_failure_does_not_change_counters(self) -> None:
        p = _default_profile(max_constructions=10, max_work_units=100)
        ctx = IngressContextV1(p)
        ctx.construct_decimal(0, "1", 0, "field")
        c_before = ctx.constructions
        w_before = ctx.work_units
        r_before = ctx.registry_size
        # This will fail (invalid sign)
        with pytest.raises(NumericIngressError):
            ctx.construct_decimal(True, "1", 0, "field")
        assert ctx.constructions == c_before
        assert ctx.work_units == w_before
        assert ctx.registry_size == r_before

    def test_work_budget_exact_boundary(self) -> None:
        """Exactly hitting the work budget should succeed."""
        # "1" costs 1+1=2 work units each
        p = _default_profile(max_work_units=4, max_constructions=10)
        ctx = IngressContextV1(p)
        ctx.construct_decimal(0, "1", 0, "field")  # 2
        ctx.construct_decimal(0, "2", 0, "field")  # 4, exactly at limit
        assert ctx.work_units == 4
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "3", 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.RESOURCE_LIMIT
        assert exc_info.value.limit_field == "max_work_units"


# ===================================================================
# Category 12: No Decimal construction before validation
# ===================================================================

class TestNoDecimalBeforeValidation:
    """Instrument the module-level Decimal reference to verify no
    construction occurs on rejected inputs.

    We patch the ``Decimal`` name inside the implementation module
    with a tracking wrapper, rather than trying to patch the immutable
    C-level metaclass ``__call__``.
    """

    def test_invalid_shape_no_decimal_created(self) -> None:
        import pipeline.proposed.bounded_numeric_ingress_v1 as mod

        ctx = IngressContextV1(_default_profile())
        call_log: list[object] = []
        original_decimal = mod.Decimal

        class TrackingDecimal(type(original_decimal)):
            """Wrapper that logs every construction."""

            def __new__(cls, *args, **kwargs):
                call_log.append(args)
                return original_decimal(*args, **kwargs)

        saved = mod.Decimal
        mod.Decimal = TrackingDecimal
        try:
            with pytest.raises(NumericIngressError):
                ctx.construct_decimal(True, "1", 0, "field")
        finally:
            mod.Decimal = saved
        assert len(call_log) == 0, "Decimal constructed before shape validation"

    def test_resource_limit_no_decimal_created(self) -> None:
        import pipeline.proposed.bounded_numeric_ingress_v1 as mod

        p = _default_profile(max_coefficient_digits=3)
        ctx = IngressContextV1(p)
        call_log: list[object] = []
        original_decimal = mod.Decimal

        class TrackingDecimal(type(original_decimal)):
            def __new__(cls, *args, **kwargs):
                call_log.append(args)
                return original_decimal(*args, **kwargs)

        saved = mod.Decimal
        mod.Decimal = TrackingDecimal
        try:
            with pytest.raises(NumericIngressError):
                ctx.construct_decimal(0, "12345", 0, "field")
        finally:
            mod.Decimal = saved
        assert len(call_log) == 0, "Decimal constructed before resource check"

    def test_exponent_violation_no_decimal_created(self) -> None:
        import pipeline.proposed.bounded_numeric_ingress_v1 as mod

        p = _default_profile(max_exponent_magnitude=5)
        ctx = IngressContextV1(p)
        call_log: list[object] = []
        original_decimal = mod.Decimal

        class TrackingDecimal(type(original_decimal)):
            def __new__(cls, *args, **kwargs):
                call_log.append(args)
                return original_decimal(*args, **kwargs)

        saved = mod.Decimal
        mod.Decimal = TrackingDecimal
        try:
            with pytest.raises(NumericIngressError):
                ctx.construct_decimal(0, "1", 100, "field")
        finally:
            mod.Decimal = saved
        assert len(call_log) == 0, "Decimal constructed before exponent check"


# ===================================================================
# Category 13: No uncontrolled conversion/formatting/dispatch
# ===================================================================

class TestNoUncontrolledDispatch:
    """Rejected inputs must not trigger formatting, conversion, or
    comparison operations that could be exploited."""

    def test_hostile_int_no_dispatch(self) -> None:
        """HostileInt traps __eq__, __hash__, __bool__, __repr__.
        If any of these are invoked, HostileInt raises RuntimeError."""
        ctx = IngressContextV1(_default_profile())
        # This should raise NumericIngressError, NOT RuntimeError
        with pytest.raises(NumericIngressError):
            ctx.construct_decimal(_HostileInt(0), "1", 0, "field")

    def test_hostile_str_no_dispatch(self) -> None:
        """HostileStr traps __len__, __iter__, __eq__, __hash__.
        Exact type check must reject before any dispatch."""
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError):
            ctx.construct_decimal(0, _HostileStr("123"), 0, "field")

    def test_hostile_int_exponent_no_dispatch(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError):
            ctx.construct_decimal(0, "1", _HostileInt(0), "field")

    def test_non_string_coefficient_types(self) -> None:
        """Various non-str coefficient types rejected without dispatch."""
        ctx = IngressContextV1(_default_profile())
        for bad_coeff in [123, 1.5, b"123", ["1", "2", "3"], None]:
            with pytest.raises(NumericIngressError) as exc_info:
                ctx.construct_decimal(0, bad_coeff, 0, "field")
            assert exc_info.value.code == NumericIngressErrorCode.INVALID_SHAPE


# ===================================================================
# Category 14: Repeated construction and bounded registry
# ===================================================================

class TestRepeatedConstructionAndRegistry:
    """Multiple constructions, registry growth, same-recipe behavior."""

    def test_registry_grows_with_constructions(self) -> None:
        ctx = IngressContextV1(_default_profile())
        for i in range(5):
            ctx.construct_decimal(0, str(i + 1), 0, "field")
        assert ctx.registry_size == 5
        assert ctx.constructions == 5

    def test_same_recipe_produces_distinct_objects(self) -> None:
        """Two calls with identical recipes produce distinct objects."""
        ctx = IngressContextV1(_default_profile())
        d1 = ctx.construct_decimal(0, "42", 0, "field")
        d2 = ctx.construct_decimal(0, "42", 0, "field")
        assert d1 == d2  # Value-equal
        assert d1 is not d2  # Distinct objects
        assert ctx.registry_size == 2

    def test_both_objects_individually_registered(self) -> None:
        ctx = IngressContextV1(_default_profile())
        d1 = ctx.construct_decimal(0, "42", 0, "field")
        d2 = ctx.construct_decimal(0, "42", 0, "field")
        # Both should be independently registered
        assert ctx.check_registered(d1, "field") is d1
        assert ctx.check_registered(d2, "field") is d2

    def test_failed_construction_does_not_register(self) -> None:
        p = _default_profile(max_coefficient_digits=3)
        ctx = IngressContextV1(p)
        ctx.construct_decimal(0, "1", 0, "field")
        with pytest.raises(NumericIngressError):
            ctx.construct_decimal(0, "12345", 0, "field")
        assert ctx.registry_size == 1

    def test_construction_counter_increments(self) -> None:
        ctx = IngressContextV1(_default_profile())
        assert ctx.constructions == 0
        ctx.construct_decimal(0, "1", 0, "field")
        assert ctx.constructions == 1
        ctx.construct_decimal(0, "2", 0, "field")
        assert ctx.constructions == 2

    def test_work_units_cumulative(self) -> None:
        ctx = IngressContextV1(_default_profile())
        # "12" costs 1+2=3
        ctx.construct_decimal(0, "12", 0, "field")
        assert ctx.work_units == 3
        # "345" costs 1+3=4
        ctx.construct_decimal(0, "345", 0, "field")
        assert ctx.work_units == 7


# ===================================================================
# Category 15: Independence from ambient decimal context
# ===================================================================

class TestAmbientContextIndependence:
    """Changing the ambient decimal context must not affect results."""

    def test_different_precision_same_result(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with decimal.localcontext() as local_ctx:
            local_ctx.prec = 5  # Very low precision
            d = ctx.construct_decimal(0, "1234567890", 0, "field")
        # Tuple form ignores context precision
        assert d.as_tuple() == (0, (1, 2, 3, 4, 5, 6, 7, 8, 9, 0), 0)

    def test_different_rounding_same_result(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with decimal.localcontext() as local_ctx:
            local_ctx.rounding = decimal.ROUND_DOWN
            d1 = ctx.construct_decimal(0, "123", -2, "field")
        with decimal.localcontext() as local_ctx:
            local_ctx.rounding = decimal.ROUND_UP
            d2 = ctx.construct_decimal(0, "123", -2, "field")
        assert d1.as_tuple() == d2.as_tuple()

    def test_traps_enabled_no_effect(self) -> None:
        """Even with all traps enabled, tuple construction succeeds."""
        ctx = IngressContextV1(_default_profile())
        with decimal.localcontext() as local_ctx:
            local_ctx.traps[decimal.Overflow] = True
            local_ctx.traps[decimal.Underflow] = True
            local_ctx.traps[decimal.InvalidOperation] = True
            d = ctx.construct_decimal(0, "42", 0, "field")
        assert d == Decimal("42")

    def test_emin_emax_no_effect(self) -> None:
        """Custom Emin/Emax in context does not affect tuple construction."""
        ctx = IngressContextV1(_default_profile())
        with decimal.localcontext() as local_ctx:
            local_ctx.Emin = -10
            local_ctx.Emax = 10
            # Construct a value with exponent that would exceed context Emax
            # but tuple form doesn't apply context limits
            d = ctx.construct_decimal(0, "1", 15, "field")
        assert d.as_tuple() == (0, (1,), 15)


# ===================================================================
# Additional edge-case coverage
# ===================================================================

class TestProfileValidation:
    """Profile construction validation edge cases."""

    def test_zero_limit_rejected(self) -> None:
        with pytest.raises(NumericIngressError) as exc_info:
            _default_profile(max_coefficient_digits=0)
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID

    def test_negative_limit_rejected(self) -> None:
        with pytest.raises(NumericIngressError) as exc_info:
            _default_profile(max_work_units=-1)
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID

    def test_ceiling_limit_accepted(self) -> None:
        """2**31 - 1 is accepted as a limit value."""
        p = _default_profile(max_coefficient_digits=2**31 - 1)
        assert p.max_coefficient_digits == 2**31 - 1

    def test_over_ceiling_rejected(self) -> None:
        """2**31 exceeds the limit ceiling."""
        with pytest.raises(NumericIngressError) as exc_info:
            _default_profile(max_coefficient_digits=2**31)
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID

    def test_float_limit_rejected(self) -> None:
        with pytest.raises(NumericIngressError) as exc_info:
            _default_profile(max_exponent_magnitude=10.0)
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID

    def test_non_profile_context_rejected(self) -> None:
        """Passing a non-IngressProfileV1 to IngressContextV1 is rejected."""
        with pytest.raises(NumericIngressError) as exc_info:
            IngressContextV1({"max_coefficient_digits": 10})
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID

    def test_none_profile_rejected(self) -> None:
        with pytest.raises(NumericIngressError) as exc_info:
            IngressContextV1(None)
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID


class TestErrorMessageClosure:
    """Error messages contain only closed schema paths and limit names."""

    def test_error_contains_path(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(True, "1", 0, "field.confidence")
        msg = str(exc_info.value)
        assert "field.confidence" in msg
        # Must not contain the actual input text
        assert "True" not in msg

    def test_resource_error_contains_limit_name(self) -> None:
        p = _default_profile(max_coefficient_digits=3)
        ctx = IngressContextV1(p)
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "12345", 0, "field.amount")
        msg = str(exc_info.value)
        assert "max_coefficient_digits" in msg
        # Must not contain the actual overlength coefficient
        assert "12345" not in msg


# ===================================================================
# Hardening H1: Path closure
# ===================================================================

class TestPathClosure:
    """H1: Invalid or unsafe path strings are rejected before they can
    appear in any error message.

    Design 01 §4: 'Report closed schema paths … without reproducing
    input text.' Context inputs must name one of the declared synthetic
    roles. Character syntax and length alone do not establish membership.
    """

    # -- construct_decimal path validation ---------------------------------

    def test_path_with_newline_rejected(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "1", 0, "field\ninjected")
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID
        # Newline must not appear in the error message
        assert "\n" not in str(exc_info.value)

    def test_path_with_carriage_return_rejected(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "1", 0, "field\rinjected")
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID
        assert "\r" not in str(exc_info.value)

    def test_path_with_space_rejected(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "1", 0, "field value")
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID

    def test_path_with_receipt_text_chars_rejected(self) -> None:
        """Angle brackets, quotes, semicolons, etc. are not in [A-Za-z0-9._-]."""
        ctx = IngressContextV1(_default_profile())
        for bad_path in ["field<script>", "field;DROP", "field'quoted", 'field"q']:
            with pytest.raises(NumericIngressError) as exc_info:
                ctx.construct_decimal(0, "1", 0, bad_path)
            assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID
            # The bad path must not appear verbatim in the error message
            assert bad_path not in str(exc_info.value)

    def test_empty_path_rejected(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "1", 0, "")
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID

    def test_overlength_path_rejected(self) -> None:
        """Path longer than 256 characters is rejected."""
        ctx = IngressContextV1(_default_profile())
        long_path = "a" * 257
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "1", 0, long_path)
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID
        # Must not reproduce the long path in the message
        assert long_path not in str(exc_info.value)

    def test_path_exactly_256_chars_rejected(self) -> None:
        """Identifier length does not establish declared membership."""
        ctx = IngressContextV1(_default_profile())
        max_path = "a" * 256
        with pytest.raises(NumericIngressError) as caught:
            ctx.construct_decimal(0, "1", 0, max_path)
        assert caught.value.code is NumericIngressErrorCode.PROFILE_INVALID
        assert caught.value.path == "path"
        assert max_path not in str(caught.value)

    def test_non_str_path_rejected(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "1", 0, 42)
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID

    def test_none_path_rejected(self) -> None:
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "1", 0, None)
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID

    def test_valid_paths_accepted(self) -> None:
        """Representative valid schema paths pass through unchanged."""
        ctx = IngressContextV1(_default_profile())
        valid_paths = [
            "field",
            "field.confidence",
            "field.amount",
        ]
        for p in valid_paths:
            d = ctx.construct_decimal(0, "1", 0, p)
            assert d == 1

    def test_path_does_not_appear_in_shape_error(self) -> None:
        """When a valid path is used, only it (not any input text) appears."""
        ctx = IngressContextV1(_default_profile())
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(True, "1", 0, "field")
        msg = str(exc_info.value)
        assert "field.sign" in msg
        assert "True" not in msg

    # -- check_registered path validation ----------------------------------

    def test_check_registered_newline_path_rejected(self) -> None:
        ctx = IngressContextV1(_default_profile())
        d = ctx.construct_decimal(0, "1", 0, "field")
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.check_registered(d, "bad\npath")
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID
        assert "\n" not in str(exc_info.value)

    def test_check_registered_non_str_path_rejected(self) -> None:
        ctx = IngressContextV1(_default_profile())
        d = ctx.construct_decimal(0, "1", 0, "field")
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.check_registered(d, None)
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID

    def test_check_registered_valid_path_accepted(self) -> None:
        ctx = IngressContextV1(_default_profile())
        d = ctx.construct_decimal(0, "42", 0, "field.amount")
        result = ctx.check_registered(d, "field.amount")
        assert result is d

    def test_invalid_path_before_unregistered_check(self) -> None:
        """Path validation fires before the unregistered-Decimal check."""
        ctx = IngressContextV1(_default_profile())
        external = Decimal("42")
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.check_registered(external, "bad path!")
        # PROFILE_INVALID (path bad) takes precedence over UNREGISTERED_DECIMAL
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID

    def test_path_validated_before_budget_check(self) -> None:
        """Path validation fires before construction-budget check."""
        p = _default_profile(max_constructions=1)
        ctx = IngressContextV1(p)
        ctx.construct_decimal(0, "1", 0, "field")  # exhaust budget
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "2", 0, "bad path!")
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID


# ===================================================================
# Hardening H2: Profile subclass bypass
# ===================================================================

class TestProfileSubclassBypass:
    """H2: IngressContextV1 requires the exact IngressProfileV1 class.

    A subclass that overrides or bypasses __post_init__ cannot slip
    through; type(profile) is IngressProfileV1 catches it.
    """

    def test_profile_subclass_bypassing_post_init_rejected(self) -> None:
        """A subclass whose __post_init__ skips validation is rejected."""

        class _EvilProfile(IngressProfileV1):
            """Subclass that intentionally bypasses __post_init__ limits."""

            def __post_init__(self) -> None:
                # Deliberately do NOT call super().__post_init__() so
                # invalid limits are accepted by this subclass instance.
                pass

        # Construct with deliberately invalid limits (0 < 1 would normally fail)
        evil = object.__new__(_EvilProfile)
        # Use object.__setattr__ to bypass frozen dataclass protection
        for field, val in [
            ("max_coefficient_digits", 0),
            ("max_exponent_magnitude", 0),
            ("max_constructions", 0),
            ("max_work_units", 0),
        ]:
            object.__setattr__(evil, field, val)

        with pytest.raises(NumericIngressError) as exc_info:
            IngressContextV1(evil)
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID

    def test_profile_subclass_with_valid_limits_still_rejected(self) -> None:
        """Even a 'benign' subclass with correct limits is rejected.

        Only the exact IngressProfileV1 class is accepted.
        """

        class _SubProfile(IngressProfileV1):
            pass

        sub = _SubProfile(
            max_coefficient_digits=10,
            max_exponent_magnitude=20,
            max_constructions=50,
            max_work_units=500,
        )
        with pytest.raises(NumericIngressError) as exc_info:
            IngressContextV1(sub)
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID

    def test_exact_profile_class_accepted(self) -> None:
        """The exact IngressProfileV1 (not a subclass) is still accepted."""
        profile = IngressProfileV1(
            max_coefficient_digits=5,
            max_exponent_magnitude=10,
            max_constructions=20,
            max_work_units=100,
        )
        ctx = IngressContextV1(profile)
        d = ctx.construct_decimal(0, "1", 0, "field")
        assert d == 1

    def test_dict_profile_rejected(self) -> None:
        """A plain dict is not IngressProfileV1 (unchanged from before)."""
        with pytest.raises(NumericIngressError) as exc_info:
            IngressContextV1({"max_coefficient_digits": 10})
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID

    def test_none_profile_rejected(self) -> None:
        """None is not IngressProfileV1 (unchanged from before)."""
        with pytest.raises(NumericIngressError) as exc_info:
            IngressContextV1(None)
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID


# ===================================================================
# Hardening H3: Profile validation and snapshot at context creation
# ===================================================================

class TestProfileSnapshotAndRevalidation:
    """H3: IngressContextV1 re-validates all limit fields at context
    creation and snapshots them as independent ints.

    This closes two gaps:
    - A profile with fields mutated (via object.__setattr__) to invalid
      values after __post_init__ is rejected at context creation.
    - Mutations of the caller's profile after a successful context
      creation cannot change the context's effective limits.
    """

    def test_pre_context_mutation_to_zero_rejected(self) -> None:
        """Profile field mutated to 0 before context creation is rejected."""
        profile = _default_profile()
        # Bypass the frozen dataclass protection
        object.__setattr__(profile, "max_constructions", 0)
        with pytest.raises(NumericIngressError) as exc_info:
            IngressContextV1(profile)
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID

    def test_pre_context_mutation_to_negative_rejected(self) -> None:
        """Profile field mutated to a negative value is rejected."""
        profile = _default_profile()
        object.__setattr__(profile, "max_coefficient_digits", -1)
        with pytest.raises(NumericIngressError) as exc_info:
            IngressContextV1(profile)
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID

    def test_pre_context_mutation_to_bool_rejected(self) -> None:
        """Profile field mutated to True (bool) is rejected — exact int required."""
        profile = _default_profile()
        object.__setattr__(profile, "max_work_units", True)
        with pytest.raises(NumericIngressError) as exc_info:
            IngressContextV1(profile)
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID

    def test_pre_context_mutation_to_over_ceiling_rejected(self) -> None:
        """Profile field mutated above ceiling is rejected."""
        profile = _default_profile()
        object.__setattr__(profile, "max_exponent_magnitude", 2**31)
        with pytest.raises(NumericIngressError) as exc_info:
            IngressContextV1(profile)
        assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID

    def test_post_context_mutation_does_not_change_limit(self) -> None:
        """Mutating the profile after context creation has no effect.

        The context holds an independent snapshot, so mutations to the
        original IngressProfileV1 object are invisible to the context.
        """
        profile = _default_profile(max_constructions=2, max_work_units=100)
        ctx = IngressContextV1(profile)
        # Construct once successfully
        ctx.construct_decimal(0, "1", 0, "field")
        # Mutate the original profile to allow many more constructions
        object.__setattr__(profile, "max_constructions", 1000)
        # The second construction succeeds under the snapshotted limit of 2.
        ctx.construct_decimal(0, "2", 0, "field")
        # The third should fail — snapshotted limit was 2
        with pytest.raises(NumericIngressError) as exc_info:
            ctx.construct_decimal(0, "3", 0, "field")
        assert exc_info.value.code == NumericIngressErrorCode.RESOURCE_LIMIT
        assert exc_info.value.limit_field == "max_constructions"

    def test_post_context_mutation_to_zero_does_not_disable_context(self) -> None:
        """Mutating a profile field to 0 after context creation leaves the
        context functional with the original snapshotted limits."""
        profile = _default_profile(max_constructions=5)
        ctx = IngressContextV1(profile)
        # Sabotage the original profile
        object.__setattr__(profile, "max_constructions", 0)
        # Context must still work using the snapshotted value of 5
        d = ctx.construct_decimal(0, "42", 0, "field")
        assert d == 42
        assert ctx.constructions == 1

    def test_all_four_limit_fields_independently_snapshotted(self) -> None:
        """Each snapshot field is independently checked."""
        for field_name, bad_value in [
            ("max_coefficient_digits", 0),
            ("max_exponent_magnitude", -5),
            ("max_constructions", 0),
            ("max_work_units", True),
        ]:
            profile = _default_profile()
            object.__setattr__(profile, field_name, bad_value)
            with pytest.raises(NumericIngressError) as exc_info:
                IngressContextV1(profile)
            assert exc_info.value.code == NumericIngressErrorCode.PROFILE_INVALID


# ===================================================================
# Hardening H4: Error construction closure
# ===================================================================

class TestErrorConstructionClosure:
    """H4: NumericIngressError.__init__ selects declared path and limit tokens
    before they appear in the message string or on the exception attributes.

    Vocabulary selection is non-recursive: it uses _safe_message_token,
    which never constructs NumericIngressError.
    """

    def test_newline_in_direct_path_sanitized(self) -> None:
        """Directly constructing an error with a newline in path is safe."""
        err = NumericIngressError(
            NumericIngressErrorCode.INVALID_SHAPE,
            "field\ninjected",
        )
        msg = str(err)
        assert "\n" not in msg
        assert "\n" not in err.path

    def test_carriage_return_in_direct_path_sanitized(self) -> None:
        err = NumericIngressError(
            NumericIngressErrorCode.INVALID_SHAPE,
            "field\rinjected",
        )
        assert "\r" not in str(err)
        assert "\r" not in err.path

    def test_space_in_direct_path_sanitized(self) -> None:
        err = NumericIngressError(
            NumericIngressErrorCode.INVALID_SHAPE,
            "field value",
        )
        # Unsupported input selects the fixed declared fallback.
        assert " " not in err.path
        # The raw input "field value" does not appear verbatim in the message
        assert "field value" not in str(err)

    def test_unsafe_chars_select_fixed_fallback(self) -> None:
        """Unsupported paths select the fixed fallback."""
        err = NumericIngressError(
            NumericIngressErrorCode.INVALID_SHAPE,
            "field<script>",
        )
        assert "<" not in str(err)
        assert ">" not in str(err)
        assert "<script>" not in str(err)
        assert err.path == "path"

    def test_non_str_path_selects_fixed_fallback(self) -> None:
        """Non-string paths use the declared fallback without conversion."""
        err = NumericIngressError(
            NumericIngressErrorCode.PROFILE_INVALID,
            42,
        )
        assert err.path == "path"
        assert str(err) == "PROFILE_INVALID: path"

    def test_newline_in_limit_field_sanitized(self) -> None:
        err = NumericIngressError(
            NumericIngressErrorCode.RESOURCE_LIMIT,
            "field.amount",
            "max_coefficient_digits\ninjected",
        )
        assert "\n" not in str(err)
        assert err.limit_field is None
        assert "injected" not in str(err)

    def test_none_limit_field_stored_as_none(self) -> None:
        err = NumericIngressError(
            NumericIngressErrorCode.INVALID_SHAPE,
            "field.sign",
        )
        assert err.limit_field is None

    def test_valid_path_passes_through_unchanged(self) -> None:
        """A declared diagnostic role is preserved exactly."""
        err = NumericIngressError(
            NumericIngressErrorCode.INVALID_SHAPE,
            "field.confidence",
        )
        assert err.path == "field.confidence"
        assert "field.confidence" in str(err)

    def test_valid_limit_field_passes_through_unchanged(self) -> None:
        err = NumericIngressError(
            NumericIngressErrorCode.RESOURCE_LIMIT,
            "field.amount",
            "max_coefficient_digits",
        )
        assert err.limit_field == "max_coefficient_digits"
        assert "max_coefficient_digits" in str(err)

    def test_overlength_path_selects_fixed_fallback(self) -> None:
        """An overlength path selects the fixed fallback."""
        long_path = "a" * 300
        err = NumericIngressError(
            NumericIngressErrorCode.INVALID_SHAPE,
            long_path,
        )
        assert err.path == "path"
        assert len(str(err)) < 400  # sanity bound

    def test_error_code_attribute_unchanged(self) -> None:
        """Code attribute is always the enum member, unaffected by sanitization."""
        err = NumericIngressError(
            NumericIngressErrorCode.CONSTRUCTION_ERROR,
            "bad\npath",
        )
        assert err.code is NumericIngressErrorCode.CONSTRUCTION_ERROR



class TestClosedDiagnosticVocabulary:
    @pytest.mark.parametrize("path", [
        "participant-001", "field.participant-001", "a-b-c", "X",
        "field_v1", "a" * 256, "field\ninjected", "field\rinjected",
        "field amount", "field<script>", "field.é", "", None, 42,
    ])
    def test_direct_error_uses_fixed_fallback(self, path):
        error = NumericIngressError(NumericIngressErrorCode.INVALID_SHAPE, path)
        assert error.path == "path"
        assert error.limit_field is None
        assert str(error) == "INVALID_SHAPE: path"

    @pytest.mark.parametrize("name", [
        "participant-001", "max_work_units\ninjected", "", "max_unknown",
        "é", 42,
        pytest.param(_HostileStr("max_work_units"), id="hostile-string"),
        pytest.param(_HostileInt(1), id="hostile-integer"),
    ])
    def test_unknown_limit_is_omitted(self, name):
        error = NumericIngressError(
            NumericIngressErrorCode.RESOURCE_LIMIT, "field.amount", name)
        assert error.limit_field is None
        assert str(error) == "RESOURCE_LIMIT: field.amount"

    def test_both_private_identifiers_are_not_reflected(self):
        error = NumericIngressError(
            NumericIngressErrorCode.RESOURCE_LIMIT,
            "participant-001", "participant-001")
        assert error.path == "path"
        assert error.limit_field is None
        assert str(error) == "RESOURCE_LIMIT: path"

    @pytest.mark.parametrize("limit", [
        "max_coefficient_digits", "max_exponent_magnitude",
        "max_constructions", "max_work_units",
    ])
    def test_all_profile_paths_and_limits_are_preserved(self, limit):
        path = "profile." + limit
        error = NumericIngressError(
            NumericIngressErrorCode.PROFILE_INVALID, path, limit)
        assert error.path == path
        assert error.limit_field == limit
        assert str(error) == "PROFILE_INVALID: " + path + ": " + limit

    @pytest.mark.parametrize("role", ["field", "field.amount", "field.confidence"])
    @pytest.mark.parametrize("child", ["sign", "coefficient", "quantum_exponent"])
    def test_declared_child_diagnostics(self, role, child):
        error = NumericIngressError(
            NumericIngressErrorCode.INVALID_SHAPE, role + "." + child)
        assert error.path == role + "." + child
        assert str(error) == "INVALID_SHAPE: " + role + "." + child

    @pytest.mark.parametrize("role", ["field", "field.amount", "field.confidence"])
    def test_real_operations_preserve_roles_and_children(self, role):
        ctx = IngressContextV1(_default_profile())
        value = ctx.construct_decimal(0, "1", 0, role)
        assert ctx.check_registered(value, role) is value
        for sign, coefficient, exponent, child, code in [
            (True, "1", 0, "sign", NumericIngressErrorCode.INVALID_SHAPE),
            (0, "", 0, "coefficient", NumericIngressErrorCode.INVALID_SHAPE),
            (0, "1", True, "quantum_exponent", NumericIngressErrorCode.INVALID_SHAPE),
        ]:
            with pytest.raises(NumericIngressError) as caught:
                ctx.construct_decimal(sign, coefficient, exponent, role)
            assert caught.value.path == role + "." + child
            assert caught.value.code is code
        assert (ctx.constructions, ctx.work_units, ctx.registry_size) == (1, 2, 1)

    @pytest.mark.parametrize("path", [
        "participant-001", "field.receipt123", "a-b-c", "X", "a" * 256,
        "field.sign", "profile", "field\ninjected", "", None,
        pytest.param(_HostileStr("field"), id="hostile-string"),
        pytest.param(_HostileInt(1), id="hostile-integer"),
    ])
    def test_unsupported_roles_fail_before_work_or_identity(self, path):
        ctx = IngressContextV1(_default_profile(max_constructions=1))
        value = ctx.construct_decimal(0, "1", 0, "field")
        before = (ctx.constructions, ctx.work_units, ctx.registry_size)
        with patch("pipeline.proposed.bounded_numeric_ingress_v1.Decimal") as constructor:
            with pytest.raises(NumericIngressError) as caught:
                ctx.construct_decimal(True, "bad", 999, path)
            assert caught.value.code is NumericIngressErrorCode.PROFILE_INVALID
            assert caught.value.path == "path"
            assert str(caught.value) == "PROFILE_INVALID: path"
            with pytest.raises(NumericIngressError) as caught:
                ctx.check_registered(object(), path)
            assert caught.value.code is NumericIngressErrorCode.PROFILE_INVALID
            assert str(caught.value) == "PROFILE_INVALID: path"
            constructor.assert_not_called()
        assert (ctx.constructions, ctx.work_units, ctx.registry_size) == before
        assert ctx.check_registered(value, "field") is value

    def test_hostile_diagnostics_and_code_do_not_dispatch(self):
        class Hostile:
            def __str__(self):
                raise AssertionError("str dispatched")
            def __repr__(self):
                raise AssertionError("repr dispatched")
            def __format__(self, spec):
                raise AssertionError("format dispatched")
            def __eq__(self, other):
                raise AssertionError("equality dispatched")
            def __hash__(self):
                raise AssertionError("hash dispatched")
        value = Hostile()
        error = NumericIngressError(
            NumericIngressErrorCode.INVALID_SHAPE, value, value)
        assert error.path == "path"
        assert error.limit_field is None
        assert str(error) == "INVALID_SHAPE: path"
        with pytest.raises(TypeError, match="^code must be a NumericIngressErrorCode$"):
            NumericIngressError(value, value, value)
