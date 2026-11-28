"""Immutable, caller-supplied evidence resources for receipt correction."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Context, Decimal, localcontext
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from pipeline.baseline_b3 import normalize_receipt_text
from pipeline.contracts import ReceiptFieldName
from pipeline.proposed.contracts import CandidateSourceKind, to_deterministic_json


def text_key(value: str) -> str:
    return normalize_receipt_text(value).casefold()


def _require_text(*values: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("Resource identifiers and text must be nonempty.")


class ResourceOrigin(str, Enum):
    EXTERNAL_FIXED_SNAPSHOT = "EXTERNAL_FIXED_SNAPSHOT"
    TRAINING_ONLY = "TRAINING_ONLY"


@dataclass(frozen=True, slots=True)
class ResourceProvenance:
    resource_id: str
    version: str
    snapshot_date: date
    origin: ResourceOrigin
    source_reference: str
    rights_reference: str
    training_manifest_reference: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.resource_id, self.version, self.source_reference, self.rights_reference)
        if type(self.snapshot_date) is not date or not isinstance(self.origin, ResourceOrigin):
            raise ValueError("A dated external snapshot or training-only resource is required.")
        if self.origin is ResourceOrigin.TRAINING_ONLY:
            _require_text(self.training_manifest_reference)
        elif self.training_manifest_reference is not None:
            raise ValueError("An external snapshot cannot declare a training manifest.")


def _snapshot_reference(provenance: ResourceProvenance, entries: tuple) -> str:
    if not isinstance(provenance, ResourceProvenance) or type(entries) is not tuple:
        raise ValueError("A resource snapshot requires provenance and immutable entries.")
    records = (asdict(provenance), *(asdict(entry) for entry in entries))
    body = to_deterministic_json(tuple({
        key: value.isoformat() if type(value) is date else value
        for key, value in record.items()
    } for record in records))
    digest = sha256(body.encode("utf-8")).hexdigest()
    return f"{provenance.resource_id}@{provenance.version}:sha256:{digest}"


@dataclass(frozen=True, slots=True)
class TerminologyEntry:
    entry_id: str
    field_name: ReceiptFieldName
    literal: str
    receipt_value: str
    source_kind: CandidateSourceKind
    retailer_id: str | None = None
    product_key: str | None = None
    pantry_identity: str | None = None
    pantry_category: str | None = None
    reference_unit: str | None = None
    source_reference: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.entry_id, self.literal, self.receipt_value)
        if not text_key(self.literal) or not text_key(self.receipt_value):
            raise ValueError("Terminology values must remain nonempty after normalization.")
        if self.source_kind is CandidateSourceKind.RETAILER_MAPPING:
            _require_text(self.retailer_id)
        elif self.source_kind is CandidateSourceKind.PANTRY_TERMINOLOGY:
            if self.retailer_id is not None or self.field_name is not ReceiptFieldName.ITEM_DESCRIPTION:
                raise ValueError("Pantry terminology applies only to item descriptions.")
        else:
            raise ValueError("A terminology entry requires retailer or pantry provenance.")
        if self.field_name not in (ReceiptFieldName.STORE_NAME, ReceiptFieldName.ITEM_DESCRIPTION):
            raise ValueError("Terminology entries apply only to store names and descriptions.")
        if self.product_key is not None:
            _require_text(self.product_key)
            if self.field_name is not ReceiptFieldName.ITEM_DESCRIPTION:
                raise ValueError("A product key requires an item-description entry.")
        for value in (self.pantry_identity, self.pantry_category, self.reference_unit):
            if value is not None:
                _require_text(value)
                if self.field_name is not ReceiptFieldName.ITEM_DESCRIPTION:
                    raise ValueError("Pantry metadata requires an item-description entry.")
        if self.source_reference is not None:
            _require_text(self.source_reference)


@dataclass(frozen=True, slots=True)
class TerminologySnapshot:
    provenance: ResourceProvenance
    entries: tuple[TerminologyEntry, ...]
    reference: str = field(init=False)
    _by_literal: Mapping = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        reference = _snapshot_reference(self.provenance, self.entries)
        by_literal = defaultdict(list)
        ids = set()
        for entry in self.entries:
            if not isinstance(entry, TerminologyEntry) or entry.entry_id in ids:
                raise ValueError("Terminology entry IDs must be unique.")
            ids.add(entry.entry_id)
            for literal in {text_key(entry.literal), text_key(entry.receipt_value)}:
                by_literal[entry.field_name, literal].append(entry)
        object.__setattr__(self, "reference", reference)
        object.__setattr__(self, "_by_literal", MappingProxyType({
            key: tuple(entries) for key, entries in by_literal.items()
        }))

    def retailer_id(self, store: str | None) -> str | None:
        if store is None:
            return None
        matches = self._by_literal.get((ReceiptFieldName.STORE_NAME, text_key(store)), ())
        ids = {entry.retailer_id for entry in matches}
        return next(iter(ids)) if len(ids) == 1 else None

    def match(
        self, field_name: ReceiptFieldName, literal: str, retailer_id: str | None,
    ) -> tuple[TerminologyEntry, ...]:
        return tuple(
            entry for entry in self._by_literal.get((field_name, text_key(literal)), ())
            if entry.retailer_id is None or entry.retailer_id == retailer_id
        )

    def pantry_matches(self, description: str, retailer_id: str | None) -> tuple[TerminologyEntry, ...]:
        """Return semantic evidence for a resolved receipt description."""
        return tuple(entry for entry in self.match(
            ReceiptFieldName.ITEM_DESCRIPTION, description, retailer_id,
        ) if entry.pantry_identity is not None)


class PriceBasis(str, Enum):
    EACH = "EACH"
    KG = "KG"
    G = "G"
    LB = "LB"
    OZ = "OZ"


class PromotionScope(str, Enum):
    UNSPECIFIED = "UNSPECIFIED"
    NON_PROMOTIONAL = "NON_PROMOTIONAL"


@dataclass(frozen=True, slots=True)
class MalaysianPriceBand:
    entry_id: str
    retailer_id: str
    product_key: str
    region: str
    valid_from: date
    valid_through: date
    basis: PriceBasis
    low_myr: Decimal
    high_myr: Decimal
    reference_unit: str | None = None
    promotion_scope: PromotionScope | None = None

    def __post_init__(self) -> None:
        _require_text(self.entry_id, self.retailer_id, self.product_key, self.region)
        if (type(self.valid_from) is not date or type(self.valid_through) is not date
                or self.valid_from > self.valid_through or not isinstance(self.basis, PriceBasis)):
            raise ValueError("A price band requires an ordered date window and an explicit basis.")
        if any(not isinstance(value, Decimal) or not value.is_finite() or value <= 0
               for value in (self.low_myr, self.high_myr)) or self.low_myr > self.high_myr:
            raise ValueError("A price band requires ordered positive MYR bounds.")
        if self.reference_unit is not None:
            _require_text(self.reference_unit)
        if self.promotion_scope is not None and not isinstance(self.promotion_scope, PromotionScope):
            raise ValueError("Use a documented promotion scope.")


@dataclass(frozen=True, slots=True)
class MalaysianPriceSnapshot:
    provenance: ResourceProvenance
    entries: tuple[MalaysianPriceBand, ...]
    reference: str = field(init=False)
    _by_context: Mapping = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        reference = _snapshot_reference(self.provenance, self.entries)
        by_context = defaultdict(list)
        ids = set()
        for entry in self.entries:
            if not isinstance(entry, MalaysianPriceBand) or entry.entry_id in ids:
                raise ValueError("Price entry IDs must be unique.")
            ids.add(entry.entry_id)
            by_context[entry.retailer_id, entry.product_key, entry.region, entry.basis].append(entry)
        object.__setattr__(self, "reference", reference)
        object.__setattr__(self, "_by_context", MappingProxyType({
            key: tuple(entries) for key, entries in by_context.items()
        }))

    def match(
        self, retailer: str, product: str, region: str, purchased: date, basis: PriceBasis,
    ) -> tuple[MalaysianPriceBand, ...]:
        return tuple(
            entry for entry in self._by_context.get((retailer, product, region, basis), ())
            if entry.valid_from <= purchased <= entry.valid_through
        )


@dataclass(frozen=True, slots=True)
class PriceDiscrepancyRule:
    rule_id: str
    relative_tolerance: Decimal

    def __post_init__(self) -> None:
        _require_text(self.rule_id)
        tolerance = self.relative_tolerance
        if (not isinstance(tolerance, Decimal) or not tolerance.is_finite()
                or not Decimal(0) <= tolerance < Decimal(1)):
            raise ValueError("Relative price tolerance must be in [0, 1).")

    @property
    def reference(self) -> str:
        return f"{self.rule_id}:relative-tolerance={self.relative_tolerance}"

    def compare(self, actual: Decimal, band: MalaysianPriceBand) -> bool:
        with localcontext(Context(prec=34)):
            low = band.low_myr * (1 - self.relative_tolerance)
            high = band.high_myr * (1 + self.relative_tolerance)
            return low <= actual <= high


@dataclass(frozen=True, slots=True)
class ReceiptResources:
    terminology: TerminologySnapshot | None = None
    prices: MalaysianPriceSnapshot | None = None
    discrepancy_rule: PriceDiscrepancyRule | None = None

    def __post_init__(self) -> None:
        for value, expected in (
            (self.terminology, TerminologySnapshot),
            (self.prices, MalaysianPriceSnapshot),
            (self.discrepancy_rule, PriceDiscrepancyRule),
        ):
            if value is not None and not isinstance(value, expected):
                raise TypeError(f"Expected {expected.__name__} for receipt evidence.")
        if (self.prices is None) != (self.discrepancy_rule is None):
            raise ValueError("A price snapshot and an explicit discrepancy rule must be supplied together.")


def load_receipt_resources(
    path: Path, *, discrepancy_rule: PriceDiscrepancyRule | None,
) -> ReceiptResources:
    """Load a fixed V1 resource artifact. A null rule enables terminology only."""
    return decode_receipt_resources(path.read_bytes(), discrepancy_rule=discrepancy_rule)


def decode_receipt_resources(
    payload: bytes, *, discrepancy_rule: PriceDiscrepancyRule | None,
) -> ReceiptResources:
    """Decode the same V1 resource artifact from already verified bytes."""
    packet = json.loads(payload.decode("utf-8"))
    if set(packet) != {"schema", "terminology", "prices"} or packet["schema"] != "receipt-resources-v1":
        raise ValueError("Expected a receipt-resources-v1 artifact.")

    def provenance(data):
        return ResourceProvenance(**{
            **data, "snapshot_date": date.fromisoformat(data["snapshot_date"]),
            "origin": ResourceOrigin(data["origin"]),
        })

    terms = packet["terminology"]
    terminology = TerminologySnapshot(provenance(terms["provenance"]), tuple(
        TerminologyEntry(**{
            **entry, "field_name": ReceiptFieldName(entry["field_name"]),
            "source_kind": CandidateSourceKind(entry["source_kind"]),
        }) for entry in terms["entries"]
    ))
    if discrepancy_rule is None:
        return ReceiptResources(terminology)
    prices = packet["prices"]
    price_snapshot = MalaysianPriceSnapshot(provenance(prices["provenance"]), tuple(
        MalaysianPriceBand(**{
            **entry, "valid_from": date.fromisoformat(entry["valid_from"]),
            "valid_through": date.fromisoformat(entry["valid_through"]),
            "basis": PriceBasis(entry["basis"]),
            "low_myr": Decimal(entry["low_myr"]), "high_myr": Decimal(entry["high_myr"]),
            "promotion_scope": PromotionScope(entry["promotion_scope"]),
        }) for entry in prices["entries"]
    ))
    return ReceiptResources(terminology, price_snapshot, discrepancy_rule)
