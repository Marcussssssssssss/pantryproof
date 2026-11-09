"""Receipt-presentation V1 synthetic conformance boundary."""

from .conformance import (
    ConformanceViolation,
    PresentationAutomaticExtraction,
    PresentationFailure,
    PresentationField,
    PresentationItemRow,
    PresentationOutcome,
    PresentationProducer,
    PresentationProvenance,
    PresentationReceipt,
    PresentationSource,
    PresentationSourceEvidence,
    PresentationSourceGate,
    ReceiptPresentationV1,
    decode_and_validate_presentation_v1,
    decode_strict_json_object,
    validate_presentation_v1_object,
)

__all__ = [
    "ConformanceViolation",
    "PresentationAutomaticExtraction",
    "PresentationFailure",
    "PresentationField",
    "PresentationItemRow",
    "PresentationOutcome",
    "PresentationProducer",
    "PresentationProvenance",
    "PresentationReceipt",
    "PresentationSource",
    "PresentationSourceEvidence",
    "PresentationSourceGate",
    "ReceiptPresentationV1",
    "decode_and_validate_presentation_v1",
    "decode_strict_json_object",
    "validate_presentation_v1_object",
]
