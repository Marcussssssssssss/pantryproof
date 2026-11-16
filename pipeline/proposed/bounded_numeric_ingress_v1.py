"""Bounded numeric ingress recipe helper v1.

D3 BOUNDED NUMERIC INGRESS — INTERNAL PROOF-OF-CONCEPT

This module provides a versioned, single-invocation Decimal construction
context with a checked profile and local counters.  It admits only
controlled finite recipes specified as (sign, coefficient, quantum_exponent)
triples and constructs Decimal values via the exact tuple form, with no
context-based conversion or rounding.

Scope
-----
- Private finite recipe constructor with explicit pre-work profile checks.
- Cumulative reservation for construction work and live allocations.
- Local exact-reference registration and admission.
- Independent of the existing D3/V0 preflight (Slice 01).
- No public package export, no pipeline integration, no operational wiring.

Owner: Leng Wei Heng
Design authority: PANTRYPROOF_D3_V0_NUMERIC_INGRESS_BOUNDARY_DESIGN_01 §4
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


# ---------------------------------------------------------------------------
# Error categories — Design 01 §4 rejection order
# ---------------------------------------------------------------------------

class NumericIngressErrorCode(enum.Enum):
    """Typed rejection categories in prescribed precedence order.

    The ordering follows Design 01 §4: profile first, then shape, then
    resource limits, then unregistered identity, then numeric domain
    invalidity, then construction failure.
    """

    PROFILE_INVALID = "PROFILE_INVALID"
    INVALID_SHAPE = "INVALID_SHAPE"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    UNREGISTERED_DECIMAL = "UNREGISTERED_DECIMAL"
    INVALID_NUMERIC_VALUE = "INVALID_NUMERIC_VALUE"
    CONSTRUCTION_ERROR = "CONSTRUCTION_ERROR"


class NumericIngressError(ValueError):
    """Rejection from the bounded numeric ingress context.

    Attributes
    ----------
    code : NumericIngressErrorCode
        Typed category for the rejection.
    path : str
        Closed schema path identifying the rejected operand role.
    limit_field : str or None
        The name of the limit that was exceeded, if applicable.

    No input text is reproduced in the error message.
    """

    def __init__(
        self,
        code: NumericIngressErrorCode,
        path: str,
        limit_field: Optional[str] = None,
    ) -> None:
        self.code = code
        self.path = path
        self.limit_field = limit_field
        parts = [code.value, path]
        if limit_field is not None:
            parts.append(limit_field)
        super().__init__(": ".join(parts))


# ---------------------------------------------------------------------------
# Profile — caller-supplied closed limits, no defaults
# ---------------------------------------------------------------------------

_LIMIT_CEILING = (2**31) - 1


@dataclass(frozen=True)
class IngressProfileV1:
    """Caller-supplied limits for a single ingress context.

    All fields must be explicit positive ``int`` values, each bounded
    by 2**31-1.  There are no defaults.  Tests select explicit local
    limits for boundary checks only.  No new production number is
    proposed by this proof-of-concept.

    Parameters
    ----------
    max_coefficient_digits : int
        Maximum number of coefficient digits (D) in a recipe.
    max_exponent_magnitude : int
        Maximum absolute value of the quantum exponent.
    max_constructions : int
        Maximum number of ``construct_decimal`` calls permitted.
    max_work_units : int
        Cumulative work-unit budget for the context.
    """

    max_coefficient_digits: int
    max_exponent_magnitude: int
    max_constructions: int
    max_work_units: int

    def __post_init__(self) -> None:
        """Validate all profile limits on construction."""
        for field_name in (
            "max_coefficient_digits",
            "max_exponent_magnitude",
            "max_constructions",
            "max_work_units",
        ):
            value = getattr(self, field_name)
            # Exact type: reject bool before int (bool is a subclass of int)
            if type(value) is not int:
                raise NumericIngressError(
                    NumericIngressErrorCode.PROFILE_INVALID,
                    f"profile.{field_name}",
                )
            if value < 1:
                raise NumericIngressError(
                    NumericIngressErrorCode.PROFILE_INVALID,
                    f"profile.{field_name}",
                )
            if value > _LIMIT_CEILING:
                raise NumericIngressError(
                    NumericIngressErrorCode.PROFILE_INVALID,
                    f"profile.{field_name}",
                )


# ---------------------------------------------------------------------------
# Construction context — single-invocation scope
# ---------------------------------------------------------------------------

class IngressContextV1:
    """Single-invocation bounded Decimal construction context.

    Each context tracks cumulative constructions, work units, and an
    identity registry keyed by ``id()``.  It admits only controlled
    finite recipes and produces Decimal values via the exact tuple form.

    Parameters
    ----------
    profile : IngressProfileV1
        Validated profile with closed limits.
    """

    def __init__(self, profile: IngressProfileV1) -> None:
        if not isinstance(profile, IngressProfileV1):
            raise NumericIngressError(
                NumericIngressErrorCode.PROFILE_INVALID,
                "profile",
            )
        self._profile = profile
        self._constructions: int = 0
        self._work_units: int = 0
        self._registry: dict[int, Decimal] = {}

    @property
    def constructions(self) -> int:
        """Number of successful constructions so far."""
        return self._constructions

    @property
    def work_units(self) -> int:
        """Cumulative work units consumed so far."""
        return self._work_units

    @property
    def registry_size(self) -> int:
        """Number of registered Decimal objects."""
        return len(self._registry)

    # -- Construction -------------------------------------------------------

    def construct_decimal(
        self,
        sign: int,
        coefficient: str,
        quantum_exponent: int,
        path: str,
    ) -> Decimal:
        """Construct a bounded Decimal from an exact recipe.

        Validation order (Design 01 §4):
        1. Exact type checks (bool rejected before int).
        2. Coefficient string length check before scanning.
        3. ASCII digit validation and canonical form.
        4. Exponent bounds.
        5. Work reservation.
        6. Digit tuple construction and Decimal via tuple form.
        7. Identity registration.

        Parameters
        ----------
        sign : int
            Exact native ``int``, must be 0 or 1.
        coefficient : str
            Exact nonempty ASCII digit string.  No redundant leading zeros
            except the single zero digit ``"0"``.
        quantum_exponent : int
            Exact native ``int`` for the exponent.
        path : str
            Closed schema path for error reporting.

        Returns
        -------
        Decimal
            The constructed value, registered in this context.

        Raises
        ------
        NumericIngressError
            On any validation or resource-limit failure.
        """
        # -- Step 0: construction budget -----------------------------------
        if self._constructions >= self._profile.max_constructions:
            raise NumericIngressError(
                NumericIngressErrorCode.RESOURCE_LIMIT,
                path,
                "max_constructions",
            )

        # -- Step 1: exact type checks (bool rejected before int) ----------
        if type(sign) is not int:
            raise NumericIngressError(
                NumericIngressErrorCode.INVALID_SHAPE,
                path + ".sign",
            )
        if type(coefficient) is not str:
            raise NumericIngressError(
                NumericIngressErrorCode.INVALID_SHAPE,
                path + ".coefficient",
            )
        if type(quantum_exponent) is not int:
            raise NumericIngressError(
                NumericIngressErrorCode.INVALID_SHAPE,
                path + ".quantum_exponent",
            )

        # -- Step 1b: sign range -------------------------------------------
        if sign not in (0, 1):
            raise NumericIngressError(
                NumericIngressErrorCode.INVALID_SHAPE,
                path + ".sign",
            )

        # -- Step 2: coefficient length before scanning --------------------
        if len(coefficient) == 0:
            raise NumericIngressError(
                NumericIngressErrorCode.INVALID_SHAPE,
                path + ".coefficient",
            )
        if len(coefficient) > self._profile.max_coefficient_digits:
            raise NumericIngressError(
                NumericIngressErrorCode.RESOURCE_LIMIT,
                path + ".coefficient",
                "max_coefficient_digits",
            )

        # -- Step 3: ASCII digit validation and canonical form -------------
        for ch in coefficient:
            if ch < "0" or ch > "9":
                raise NumericIngressError(
                    NumericIngressErrorCode.INVALID_SHAPE,
                    path + ".coefficient",
                )
        # No redundant leading zeros except single "0"
        if len(coefficient) > 1 and coefficient[0] == "0":
            raise NumericIngressError(
                NumericIngressErrorCode.INVALID_SHAPE,
                path + ".coefficient",
            )

        # -- Step 4: exponent bounds ---------------------------------------
        exp_mag = self._profile.max_exponent_magnitude
        if quantum_exponent < -exp_mag or quantum_exponent > exp_mag:
            raise NumericIngressError(
                NumericIngressErrorCode.INVALID_NUMERIC_VALUE,
                path + ".quantum_exponent",
                "max_exponent_magnitude",
            )

        # -- Step 5: work reservation --------------------------------------
        # Each construction costs 1 + coefficient_digits work units.
        work_cost = 1 + len(coefficient)
        if self._work_units + work_cost > self._profile.max_work_units:
            raise NumericIngressError(
                NumericIngressErrorCode.RESOURCE_LIMIT,
                path,
                "max_work_units",
            )

        # -- Step 6: digit tuple construction and Decimal via tuple form ---
        try:
            digit_tuple = tuple(int(ch) for ch in coefficient)
            result = Decimal((sign, digit_tuple, quantum_exponent))
        except Exception as exc:
            raise NumericIngressError(
                NumericIngressErrorCode.CONSTRUCTION_ERROR,
                path,
            ) from exc

        # -- Step 7: commit counters and register --------------------------
        self._constructions += 1
        self._work_units += work_cost
        self._registry[id(result)] = result

        return result

    # -- Registration check -------------------------------------------------

    def check_registered(self, value: object, path: str) -> Decimal:
        """Verify that *value* is a registered Decimal from this context.

        Uses exact object identity (``is``), not value equality.

        Parameters
        ----------
        value : object
            The object to verify.
        path : str
            Closed schema path for error reporting.

        Returns
        -------
        Decimal
            The same object, confirmed registered.

        Raises
        ------
        NumericIngressError
            If the object is not registered (UNREGISTERED_DECIMAL).
        """
        obj_id = id(value)
        registered = self._registry.get(obj_id)
        if registered is None or registered is not value:
            raise NumericIngressError(
                NumericIngressErrorCode.UNREGISTERED_DECIMAL,
                path,
            )
        return registered
