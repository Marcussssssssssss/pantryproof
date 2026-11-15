"""Public, source-only D1 purchase-date discovery entry point."""

from __future__ import annotations

from pipeline.contracts import ReceiptSourceEvidence
from pipeline.layout_b2 import B2ExtractionResult
from pipeline.proposed.contracts import CandidateRecordV1, ConfigurationRefV1
from pipeline.proposed.purchase_date_source_contracts_v1 import (
    DateDiscoveryMethodProfileV1,
    DateDiscoveryResultV1,
    _build_result,
    validate_date_discovery_result_v1,
)

__all__ = ("discover_purchase_date_sources_v1", "validate_date_discovery_result_v1")


def discover_purchase_date_sources_v1(
    *,
    source_evidence: ReceiptSourceEvidence,
    b2_result: B2ExtractionResult,
    theta_a_reference: ConfigurationRefV1,
    method_profile: DateDiscoveryMethodProfileV1,
    existing_c0: CandidateRecordV1 | None = None,
) -> DateDiscoveryResultV1:
    """Observe stored regions and group unranked date interpretations."""
    return _build_result({
        "source_evidence": source_evidence,
        "b2_result": b2_result,
        "theta_a_reference": theta_a_reference,
        "method_profile": method_profile,
        "existing_c0": existing_c0,
    })
