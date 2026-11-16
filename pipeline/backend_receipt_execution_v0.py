"""Synthetic-only execution seam for an injected source gate and unchanged B2.

This module supplies no gate criteria, OCR engine, retries or downstream policy.
"""

from __future__ import annotations

from collections.abc import Callable

from pipeline.contracts import SourceEvidenceDecision, SourceEvidenceGateResult
from pipeline.layout_b2 import B2ExtractionResult, extract_b2
from pipeline.ocr_adapter import (
    AdaptedOcrSource,
    OcrAdapterError,
    attach_gate_result,
)


__all__ = ("extract_adapted_receipt_v0",)


def extract_adapted_receipt_v0(
    *,
    adapted_source: AdaptedOcrSource,
    gate_evaluator: Callable[[AdaptedOcrSource], SourceEvidenceGateResult],
) -> B2ExtractionResult:
    """Call the supplied gate once, attach its result, then call B2 once.

    The exact source is passed to the evaluator. Existing record validation
    and attachment enforce structural and receipt bindings before extraction.
    Exceptions propagate unchanged; no retry or partial return is attempted.
    Exactly-once invocation is local to this call, not a cross-request guarantee.
    """
    if not isinstance(adapted_source, AdaptedOcrSource):
        raise OcrAdapterError("adapted_source must be an AdaptedOcrSource.")
    AdaptedOcrSource.__post_init__(adapted_source)
    if not callable(gate_evaluator):
        raise TypeError("gate_evaluator must be callable.")

    gate_result = gate_evaluator(adapted_source)
    if isinstance(gate_result, SourceEvidenceGateResult):
        SourceEvidenceGateResult.__post_init__(gate_result)
        # Contract annotations alone do not enforce enum membership. B2 uses
        # enum identity, so a string must never bypass its insufficient branch.
        if not isinstance(gate_result.decision, SourceEvidenceDecision):
            raise OcrAdapterError(
                "gate_result.decision must be a SourceEvidenceDecision."
            )

    evidence = attach_gate_result(adapted_source, gate_result)
    return extract_b2(evidence)
